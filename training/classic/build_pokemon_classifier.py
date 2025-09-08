from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def get_classifier_output_dir(output_dir: str) -> Path:
    if Path(output_dir).is_absolute():
        return Path(output_dir)
    return PROJECT_ROOT / output_dir


def check_classifier_exists(output_dir: Path) -> dict[str, bool]:
    return {
        "config.json": (output_dir / "config.json").exists(),
        "preprocessor_config.json": (output_dir / "preprocessor_config.json").exists(),
        "pytorch_model.bin": (output_dir / "pytorch_model.bin").exists(),
    }


def run_download_training_images(
    dry_run: bool = False,
    num_images: int = 300,
    engines: str = "all",
    concurrency: int = 8,
) -> bool:
    if dry_run:
        pass
    else:
        pass
    cmd = [
        "python",
        "training/classic/download_training_images.py",
        "--num-images",
        str(num_images),
        "--engines",
        engines,
        "--concurrency",
        str(concurrency),
        "--manifest",
    ]
    if dry_run:
        cmd.append("--dry-run")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT)
        if result.returncode == 0:
            stdout = result.stdout
            stdout.count("Downloaded:")
            stdout.count("Skipped:")
            if not dry_run:
                pass
            else:
                pass
            return True
        else:
            return False
    except Exception:
        return False


def run_augment_training_images(
    dry_run: bool = False,
    num_augmented: int = 150,
    max_ops: int = 3,
) -> bool:
    if dry_run:
        pass
    else:
        pass
    cmd = [
        "python",
        "training/classic/augment_training_images.py",
        "--num-augmented",
        str(num_augmented),
        "--max-ops",
        str(max_ops),
    ]
    if dry_run:
        cmd.append("--dry-run")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT)
        if result.returncode == 0:
            stdout = result.stdout
            stdout.count("Wrote augmented:")
            stdout.count("Skipped augmentation:")
            if not dry_run:
                pass
            else:
                pass
            return True
        else:
            return False
    except Exception:
        return False


def run_finetune_vit(
    dry_run: bool = False,
    output_dir: str = "pokemon_classifier",
    model_name: str = "google/vit-base-patch16-224-in21k",
    epochs: int = 3,
    batch_size: int = 16,
    learning_rate: float = 5e-5,
    use_aug: bool = True,
    fp16: bool = False,
) -> bool:
    if dry_run:
        return True
    cmd = [
        "python",
        "training/classic/finetune_vit.py",
        "--output-dir",
        output_dir,
        "--model-name",
        model_name,
        "--epochs",
        str(epochs),
        "--batch-size",
        str(batch_size),
        "--learning-rate",
        str(learning_rate),
    ]
    if use_aug:
        cmd.append("--use-aug")
    if fp16:
        cmd.append("--fp16")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=PROJECT_ROOT)
        if result.returncode == 0:
            output_path = get_classifier_output_dir(output_dir)
            files_created = check_classifier_exists(output_path)
            for _filename, _exists in files_created.items():
                pass
            return bool(all(files_created.values()))
        else:
            return False
    except Exception:
        return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build complete Pokemon Vision Transformer classifier",
        epilog="""
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without actually training the model",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing model files (config.json, preprocessor_config.json, pytorch_model.bin)",
    )
    data_group = parser.add_argument_group("Data Collection Options")
    data_group.add_argument(
        "--num-images",
        type=int,
        default=300,
        help="Number of images to download per Pokemon (default: 300)",
    )
    data_group.add_argument(
        "--engines",
        choices=["ddg", "brave", "all"],
        default="all",
        help="Search engines to use for image collection (default: all)",
    )
    data_group.add_argument(
        "--concurrency",
        type=int,
        default=8,
        help="Number of concurrent download threads (default: 8)",
    )
    aug_group = parser.add_argument_group("Data Augmentation Options")
    aug_group.add_argument(
        "--num-augmented",
        type=int,
        default=150,
        help="Target total images per Pokemon after augmentation (default: 150)",
    )
    aug_group.add_argument(
        "--max-ops",
        type=int,
        default=3,
        help="Maximum augmentation operations per image (default: 3)",
    )
    train_group = parser.add_argument_group("Training Options")
    train_group.add_argument(
        "--output-dir",
        type=str,
        default="pokemon_classifier",
        help="Directory to save the trained model (default: pokemon_classifier)",
    )
    train_group.add_argument(
        "--model-name",
        type=str,
        default="google/vit-base-patch16-224-in21k",
        help="Base ViT model to fine-tune (default: google/vit-base-patch16-224-in21k)",
    )
    train_group.add_argument(
        "--epochs", type=int, default=3, help="Number of training epochs (default: 3)"
    )
    train_group.add_argument(
        "--batch-size", type=int, default=16, help="Training batch size (default: 16)"
    )
    train_group.add_argument(
        "--learning-rate", type=float, default=5e-5, help="Learning rate (default: 5e-5)"
    )
    train_group.add_argument(
        "--no-aug",
        action="store_true",
        help="Don't use augmented images during training (use original images only)",
    )
    train_group.add_argument(
        "--fp16",
        action="store_true",
        help="Enable mixed precision training (requires compatible GPU)",
    )
    skip_group = parser.add_argument_group("Skip Options (for development/testing)")
    skip_group.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip image download step (use existing images)",
    )
    skip_group.add_argument(
        "--skip-augmentation",
        action="store_true",
        help="Skip image augmentation step (use existing images)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.dry_run:
        pass
    output_path = get_classifier_output_dir(args.output_dir)
    existing_files = check_classifier_exists(output_path)
    if any(existing_files.values()) and not args.overwrite:
        for _filename, exists in existing_files.items():
            if exists:
                pass
        raise SystemExit(1)
    elif any(existing_files.values()) and args.overwrite:
        pass
    if args.skip_download:
        download_success = True
    else:
        download_success = run_download_training_images(
            dry_run=args.dry_run,
            num_images=args.num_images,
            engines=args.engines,
            concurrency=args.concurrency,
        )
        if not download_success:
            raise SystemExit(1)
    if args.skip_augmentation:
        augmentation_success = True
    else:
        augmentation_success = run_augment_training_images(
            dry_run=args.dry_run,
            num_augmented=args.num_augmented,
            max_ops=args.max_ops,
        )
        if not augmentation_success:
            pass
    training_success = run_finetune_vit(
        dry_run=args.dry_run,
        output_dir=args.output_dir,
        model_name=args.model_name,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        use_aug=not args.no_aug,
        fp16=args.fp16,
    )
    if not training_success:
        raise SystemExit(1)
    if args.dry_run:
        pass
    else:
        final_files = check_classifier_exists(output_path)
        if all(final_files.values()):
            pass
        else:
            for _filename, exists in final_files.items():
                pass


if __name__ == "__main__":
    main()
