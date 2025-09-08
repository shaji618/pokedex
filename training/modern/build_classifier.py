from __future__ import annotations

import argparse
import logging
import subprocess
import time
from pathlib import Path

from training.modern.training_utils import (
    add_debug,
    add_dry_run,
    count_total_training_images,
    get_augmentation_strategies,
    get_recommended_training_config,
    list_supported_models,
    print_training_summary,
)


logging.basicConfig(level=logging.INFO, format="%(message)s")
training_logger = logging.getLogger("training")


class ModernTrainingPipeline:
    def __init__(
        self,
        dry_run: bool = False,
        debug: bool = False,
        output_dir: str = "pokemon_classifier_modern",
    ) -> None:
        self.dry_run = dry_run
        self.debug = debug
        self.output_dir = Path(output_dir)
        self.logger = training_logger
        self.stats = {
            "download_success": False,
            "filter_success": False,
            "augment_success": False,
            "train_success": False,
            "images_downloaded": 0,
            "images_filtered": 0,
            "images_augmented": 0,
            "training_time": 0.0,
        }

    def check_existing_model(self, overwrite: bool = False) -> bool:
        if not self.output_dir.exists():
            return True
        model_files = [
            "config.json",
            "preprocessor_config.json",
            "pytorch_model.bin",
        ]
        existing_files = [f for f in model_files if (self.output_dir / f).exists()]
        if not existing_files:
            return True
        if not overwrite:
            self.logger.warning(f"\n⚠️ Model files already exist in {self.output_dir}:")
            for f in existing_files:
                self.logger.info(f"  • {f}")
            self.logger.info(
                "\nUse --overwrite to replace existing model, or --dry-run to preview training."
            )
            return False
        self.logger.info(
            f"\n🔄 OVERWRITE MODE: Will replace existing model files in {self.output_dir}"
        )
        return True

    def run_download_training_images(
        self,
        num_images: int = 300,
        engines: str = "all",
        concurrency: int = 8,
    ) -> bool:
        step_name = "🌐 Download Training Images"
        if self.dry_run:
            self.logger.info(f"\n{step_name} (Preview)")
            self.logger.info(
                f"  🔍 Would download {num_images} images per Pokemon using {engines} engines"
            )
            self.logger.info(f"  📊 Concurrency: {concurrency} threads")
            return True
        self.logger.info(f"\n{step_name}")
        self.logger.info(f"  📥 Target: {num_images} images per Pokemon")
        self.logger.info(f"  🌐 Search engines: {engines}")
        cmd = [
            "python",
            "../classic/download_training_images.py",
            "--num-images",
            str(num_images),
            "--engines",
            engines,
            "--concurrency",
            str(concurrency),
            "--manifest",
        ]
        success = self._run_subprocess(cmd, "Image download")
        self.stats["download_success"] = success
        return success

    def run_clip_quality_filter(
        self,
        quality_level: str = "moderate",
        clip_model: str = "ViT-B/32",
    ) -> bool:
        if self.dry_run:
            return True
        cmd = [
            "python",
            "clip_quality_filter.py",
            "--quality-level",
            quality_level,
            "--clip-model",
            clip_model,
        ]
        try:
            success = self._run_subprocess(cmd, "CLIP filtering", required=False)
            self.stats["filter_success"] = success
            if success:
                pass
            else:
                pass
            return True
        except Exception:
            return True

    def run_modern_augmentation(
        self,
        strategy: str = "randaugment",
        target_count: int = 200,
        magnitude: int = 9,
    ) -> bool:
        if self.dry_run:
            return True
        cmd = [
            "python",
            "augment_images.py",
            "--strategy",
            strategy,
            "--target-count",
            str(target_count),
            "--magnitude",
            str(magnitude),
        ]
        success = self._run_subprocess(cmd, "Modern augmentation")
        self.stats["augment_success"] = success
        return success

    def run_modern_training(
        self,
        model: str = "swin-base",
        epochs: int = 5,
        batch_size: int = 16,
        learning_rate: float = 3e-5,
        loss_function: str = "label_smoothing",
        use_fp16: bool = True,
    ) -> bool:
        if self.dry_run:
            return True
        start_time = time.time()
        cmd = [
            "python",
            "finetune_vit.py",
            "--model",
            model,
            "--output-dir",
            str(self.output_dir),
            "--epochs",
            str(epochs),
            "--batch-size",
            str(batch_size),
            "--learning-rate",
            str(learning_rate),
            "--loss-function",
            loss_function,
            "--use-augmented",
        ]
        if use_fp16:
            cmd.append("--fp16")
        success = self._run_subprocess(cmd, "Modern training")
        training_time = time.time() - start_time
        self.stats["training_time"] = training_time
        self.stats["train_success"] = success
        if success:
            pass
        return success

    def _run_subprocess(
        self,
        cmd: list[str],
        _step_name: str,
        required: bool = True,
    ) -> bool:
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=Path(__file__).parent,
                timeout=3600,
            )
            if result.returncode == 0:
                if self.debug:
                    pass
                return True
            else:
                if self.debug:
                    pass
                return not required
        except subprocess.TimeoutExpired:
            return not required
        except Exception:
            return not required

    def validate_final_model(self) -> bool:
        if self.dry_run:
            return True
        required_files = [
            "config.json",
            "preprocessor_config.json",
            "pytorch_model.bin",
            "training_metadata.json",
        ]
        missing_files = []
        for filename in required_files:
            if not (self.output_dir / filename).exists():
                missing_files.append(filename)
        if missing_files:
            for _f in missing_files:
                pass
            return False
        model_file = self.output_dir / "pytorch_model.bin"
        if model_file.stat().st_size < 100 * 1024 * 1024:
            pass
        return True

    def print_final_summary(self) -> None:
        if self.dry_run:
            pass
        else:
            if self.stats["training_time"] > 0:
                pass
        if not self.dry_run and self.stats["train_success"]:
            pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Modern Pokemon Vision Transformer training pipeline",
        epilog="""
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_dry_run(parser, help="Preview the training pipeline without executing")
    add_debug(parser, help="Enable detailed output and intermediate results")
    core_group = parser.add_argument_group("Core Configuration")
    core_group.add_argument(
        "--overwrite", action="store_true", help="Overwrite existing model files"
    )
    core_group.add_argument(
        "--output-dir",
        type=str,
        default="pokemon_classifier_modern",
        help="Directory to save the trained model (default: pokemon_classifier_modern)",
    )
    data_group = parser.add_argument_group("Data Pipeline")
    data_group.add_argument(
        "--num-images", type=int, default=300, help="Images to download per Pokemon (default: 300)"
    )
    data_group.add_argument(
        "--engines",
        choices=["ddg", "brave", "all"],
        default="all",
        help="Search engines for image download (default: all)",
    )
    data_group.add_argument(
        "--skip-download", action="store_true", help="Skip image download (use existing images)"
    )
    data_group.add_argument(
        "--skip-clip-filter", action="store_true", help="Skip CLIP-based quality filtering"
    )
    aug_group = parser.add_argument_group("Modern Augmentation")
    aug_group.add_argument(
        "--augmentation-strategy",
        choices=list(get_augmentation_strategies().keys()),
        default="randaugment",
        help="Augmentation strategy (default: randaugment)",
    )
    aug_group.add_argument(
        "--target-images",
        type=int,
        default=200,
        help="Target total images per Pokemon after augmentation (default: 200)",
    )
    aug_group.add_argument(
        "--augmentation-magnitude",
        type=int,
        default=9,
        choices=range(1, 31),
        help="Augmentation magnitude (1-30, default: 9)",
    )
    aug_group.add_argument(
        "--skip-augmentation",
        action="store_true",
        help="Skip modern augmentation (use existing images)",
    )
    model_group = parser.add_argument_group("Model & Training")
    model_group.add_argument(
        "--model",
        type=str,
        default="swin-base",
        help="Model architecture (default: swin-base, use --list-models to see options)",
    )
    model_group.add_argument(
        "--epochs", type=int, default=5, help="Number of training epochs (default: 5)"
    )
    model_group.add_argument(
        "--batch-size", type=int, default=16, help="Training batch size (default: 16)"
    )
    model_group.add_argument(
        "--learning-rate", type=float, default=3e-5, help="Learning rate (default: 3e-5)"
    )
    model_group.add_argument(
        "--loss-function",
        choices=["cross_entropy", "label_smoothing", "focal"],
        default="label_smoothing",
        help="Loss function (default: label_smoothing)",
    )
    model_group.add_argument(
        "--no-fp16", action="store_true", help="Disable mixed precision training"
    )
    model_group.add_argument(
        "--list-models", action="store_true", help="List supported model architectures and exit"
    )
    filter_group = parser.add_argument_group("CLIP Quality Filtering")
    filter_group.add_argument(
        "--clip-quality",
        choices=["strict", "moderate", "permissive"],
        default="moderate",
        help="CLIP quality filtering level (default: moderate)",
    )
    filter_group.add_argument(
        "--clip-model",
        choices=["ViT-B/32", "ViT-B/16", "ViT-L/14"],
        default="ViT-B/32",
        help="CLIP model for quality filtering (default: ViT-B/32)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.list_models:
        for model_key in list_supported_models():
            if model_key.startswith(("swin", "convnext")) or model_key.startswith("vit"):
                pass
            else:
                pass
        return 0
    pipeline = ModernTrainingPipeline(
        dry_run=args.dry_run,
        debug=args.debug,
        output_dir=args.output_dir,
    )
    if args.dry_run:
        pass
    if not pipeline.check_existing_model(args.overwrite):
        return 1
    stats = count_total_training_images()
    config = get_recommended_training_config(stats["total_combined"])
    print_training_summary(stats, config)
    success = True
    if args.skip_download:
        pass
    else:
        success &= pipeline.run_download_training_images(
            num_images=args.num_images,
            engines=args.engines,
        )
        if not success and not args.dry_run:
            return 1
    if args.skip_clip_filter:
        pass
    else:
        pipeline.run_clip_quality_filter(
            quality_level=args.clip_quality,
            clip_model=args.clip_model,
        )
    if args.skip_augmentation:
        pass
    else:
        success &= pipeline.run_modern_augmentation(
            strategy=args.augmentation_strategy,
            target_count=args.target_images,
            magnitude=args.augmentation_magnitude,
        )
        if not success and not args.dry_run:
            pass
    success &= pipeline.run_modern_training(
        model=args.model,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        loss_function=args.loss_function,
        use_fp16=not args.no_fp16,
    )
    if not success and not args.dry_run:
        return 1
    if not args.dry_run:
        validation_success = pipeline.validate_final_model()
        if not validation_success:
            return 1
    pipeline.print_final_summary()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
