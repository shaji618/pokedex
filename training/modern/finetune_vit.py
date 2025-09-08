from __future__ import annotations

import argparse
import json
import logging
import random
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from sklearn.model_selection import train_test_split
from torch.utils.data import Dataset
from transformers import (
    AutoImageProcessor,
    AutoModelForImageClassification,
    EarlyStoppingCallback,
    Trainer,
    TrainingArguments,
)
from transformers.trainer_utils import set_seed

from training.modern.training_utils import (
    add_debug,
    add_dry_run,
    find_image_files,
    get_model_name,
    get_pokemon_display_name,
    iter_pokemon_directories,
    list_supported_models,
)


warnings.filterwarnings("ignore", category=UserWarning, module="transformers")


class LabelSmoothingCrossEntropy(nn.Module):
    def __init__(self, smoothing: float = 0.1) -> None:
        super().__init__()
        self.smoothing = smoothing

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        log_probs = F.log_softmax(logits, dim=-1)
        nll_loss = -log_probs.gather(dim=-1, index=targets.unsqueeze(1)).squeeze(1)
        smooth_loss = -log_probs.mean(dim=-1)
        loss = (1 - self.smoothing) * nll_loss + self.smoothing * smooth_loss
        return loss.mean()


class FocalLoss(nn.Module):
    def __init__(self, alpha: float = 1.0, gamma: float = 2.0) -> None:
        super().__init__()
        self.alpha = alpha
        self.gamma = gamma

    def forward(self, logits: torch.Tensor, targets: torch.Tensor) -> torch.Tensor:
        ce_loss = F.cross_entropy(logits, targets, reduction="none")
        pt = torch.exp(-ce_loss)
        focal_loss = self.alpha * (1 - pt) ** self.gamma * ce_loss
        return focal_loss.mean()


class AdvancedPokemonDataset(Dataset):
    def __init__(
        self,
        image_paths: list[Path],
        labels: list[str],
        label2id: dict[str, int],
        processor: AutoImageProcessor,
        augment_transform: callable | None = None,
        image_size: int = 224,
    ) -> None:
        self.image_paths = image_paths
        self.labels = labels
        self.label2id = label2id
        self.processor = processor
        self.augment_transform = augment_transform
        self.image_size = image_size

    def __len__(self) -> int:
        return len(self.image_paths)

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        try:
            from PIL import Image

            image = Image.open(self.image_paths[idx]).convert("RGB")
            if self.augment_transform:
                image = self.augment_transform(image)
                if torch.is_tensor(image):
                    import torchvision.transforms as transforms

                    to_pil = transforms.ToPILImage()
                    if image.min() < 0:
                        denorm = transforms.Normalize(
                            mean=[-0.485 / 0.229, -0.456 / 0.224, -0.406 / 0.225],
                            std=[1 / 0.229, 1 / 0.224, 1 / 0.225],
                        )
                        image = denorm(image)
                        image = torch.clamp(image, 0, 1)
                    image = to_pil(image)
            inputs = self.processor(image, return_tensors="pt")
            label_id = self.label2id[self.labels[idx]]
            return {
                "pixel_values": inputs["pixel_values"].squeeze(0),
                "labels": torch.tensor(label_id, dtype=torch.long),
            }
        except Exception:
            dummy_image = torch.zeros(3, self.image_size, self.image_size)
            return {
                "pixel_values": dummy_image,
                "labels": torch.tensor(0, dtype=torch.long),
            }


