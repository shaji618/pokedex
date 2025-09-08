from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
POKEMON_DATA_DIR = PROJECT_ROOT / "pokemon_data"
POKEMON_CLASSIFIER_DIR = PROJECT_ROOT / "pokemon_classifier"


def add_dry_run(
    parser: argparse.ArgumentParser, *, help: str | None = None
) -> argparse.ArgumentParser:
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=help or "Do not write files; only report actions",
    )
    return parser


def add_overwrite(
    parser: argparse.ArgumentParser, *, help: str | None = None
) -> argparse.ArgumentParser:
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help=help or "Overwrite existing files even if unchanged",
    )
    return parser


def add_pokemon(
    parser: argparse.ArgumentParser, *, help: str | None = None
) -> argparse.ArgumentParser:
    parser.add_argument(
        "--pokemon",
        type=str,
        default=None,
        help=help or "Single Pokémon display name from metadata.json",
    )
    return parser


def add_debug(
    parser: argparse.ArgumentParser, *, help: str | None = None
) -> argparse.ArgumentParser:
    parser.add_argument(
        "--debug",
        action="store_true",
        help=help or "Write debug artifacts for troubleshooting",
    )
    return parser


def iter_pokemon_directories(base_directory: Path | None = None) -> list[Path]:
    if base_directory is None:
        base_directory = POKEMON_DATA_DIR
    directories = []
    for child in sorted(base_directory.iterdir()):
        if child.is_dir() and (child / "metadata.json").exists():
            directories.append(child)
    return directories


