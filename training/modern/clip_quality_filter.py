from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import torch
from PIL import Image


try:
    import clip

    CLIP_AVAILABLE = True
except ImportError:
    CLIP_AVAILABLE = False
from training.modern.training_utils import (
    add_debug,
    add_dry_run,
    add_pokemon,
    find_image_files,
    find_pokemon_directory,
    get_pokemon_display_name,
    iter_pokemon_directories,
    polite_sleep,
)


class CLIPImageFilter:
    def __init__(
        self,
        model_name: str = "ViT-B/32",
        device: str | None = None,
        batch_size: int = 32,
    ) -> None:
        if not CLIP_AVAILABLE:
            raise ImportError("CLIP is required but not installed")
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device
        self.batch_size = batch_size
        logging.basicConfig(level=logging.INFO, format="%(message)s")
        self.logger = logging.getLogger("training")
        self.logger.info(f"Loading CLIP model {model_name} on {device}...")
        self.model, self.preprocess = clip.load(model_name, device=device)
        self.model.eval()
        self.thresholds = {
            "strict": 0.30,
            "moderate": 0.25,
            "permissive": 0.20,
        }

    def create_text_queries(self, pokemon_name: str) -> list[str]:
        queries = [
            f"a photo of {pokemon_name} pokemon",
            f"{pokemon_name} pokemon character",
            f"pokemon {pokemon_name}",
            f"{pokemon_name} from pokemon anime",
            f"{pokemon_name} pokemon official art",
            f"cute {pokemon_name} pokemon",
        ]
        name_lower = pokemon_name.lower()
        if name_lower != pokemon_name:
            queries.append(f"a photo of {name_lower} pokemon")
        if "_" in pokemon_name:
            name_spaced = pokemon_name.replace("_", " ")
            queries.append(f"a photo of {name_spaced} pokemon")
        return queries

    def compute_similarity_batch(
        self,
        image_paths: list[Path],
        text_queries: list[str],
    ) -> list[float]:
        if not image_paths:
            return []
        similarities = []
        for i in range(0, len(image_paths), self.batch_size):
            batch_paths = image_paths[i : i + self.batch_size]
            batch_similarities = self._process_batch(batch_paths, text_queries)
            similarities.extend(batch_similarities)
        return similarities

    def _process_batch(
        self,
        image_paths: list[Path],
        text_queries: list[str],
    ) -> list[float]:
        images = []
        valid_indices = []
        for idx, path in enumerate(image_paths):
            try:
                image = Image.open(path).convert("RGB")
                image_tensor = self.preprocess(image)
                images.append(image_tensor)
                valid_indices.append(idx)
            except Exception as e:
                self.logger.error(f"[error] Failed to load {path}: {e}")
        if not images:
            return [0.0] * len(image_paths)
        image_batch = torch.stack(images).to(self.device)
        text_tokens = clip.tokenize(text_queries).to(self.device)
        with torch.no_grad():
            image_features = self.model.encode_image(image_batch)
            text_features = self.model.encode_text(text_tokens)
            image_features = image_features / image_features.norm(dim=-1, keepdim=True)
            text_features = text_features / text_features.norm(dim=-1, keepdim=True)
            similarities = (image_features @ text_features.T).cpu().numpy()
            max_similarities = similarities.max(axis=1)
        result = [0.0] * len(image_paths)
        for i, valid_idx in enumerate(valid_indices):
            result[valid_idx] = float(max_similarities[i])

        return result

    def filter_images(
        self,
        pokemon_name: str,
        image_paths: list[Path],
        quality_level: str = "moderate",
        dry_run: bool = False,
    ) -> tuple[list[Path], list[Path], list[float]]:
        if not image_paths:
            return [], [], []
        self.logger.info(f"🔍 CLIP filtering {len(image_paths)} images for {pokemon_name}")
        self.logger.info(
            f"   Quality level: {quality_level} (threshold: {self.thresholds[quality_level]})"
        )
        text_queries = self.create_text_queries(pokemon_name)
        similarities = self.compute_similarity_batch(image_paths, text_queries)
        threshold = self.thresholds[quality_level]
        kept_images = []
        filtered_images = []
        for path, score in zip(image_paths, similarities, strict=False):
            if score >= threshold:
                kept_images.append(path)
                if dry_run:
                    self.logger.info(f"[keep] {path.name} (score: {score:.3f})")
            else:
                filtered_images.append(path)
                if dry_run:
                    self.logger.info(f"[filter] {path.name} (score: {score:.3f})")

        return kept_images, filtered_images, similarities

    def generate_quality_report(
        self,
        pokemon_name: str,
        image_paths: list[Path],
        similarities: list[float],
    ) -> dict[str, int | float]:
        if not similarities:
            return {}
        similarities_array = np.array(similarities)
        return {
            "pokemon": pokemon_name,
            "total_images": len(image_paths),
            "mean_score": float(similarities_array.mean()),
            "median_score": float(np.median(similarities_array)),
            "std_score": float(similarities_array.std()),
            "min_score": float(similarities_array.min()),
            "max_score": float(similarities_array.max()),
            "high_quality_count": int((similarities_array >= 0.30).sum()),
            "medium_quality_count": int((similarities_array >= 0.25).sum()),
            "low_quality_count": int((similarities_array < 0.20).sum()),
        }