class ModernTrainer(Trainer):
    def __init__(self, loss_fn: nn.Module, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.loss_fn = loss_fn

    def compute_loss(self, model: Any, inputs: Any, return_outputs: bool = False) -> Any:
        labels = inputs.get("labels")
        outputs = model(**inputs)
        loss = self.loss_fn(outputs.logits, labels) if labels is not None else outputs.loss
        return (loss, outputs) if return_outputs else loss


def load_model_and_processor(
    model_name: str,
    num_labels: int,
    id2label: dict[int, str],
    label2id: dict[str, int],
) -> tuple[AutoModelForImageClassification, AutoImageProcessor]:
    full_model_name = get_model_name(model_name)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger = logging.getLogger("training")
    logger.info(f"Loading model: {full_model_name}")
    try:
        processor = AutoImageProcessor.from_pretrained(full_model_name)
        model = AutoModelForImageClassification.from_pretrained(
            full_model_name,
            num_labels=num_labels,
            id2label=id2label,
            label2id=label2id,
            ignore_mismatched_sizes=True,
        )
        logger.info(f"✅ Successfully loaded {model.__class__.__name__}")
        return model, processor
    except Exception as e:
        logger.error(f"❌ Failed to load {full_model_name}: {e}")
        fallback_name = "google/vit-base-patch16-224-in21k"
        logger.warning(f"🔄 Falling back to {fallback_name}")
        processor = AutoImageProcessor.from_pretrained(fallback_name)
        model = AutoModelForImageClassification.from_pretrained(
            fallback_name,
            num_labels=num_labels,
            id2label=id2label,
            label2id=label2id,
            ignore_mismatched_sizes=True,
        )
        return model, processor


def collect_training_data(
    use_augmented: bool = True,
    min_images_per_pokemon: int = 10,
    max_images_per_pokemon: int | None = None,
    validation_split: float = 0.1,
    random_state: int = 42,
) -> tuple[list[Path], list[str], list[Path], list[str], dict[str, int], dict[int, str]]:
    all_image_paths = []
    all_labels = []
    pokemon_stats = {}
    for pokemon_dir in iter_pokemon_directories():
        display_name = get_pokemon_display_name(pokemon_dir)
        image_paths = []
        images_dir = pokemon_dir / "images"
        if images_dir.exists():
            image_paths.extend(find_image_files(images_dir))
        if use_augmented:
            for aug_dir_name in ["images_aug", "images_aug_modern"]:
                aug_dir = pokemon_dir / aug_dir_name
                if aug_dir.exists():
                    image_paths.extend(find_image_files(aug_dir))
        if len(image_paths) < min_images_per_pokemon:
            continue
        if max_images_per_pokemon and len(image_paths) > max_images_per_pokemon:
            random.shuffle(image_paths)
            image_paths = image_paths[:max_images_per_pokemon]
        labels = [display_name] * len(image_paths)
        all_image_paths.extend(image_paths)
        all_labels.extend(labels)
        pokemon_stats[display_name] = len(image_paths)
    unique_labels = sorted(set(all_labels))
    label2id = {label: idx for idx, label in enumerate(unique_labels)}
    id2label = {idx: label for label, idx in label2id.items()}
    train_paths, val_paths, train_labels, val_labels = train_test_split(
        all_image_paths,
        all_labels,
        test_size=validation_split,
        stratify=all_labels,
        random_state=random_state,
    )
    return train_paths, train_labels, val_paths, val_labels, label2id, id2label


def compute_metrics(eval_pred: Any) -> dict[str, float]:
    predictions, labels = eval_pred
    if isinstance(predictions, tuple):
        predictions = predictions[0]
    predictions = np.argmax(predictions, axis=1)
    accuracy = (predictions == labels).mean()
    if len(np.unique(labels)) >= 5:
        logits = eval_pred[0]
        if isinstance(logits, tuple):
            logits = logits[0]
        top5_preds = np.argsort(logits, axis=1)[:, -5:]
        top5_accuracy = np.mean([label in top5_preds[i] for i, label in enumerate(labels)])
    else:
        top5_accuracy = accuracy
    return {
        "accuracy": accuracy,
        "top5_accuracy": top5_accuracy,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Modern Pokemon Vision Transformer fine-tuning",
        epilog="""
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_dry_run(parser, help="Show training configuration without actually training")
    add_debug(parser, help="Enable debug output and checkpointing")
    model_group = parser.add_argument_group("Model Configuration")
    model_group.add_argument(
        "--model",
        type=str,
        default="swin-base",
        help="Model architecture (default: swin-base, use --list-models to see options)",
    )
    model_group.add_argument(
        "--list-models", action="store_true", help="List all supported model architectures and exit"
    )
    train_group = parser.add_argument_group("Training Configuration")
    train_group.add_argument(
        "--output-dir",
        type=str,
        default="pokemon_classifier_modern",
        help="Directory to save the trained model (default: pokemon_classifier_modern)",
    )
    train_group.add_argument(
        "--epochs", type=int, default=5, help="Number of training epochs (default: 5)"
    )
    train_group.add_argument(
        "--batch-size", type=int, default=16, help="Training batch size (default: 16)"
    )
    train_group.add_argument(
        "--learning-rate", type=float, default=3e-5, help="Learning rate (default: 3e-5)"
    )
    train_group.add_argument(
        "--warmup-ratio",
        type=float,
        default=0.1,
        help="Warmup ratio for learning rate scheduling (default: 0.1)",
    )
    train_group.add_argument(
        "--weight-decay",
        type=float,
        default=0.01,
        help="Weight decay for regularization (default: 0.01)",
    )
    advanced_group = parser.add_argument_group("Advanced Training Options")
    advanced_group.add_argument(
        "--loss-function",
        choices=["cross_entropy", "label_smoothing", "focal"],
        default="label_smoothing",
        help="Loss function to use (default: label_smoothing)",
    )
    advanced_group.add_argument(
        "--label-smoothing", type=float, default=0.1, help="Label smoothing factor (default: 0.1)"
    )
    advanced_group.add_argument(
        "--gradient-clipping",
        type=float,
        default=1.0,
        help="Gradient clipping value (default: 1.0)",
    )
    advanced_group.add_argument(
        "--lr-scheduler",
        choices=["cosine", "linear", "constant"],
        default="cosine",
        help="Learning rate scheduler (default: cosine)",
    )
    data_group = parser.add_argument_group("Data Configuration")
    data_group.add_argument(
        "--use-augmented",
        action="store_true",
        default=True,
        help="Use augmented training data (default: True)",
    )
    data_group.add_argument(
        "--no-augmented",
        action="store_true",
        help="Don't use augmented data (only original images)",
    )
    data_group.add_argument(
        "--max-images-per-pokemon",
        type=int,
        help="Maximum images per Pokemon (for faster training)",
    )
    data_group.add_argument(
        "--validation-split", type=float, default=0.1, help="Validation set size (default: 0.1)"
    )
    system_group = parser.add_argument_group("System Configuration")
    system_group.add_argument(
        "--fp16", action="store_true", help="Enable mixed precision training (recommended for GPU)"
    )
    system_group.add_argument(
        "--dataloader-workers",
        type=int,
        default=4,
        help="Number of dataloader workers (default: 4)",
    )
    system_group.add_argument(
        "--seed", type=int, default=42, help="Random seed for reproducibility (default: 42)"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.list_models:
        for model_key in list_supported_models():
            get_model_name(model_key)
        return 0
    if args.dry_run:
        pass
    set_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if device.type == "cuda":
        pass
    use_augmented = args.use_augmented and not args.no_augmented
    train_paths, train_labels, val_paths, val_labels, label2id, id2label = collect_training_data(
        use_augmented=use_augmented,
        max_images_per_pokemon=args.max_images_per_pokemon,
        validation_split=args.validation_split,
        random_state=args.seed,
    )
    if args.dry_run:
        return 0
    model, processor = load_model_and_processor(args.model, len(label2id), id2label, label2id)
    train_dataset = AdvancedPokemonDataset(train_paths, train_labels, label2id, processor)
    val_dataset = AdvancedPokemonDataset(val_paths, val_labels, label2id, processor)
    if args.loss_function == "label_smoothing":
        loss_fn = LabelSmoothingCrossEntropy(smoothing=args.label_smoothing)
    elif args.loss_function == "focal":
        loss_fn = FocalLoss()
    else:
        loss_fn = nn.CrossEntropyLoss()
    output_dir = Path(args.output_dir)
    training_args = TrainingArguments(
        output_dir=str(output_dir),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        warmup_ratio=args.warmup_ratio,
        weight_decay=args.weight_decay,
        learning_rate=args.learning_rate,
        fp16=args.fp16,
        dataloader_num_workers=args.dataloader_workers,
        max_grad_norm=args.gradient_clipping,
        evaluation_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=3,
        load_best_model_at_end=True,
        metric_for_best_model="accuracy",
        greater_is_better=True,
        logging_steps=50,
        logging_strategy="steps",
        report_to=None,
        seed=args.seed,
        data_seed=args.seed,
    )
    trainer = ModernTrainer(
        loss_fn=loss_fn,
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        tokenizer=processor,
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=2)],
    )
    trainer.train()
    trainer.save_model()
    processor.save_pretrained(output_dir)
    metadata = {
        "model_name": get_model_name(args.model),
        "num_classes": len(label2id),
        "training_images": len(train_paths),
        "validation_images": len(val_paths),
        "id2label": id2label,
        "label2id": label2id,
        "training_config": {
            "epochs": args.epochs,
            "batch_size": args.batch_size,
            "learning_rate": args.learning_rate,
            "loss_function": args.loss_function,
            "label_smoothing": args.label_smoothing,
            "use_augmented": use_augmented,
        },
    }
    with open(output_dir / "training_metadata.json", mode="w") as f:
        json.dump(metadata, f, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
