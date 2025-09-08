from __future__ import annotations

import argparse
import logging
import random
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import torch
from PIL import Image
from sklearn.model_selection import train_test_split
from torch.utils.data import Dataset
from transformers import (
    AutoImageProcessor,
    AutoModelForImageClassification,
    EarlyStoppingCallback,
    Trainer,
    TrainingArguments,
)


logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("training")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
POKEMON_DATA_DIR = PROJECT_ROOT / "pokemon_data"


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def list_species_dirs(base: Path) -> list[Path]:
    return [p for p in sorted(base.iterdir()) if p.is_directory()]


def display_name_for(directory_path: Path) -> str:
    meta = directory_path / "metadata.json"
    if meta.exists():
        try:
            import json

            with open(meta, encoding="utf-8") as f:
                data = json.load(f)
            name = data.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
        except Exception:
            pass
    return directory_path.name


def gather_image_files(directory_path: Path, *, use_aug: bool) -> list[tuple[Path, str]]:
    pairs: list[tuple[Path, str]] = []
    candidates: list[Path] = []
    base = directory_path / "images"
    if base.exists():
        candidates.append(base)
    if use_aug:
        aug = directory_path / "images_aug"
        if aug.exists():
            candidates.append(aug)
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    label = display_name_for(directory_path)
    for cdir in candidates:
        for f in cdir.iterdir():
            if f.is_file() and f.suffix.lower() in exts:
                pairs.append((f, label))
    return pairs


def build_label_mappings(labels: Sequence[str]) -> tuple[dict[str, int], dict[int, str]]:
    uniq = sorted(set(labels))
    label2id = {name: idx for idx, name in enumerate(uniq)}
    id2label = {idx: name for name, idx in label2id.items()}
    return label2id, id2label


class PokemonImageDataset(Dataset):
    def __init__(
        self,
        pairs: Sequence[tuple[Path, str]],
        processor: AutoImageProcessor,
        label2id: dict[str, int],
    ) -> None:
        self.pairs = list(pairs)
        self.processor = processor
        self.label2id = label2id

    def __len__(self) -> int:
        return len(self.pairs)

    def __getitem__(self, idx: int) -> dict[str, Any]:
        path, label_name = self.pairs[idx]
        try:
            image = Image.open(path).convert("RGB")
        except Exception:
            image = Image.new(
                "RGB",
                (self.processor.size.get("width", 224), self.processor.size.get("height", 224)),
                (0, 0, 0),
            )
        pixel_values = self.processor(images=image, return_tensors="pt").pixel_values[0]
        label_id = self.label2id[label_name]
        return {"pixel_values": pixel_values, "labels": label_id}


def split_pairs(
    pairs: list[tuple[Path, str]], val_ratio: float, seed: int
) -> tuple[list[tuple[Path, str]], list[tuple[Path, str]]]:
    X = [str(p) for p, _ in pairs]
    y = [lbl for _, lbl in pairs]
    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=max(0.01, min(0.5, val_ratio)), random_state=seed, stratify=y
    )
    train_pairs = [(Path(p), label) for p, label in zip(X_train, y_train, strict=False)]
    val_pairs = [(Path(p), label) for p, label in zip(X_val, y_val, strict=False)]
    return train_pairs, val_pairs


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fine-tune ViT on pokemon_data images")
    p.add_argument(
        "--model-name",
        type=str,
        default="google/vit-base-patch16-224-in21k",
        help="HF model checkpoint",
    )
    p.add_argument(
        "--output-dir",
        type=str,
        default="pokemon_classifier",
        help="Directory to save fine-tuned model",
    )
    p.add_argument("--epochs", type=int, default=3)
    p.add_argument("--batch-size", type=int, default=16)
    p.add_argument("--learning-rate", type=float, default=5e-5)
    p.add_argument("--val-ratio", type=float, default=0.1)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--use-aug", action="store_true", help="Include images_aug as additional data")
    p.add_argument("--fp16", action="store_true", help="Enable mixed precision training")
    p.add_argument("--num-workers", type=int, default=4)
    p.add_argument(
        "--save-steps", type=int, default=0, help="If >0, save checkpoints every N steps"
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    set_seed(args.seed)

    base = POKEMON_DATA_DIR
    if not base.exists():
        logger.error(f"pokemon_data directory not found: {base}")
        return 2
    species_dirs = list_species_dirs(base)
    all_pairs: list[tuple[Path, str]] = []
    for sp_directory in species_dirs:
        pairs = gather_image_files(sp_directory, use_aug=args.use_aug)
        all_pairs.extend(pairs)
    if len(all_pairs) < 2:
        logger.error("Not enough images found to train.")
        return 3
    labels = [label for _, label in all_pairs]
    label2id, id2label = build_label_mappings(labels)
    number_labels = len(label2id)
    if number_labels < 2:
        logger.error("Need at least 2 classes for classification.")
        return 4
    train_pairs, val_pairs = split_pairs(
        all_pairs, val_ratio=max(0.01, min(0.5, args.val_ratio)), seed=args.seed
    )
    processor = AutoImageProcessor.from_pretrained(args.model_name)
    model = AutoModelForImageClassification.from_pretrained(
        args.model_name,
        number_labels=number_labels,
        id2label=id2label,
        label2id=label2id,
    )
    train_dataset = PokemonImageDataset(train_pairs, processor=processor, label2id=label2id)
    eval_dataset = PokemonImageDataset(val_pairs, processor=processor, label2id=label2id)
    training_args = TrainingArguments(
        output_directory=str(Path(args.output_directory)),
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        evaluation_strategy="steps" if args.save_steps > 0 else "epoch",
        save_strategy="steps" if args.save_steps > 0 else "epoch",
        save_steps=args.save_steps if args.save_steps > 0 else None,
        number_train_epochs=args.epochs,
        learning_rate=args.learning_rate,
        weight_decay=0.05,
        lr_scheduler_type="cosine",
        seed=args.seed,
        dataloader_number_workers=args.number_workers,
        fp16=args.fp16,
        logging_steps=50,
        remove_unused_columns=False,
        load_best_model_at_end=True,
        metric_for_best_model="accuracy",
        greater_is_better=True,
    )

    def compute_metrics(eval_pred: Any) -> dict[str, float]:
        logits, labels = eval_pred
        if isinstance(logits, list | tuple):
            logits = logits[0]
        preds = np.argmax(logits, axis=-1)
        acc = (
            (preds == labels).mean().item()
            if hasattr((preds == labels), "item")
            else float((preds == labels).mean())
        )
        return {"accuracy": acc}

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        tokenizer=processor,
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=2)],
    )
    trainer.train()
    trainer.save_model()
    processor.save_pretrained(args.output_directory)
    logger.info(f"Saved fine-tuned model to: {args.output_directory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