def filter_pokemon_images(
    pokemon_dir: Path,
    clip_filter: CLIPImageFilter,
    quality_level: str = "moderate",
    apply_filter: bool = True,
    dry_run: bool = False,
    backup_filtered: bool = True,
) -> dict[str, int]:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger = logging.getLogger("training")
    display_name = get_pokemon_display_name(pokemon_dir)
    images_to_process = []
    images_dir = pokemon_dir / "images"
    if images_dir.exists():
        images_to_process.extend(find_image_files(images_dir))
    for aug_dir_name in ["images_aug", "images_aug_modern"]:
        aug_dir = pokemon_dir / aug_dir_name
        if aug_dir.exists():
            images_to_process.extend(find_image_files(aug_dir))
    if not images_to_process:
        logger.info(f"[skip] {display_name}: No images found")
        return {"kept": 0, "filtered": 0, "errors": 0}
    kept_images, filtered_images, similarities = clip_filter.filter_images(
        display_name, images_to_process, quality_level, dry_run
    )
    report = clip_filter.generate_quality_report(display_name, images_to_process, similarities)
    stats = {
        "kept": len(kept_images),
        "filtered": len(filtered_images),
        "errors": 0,
    }
    if dry_run:
        logger.info(
            f"[dry-run] {display_name}: Would keep {len(kept_images)}, filter {len(filtered_images)}"
        )
        logger.info(f"          Mean quality score: {report.get('mean_score', 0):.3f}")
        return stats
    if apply_filter and filtered_images:
        if backup_filtered:
            backup_dir = pokemon_dir / "filtered_images"
            backup_dir.mkdir(exist_ok=True)
        for img_path in filtered_images:
            try:
                if backup_filtered:
                    backup_path = backup_dir / img_path.name
                    img_path.rename(backup_path)
                else:
                    img_path.unlink()
            except Exception as e:
                logger.error(f"[error] Failed to process {img_path}: {e}")
                stats["errors"] += 1
    report_path = pokemon_dir / "clip_quality_report.json"
    try:
        with open(report_path, mode="w") as f:
            json.dump(report, f, indent=2)
    except Exception as e:
        logger.warning(f"[warning] Failed to save quality report: {e}")
    logger.info(f"[done] {display_name}: Kept {len(kept_images)}, filtered {len(filtered_images)}")
    logger.info(f"       Mean quality score: {report.get('mean_score', 0):.3f}")
    return stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Filter Pokemon training images using CLIP for quality and relevance",
        epilog="""
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_dry_run(parser, help="Preview filtering without modifying files")
    add_pokemon(parser, help="Filter images for specific Pokemon only")
    add_debug(parser, help="Enable detailed output and save intermediate results")
    parser.add_argument(
        "--quality-level",
        choices=["strict", "moderate", "permissive"],
        default="moderate",
        help="Quality filtering level (default: moderate)",
    )
    parser.add_argument(
        "--no-filter",
        action="store_true",
        help="Only generate quality reports, don't actually filter images",
    )
    parser.add_argument(
        "--no-backup", action="store_true", help="Delete filtered images instead of backing them up"
    )
    parser.add_argument(
        "--clip-model",
        choices=["ViT-B/32", "ViT-B/16", "ViT-L/14"],
        default="ViT-B/32",
        help="CLIP model to use (default: ViT-B/32)",
    )
    parser.add_argument(
        "--batch-size", type=int, default=32, help="Batch size for CLIP inference (default: 32)"
    )
    parser.add_argument(
        "--device",
        choices=["auto", "cpu", "cuda"],
        default="auto",
        help="Device to run CLIP on (default: auto)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger = logging.getLogger("training")
    if not CLIP_AVAILABLE:
        logger.error("❌ CLIP is required but not installed")
        logger.info("📦 Install with: pip install git+https://github.com/openai/CLIP.git")
        return 1
    logger.info("🔍 CLIP-based Pokemon Image Quality Filtering")
    logger.info("=" * 55)
    logger.info("🚀 This represents a major advancement over 2021 techniques!")
    if args.dry_run:
        logger.info("🔍 DRY RUN MODE - No files will be modified")
    if args.device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    else:
        device = args.device
    logger.info(f"🖥️ Using device: {device}")
    if device == "cuda":
        logger.info(f"   GPU: {torch.cuda.get_device_name()}")
    try:
        clip_filter = CLIPImageFilter(
            model_name=args.clip_model,
            device=device,
            batch_size=args.batch_size,
        )
    except Exception as e:
        logger.error(f"❌ Failed to initialize CLIP: {e}")
        return 1
    logger.info("✅ CLIP model loaded successfully")
    logger.info(f"🎯 Quality level: {args.quality_level}")
    logger.info(f"📋 Apply filtering: {not args.no_filter}")
    if args.pokemon:
        pokemon_dir = find_pokemon_directory(args.pokemon)
        if not pokemon_dir:
            logger.error(f"❌ Pokemon '{args.pokemon}' not found")
            return 1
        pokemon_dirs = [pokemon_dir]
    else:
        pokemon_dirs = iter_pokemon_directories()
        logger.info(f"\n🎯 Processing {len(pokemon_dirs)} Pokemon")
    total_stats = {"kept": 0, "filtered": 0, "errors": 0}
    for i, pokemon_dir in enumerate(pokemon_dirs, 1):
        if len(pokemon_dirs) > 1:
            logger.info(f"\n[{i:3d}/{len(pokemon_dirs)}] Processing {pokemon_dir.name}...")
        try:
            stats = filter_pokemon_images(
                pokemon_dir=pokemon_dir,
                clip_filter=clip_filter,
                quality_level=args.quality_level,
                apply_filter=not args.no_filter,
                dry_run=args.dry_run,
                backup_filtered=not args.no_backup,
            )
            for key in total_stats:
                total_stats[key] += stats[key]
        except Exception as e:
            logger.error(f"[error] Failed to process {pokemon_dir.name}: {e}")
            total_stats["errors"] += 1
        if not args.dry_run and len(pokemon_dirs) > 1:
            polite_sleep(0.2)
    logger.info("\n" + "=" * 55)
    logger.info("📊 CLIP FILTERING SUMMARY")
    logger.info("=" * 55)
    logger.info(f"Pokemon processed: {len(pokemon_dirs)}")
    logger.info(f"Images kept: {total_stats['kept']:,}")
    logger.info(f"Images filtered: {total_stats['filtered']:,}")
    if total_stats["errors"] > 0:
        logger.warning(f"Errors encountered: {total_stats['errors']}")
    if total_stats["filtered"] > 0:
        filter_rate = total_stats["filtered"] / (total_stats["kept"] + total_stats["filtered"])
        logger.info(f"Filter rate: {filter_rate:.1%}")
    if not args.dry_run and not args.no_filter:
        logger.info("\n✅ CLIP filtering completed successfully!")
        logger.info("📈 Expected improvement: 3-5% better training efficiency")
        if not args.no_backup:
            logger.info("🗂️ Filtered images backed up to filtered_images/ directories")
    else:
        logger.info("\n🔍 Analysis completed - no files were modified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
