from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import random
from pathlib import Path

import torch
import torchvision.transforms as transforms
from PIL import Image

from training.modern.training_utils import (
    add_debug,
    add_dry_run,
    add_overwrite,
    add_pokemon,
    atomic_write,
    find_image_files,
    find_pokemon_directory,
    get_augmentation_strategies,
    get_pokemon_display_name,
    iter_pokemon_directories,
    polite_sleep,
)


class ModernAugmentationEngine:
    def __init__(
        self,
        strategy: str = "randaugment",
        image_size: int = 224,
        magnitude: int = 9,
        num_ops: int = 2,
        fill_color: tuple[int, int, int] = (128, 128, 128),
    ) -> None:
        self.strategy = strategy
        self.image_size = image_size
        self.magnitude = magnitude
        self.num_ops = num_ops
        self.fill_color = fill_color
        self.transform = self._build_transform()
        self.denorm_transform = transforms.Compose(
            [
                transforms.Normalize(
                    mean=[-0.485 / 0.229, -0.456 / 0.224, -0.406 / 0.225],
                    std=[1 / 0.229, 1 / 0.224, 1 / 0.225],
                )
            ]
        )

    def _build_transform(self) -> transforms.Compose:
        base_transforms = [
            transforms.Resize((self.image_size, self.image_size), antialias=True),
        ]
        if self.strategy == "randaugment":
            augmentation = transforms.RandAugment(
                num_ops=self.num_ops,
                magnitude=self.magnitude,
                fill=self.fill_color,
            )
        elif self.strategy == "trivialaugment":
            augmentation = transforms.TrivialAugmentWide(fill=self.fill_color)
        elif self.strategy == "autoaugment":
            augmentation = transforms.AutoAugment(
                policy=transforms.AutoAugmentPolicy.IMAGENET,
                fill=self.fill_color,
            )
        elif self.strategy == "pokemon_custom":
            augmentation = self._build_pokemon_policy()
        elif self.strategy == "modern_combined":
            augmentation = self._build_combined_policy()
        else:
            augmentation = self._build_basic_policy()
        pipeline = [
            *base_transforms,
            augmentation,
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225],
            ),
        ]
        return transforms.Compose(pipeline)

    def _build_pokemon_policy(self) -> transforms.Compose:
        return transforms.Compose(
            [
                transforms.RandomChoice(
                    [
                        transforms.ColorJitter(
                            brightness=0.3, contrast=0.3, saturation=0.4, hue=0.1
                        ),
                        transforms.RandomAdjustSharpness(sharpness_factor=1.5),
                        transforms.RandomAutocontrast(p=0.3),
                    ]
                ),
                transforms.RandomChoice(
                    [
                        transforms.RandomRotation(degrees=15, fill=self.fill_color),
                        transforms.RandomAffine(
                            degrees=0, translate=(0.1, 0.1), scale=(0.9, 1.1), fill=self.fill_color
                        ),
                        transforms.RandomPerspective(
                            distortion_scale=0.2, p=0.5, fill=self.fill_color
                        ),
                    ]
                ),
                transforms.RandomHorizontalFlip(p=0.5),
                transforms.RandomChoice(
                    [
                        transforms.RandomResizedCrop(
                            self.image_size, scale=(0.8, 1.0), ratio=(0.9, 1.1), antialias=True
                        ),
                        transforms.Resize((self.image_size, self.image_size), antialias=True),
                    ]
                ),
                transforms.RandomChoice(
                    [
                        transforms.GaussianBlur(kernel_size=3, sigma=(0.1, 1.0)),
                        transforms.RandomEqualize(p=0.3),
                        transforms.Identity(),
                    ]
                ),
            ]
        )

    def _build_combined_policy(self) -> transforms.Compose:
        strategies = [
            transforms.RandAugment(num_ops=1, magnitude=7),
            transforms.TrivialAugmentWide(),
            self._build_pokemon_policy(),
        ]
        return transforms.RandomChoice(strategies)

    def _build_basic_policy(self) -> transforms.Compose:
        return transforms.Compose(
            [
                transforms.RandomHorizontalFlip(p=0.5),
                transforms.RandomRotation(degrees=10, fill=self.fill_color),
                transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2),
                transforms.RandomResizedCrop(self.image_size, scale=(0.9, 1.0), antialias=True),
            ]
        )

    def augment_image(self, image: Image.Image) -> Image.Image:
        tensor = self.transform(image)
        tensor = self.denorm_transform(tensor)
        tensor = torch.clamp(tensor, 0, 1)
        to_pil = transforms.ToPILImage()
        return to_pil(tensor)

    def get_strategy_info(self) -> dict[str, str | int]:
        return {
            "strategy": self.strategy,
            "image_size": self.image_size,
            "magnitude": self.magnitude,
            "num_ops": self.num_ops,
            "description": get_augmentation_strategies().get(self.strategy, "Unknown strategy"),
        }


class TestTimeAugmentation:
    def __init__(self, num_crops: int = 5, flip: bool = True) -> None:
        self.num_crops = num_crops
        self.flip = flip

    def generate_tta_variants(self, image: Image.Image, size: int = 224) -> list[torch.Tensor]:
        variants = []
        normalize = transforms.Compose(
            [
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ]
        )
        center_crop = transforms.Compose(
            [transforms.Resize((size, size), antialias=True), normalize]
        )
        variants.append(center_crop(image))
        for _ in range(self.num_crops - 1):
            crop_transform = transforms.Compose(
                [transforms.RandomResizedCrop(size, scale=(0.9, 1.0), antialias=True), normalize]
            )
            variants.append(crop_transform(image))
        if self.flip:
            flip_transform = transforms.Compose(
                [
                    transforms.RandomHorizontalFlip(p=1.0),
                    transforms.Resize((size, size), antialias=True),
                    normalize,
                ]
            )
            variants.append(flip_transform(image))
        return variants