def read_pokemon_metadata(pokemon_dir: Path) -> dict | None:
    metadata_path = pokemon_dir / "metadata.json"
    if not metadata_path.exists():
        return None
    try:
        with open(metadata_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def get_pokemon_display_name(pokemon_dir: Path) -> str:
    metadata = read_pokemon_metadata(pokemon_dir)
    if metadata and metadata.get("name"):
        return metadata["name"]
    return pokemon_dir.name


def find_pokemon_directory(pokemon_name: str, base_directory: Path | None = None) -> Path | None:
    if base_directory is None:
        base_directory = POKEMON_DATA_DIR
    normalized_query = pokemon_name.strip().lower().replace(" ", "_").replace("'", "_")
    for pokemon_dir in iter_pokemon_directories(base_directory):
        if pokemon_dir.name.lower() == normalized_query:
            return pokemon_dir
    for pokemon_dir in iter_pokemon_directories(base_directory):
        display_name = get_pokemon_display_name(pokemon_dir)
        if display_name.lower().replace(" ", "_").replace("'", "_") == normalized_query:
            return pokemon_dir
    return None


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
    tmp.replace(path)


def polite_sleep(seconds: float = 0.3) -> None:
    time.sleep(seconds)


def get_image_extensions() -> set[str]:
    return {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}


def find_image_files(directory: Path, recursive: bool = False) -> list[Path]:
    extensions = get_image_extensions()
    files = []
    if not directory.exists():
        return files
    if recursive:
        for ext in extensions:
            files.extend(directory.rglob(f"*{ext}"))
            files.extend(directory.rglob(f"*{ext.upper()}"))
    else:
        for file_path in directory.iterdir():
            if file_path.is_file() and file_path.suffix.lower() in extensions:
                files.append(file_path)
    return sorted(files)


def validate_training_data(
    pokemon_dir: Path, min_images: int = 10
) -> dict[str, bool | int | list[str]]:
    result = {
        "valid": False,
        "has_metadata": False,
        "has_images": False,
        "image_count": 0,
        "has_augmented": False,
        "augmented_count": 0,
        "issues": [],
    }
    if (pokemon_dir / "metadata.json").exists():
        result["has_metadata"] = True
    else:
        result["issues"].append("Missing metadata.json")
    images_dir = pokemon_dir / "images"
    if images_dir.exists():
        images = find_image_files(images_dir)
        result["image_count"] = len(images)
        if len(images) >= min_images:
            result["has_images"] = True
        else:
            result["issues"].append(f"Only {len(images)} images (need {min_images})")
    else:
        result["issues"].append("Missing images/ directory")
    aug_dir = pokemon_dir / "images_aug"
    if aug_dir.exists():
        aug_images = find_image_files(aug_dir)
        result["augmented_count"] = len(aug_images)
        if len(aug_images) > 0:
            result["has_augmented"] = True
    result["valid"] = result["has_metadata"] and result["has_images"]
    return result


def count_total_training_images() -> dict[str, int]:
    stats = {
        "pokemon_count": 0,
        "total_original": 0,
        "total_augmented": 0,
        "total_combined": 0,
        "valid_pokemon": 0,
    }
    for pokemon_dir in iter_pokemon_directories():
        stats["pokemon_count"] += 1
        validation = validate_training_data(pokemon_dir)
        stats["total_original"] += validation["image_count"]
        stats["total_augmented"] += validation["augmented_count"]
        if validation["valid"]:
            stats["valid_pokemon"] += 1
    stats["total_combined"] = stats["total_original"] + stats["total_augmented"]
    return stats


SUPPORTED_MODELS = {
    "vit-base": "google/vit-base-patch16-224-in21k",
    "vit-large": "google/vit-large-patch16-224-in21k",
    "swin-base": "microsoft/swin-base-patch4-window7-224",
    "swin-large": "microsoft/swin-large-patch4-window7-224",
    "convnext-base": "facebook/convnext-base-224",
    "convnext-large": "facebook/convnext-large-224",
    "efficientnet-b0": "google/efficientnet-b0",
    "efficientnet-b3": "google/efficientnet-b3",
    "clip-vit-base": "openai/clip-vit-base-patch16",
    "clip-vit-large": "openai/clip-vit-large-patch14",
}


def get_model_name(model_key: str) -> str:
    if model_key in SUPPORTED_MODELS:
        return SUPPORTED_MODELS[model_key]
    return model_key


def list_supported_models() -> list[str]:
    return list(SUPPORTED_MODELS.keys())


AUGMENTATION_STRATEGIES = {
    "basic": "Original 6-technique approach from 2021 tutorial",
    "randaugment": "RandAugment with principled policy selection",
    "trivialaugment": "TrivialAugmentWide (often better than RandAugment)",
    "autoaugment": "AutoAugment with ImageNet policies",
    "pokemon_custom": "Custom policy optimized for Pokemon images",
    "modern_combined": "Best of multiple modern techniques combined",
}


def get_augmentation_strategies() -> dict[str, str]:
    return AUGMENTATION_STRATEGIES.copy()


def get_recommended_training_config(dataset_size: int, gpu_available: bool = True) -> dict:
    config = {
        "batch_size": 16,
        "epochs": 3,
        "learning_rate": 5e-5,
        "model": "swin-base",
        "augmentation": "randaugment",
        "use_mixed_precision": gpu_available,
        "gradient_clipping": 1.0,
        "label_smoothing": 0.1,
        "warmup_steps": 100,
    }
    if dataset_size < 50000:
        config.update(
            {
                "epochs": 5,
                "learning_rate": 3e-5,
                "label_smoothing": 0.15,
            }
        )
    elif dataset_size > 200000:
        config.update(
            {
                "batch_size": 32 if gpu_available else 16,
                "epochs": 2,
                "learning_rate": 1e-4,
            }
        )
    if not gpu_available:
        config.update(
            {
                "batch_size": 8,
                "use_mixed_precision": False,
                "model": "vit-base",
            }
        )
    return config


def print_training_summary(stats: dict[str, int], config: dict) -> None:
    pass


if __name__ == "__main__":
    pokemon_dirs = iter_pokemon_directories()
    for _i, pdir in enumerate(pokemon_dirs[:5]):
        display_name = get_pokemon_display_name(pdir)
    stats = count_total_training_images()
    print_training_summary(stats, get_recommended_training_config(stats["total_combined"]))