def augment_pokemon_images(
    pokemon_dir: Path,
    target_count: int,
    augmentation_engine: ModernAugmentationEngine,
    output_subdir: str = "images_aug_modern",
    overwrite: bool = False,
    dry_run: bool = False,
) -> dict[str, int]:
    get_pokemon_display_name(pokemon_dir)
    images_dir = pokemon_dir / "images"
    output_dir = pokemon_dir / output_subdir
    if not images_dir.exists():
        return {"added": 0, "skipped": 0, "errors": 0}
    source_images = find_image_files(images_dir)
    if not source_images:
        return {"added": 0, "skipped": 0, "errors": 0}
    existing_augmented = find_image_files(output_dir) if output_dir.exists() else []
    current_total = len(source_images) + len(existing_augmented)
    if current_total >= target_count and not overwrite:
        return {"added": 0, "skipped": current_total, "errors": 0}
    needed = max(0, target_count - len(source_images))
    if overwrite:
        needed = target_count - len(source_images)
    if dry_run:
        return {"added": needed, "skipped": 0, "errors": 0}
    if overwrite and output_dir.exists():
        for f in output_dir.iterdir():
            if f.is_file():
                with contextlib.suppress(Exception):
                    f.unlink()
    output_dir.mkdir(exist_ok=True)
    added = 0
    errors = 0
    existing_hashes = set()
    for img_path in find_image_files(output_dir):
        try:
            with open(img_path, "rb") as f:
                existing_hashes.add(hashlib.sha1(f.read(), usedforsecurity=False).hexdigest())
        except Exception:
            pass
    while added < needed:
        try:
            source_path = random.choice(source_images)
            source_image = Image.open(source_path).convert("RGB")
            augmented_image = augmentation_engine.augment_image(source_image)
            img_bytes = io.BytesIO()
            augmented_image.save(img_bytes, format="PNG")
            img_data = img_bytes.getvalue()
            img_hash = hashlib.sha1(img_data, usedforsecurity=False).hexdigest()
            if img_hash in existing_hashes:
                continue
            output_path = output_dir / f"{img_hash}.png"
            atomic_write(output_path, img_data)
            existing_hashes.add(img_hash)
            added += 1
            if added % 50 == 0:
                pass
        except Exception:
            errors += 1
            if errors > 10:
                break
    len(source_images) + len(find_image_files(output_dir))
    return {"added": added, "skipped": len(existing_augmented), "errors": errors}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Modern image augmentation for Pokemon training data",
        epilog="""
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_dry_run(parser, help="Preview augmentation without saving files")
    add_overwrite(parser, help="Regenerate all augmented images")
    add_pokemon(parser, help="Process only specific Pokemon")
    add_debug(parser, help="Enable debug output and save intermediate results")
    parser.add_argument(
        "--strategy",
        choices=list(get_augmentation_strategies().keys()),
        default="randaugment",
        help="Augmentation strategy to use (default: randaugment)",
    )
    parser.add_argument(
        "--target-count",
        type=int,
        default=200,
        help="Target total images per Pokemon including originals (default: 200)",
    )
    parser.add_argument(
        "--magnitude",
        type=int,
        default=9,
        choices=range(1, 31),
        help="Augmentation magnitude/severity (1-30, default: 9)",
    )
    parser.add_argument(
        "--num-ops",
        type=int,
        default=2,
        choices=range(1, 5),
        help="Number of augmentation operations for RandAugment (1-4, default: 2)",
    )
    parser.add_argument(
        "--image-size",
        type=int,
        default=224,
        help="Target image size for augmentation (default: 224)",
    )
    parser.add_argument(
        "--output-subdir",
        type=str,
        default="images_aug_modern",
        help="Output subdirectory name (default: images_aug_modern)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.dry_run:
        pass
    aug_engine = ModernAugmentationEngine(
        strategy=args.strategy,
        image_size=args.image_size,
        magnitude=args.magnitude,
        num_ops=args.num_ops,
    )
    aug_engine.get_strategy_info()
    if args.strategy == "randaugment":
        pass
    if args.pokemon:
        pokemon_dir = find_pokemon_directory(args.pokemon)
        if not pokemon_dir:
            return 1
        pokemon_dirs = [pokemon_dir]
    else:
        pokemon_dirs = iter_pokemon_directories()
    total_stats = {"added": 0, "skipped": 0, "errors": 0}
    for _i, pokemon_dir in enumerate(pokemon_dirs, 1):
        if len(pokemon_dirs) > 1:
            pass
        stats = augment_pokemon_images(
            pokemon_dir=pokemon_dir,
            target_count=args.target_count,
            augmentation_engine=aug_engine,
            output_subdir=args.output_subdir,
            overwrite=args.overwrite,
            dry_run=args.dry_run,
        )
        for key in total_stats:
            total_stats[key] += stats[key]
        if not args.dry_run and len(pokemon_dirs) > 1:
            polite_sleep(0.1)
    if total_stats["errors"] > 0:
        pass
    if not args.dry_run:
        pass
    else:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
