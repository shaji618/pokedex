from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import random
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageOps

from training.scripts import cli as cli_utils


PROJECT_ROOT = Path(__file__).resolve().parents[1]
POKEMON_DATA_DIR = PROJECT_ROOT / "pokemon_data"


def iter_species_dirs(base_directory: Path) -> Iterable[Path]:
    for child in sorted(base_directory.iterdir()):
        if child.is_directory():
            yield child


def read_display_name(metadata_path: Path) -> str | None:
    try:
        with open(metadata_path, encoding="utf-8") as f:
            data = json.load(f)
        name = data.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    except Exception:
        return None
    return None


def find_single_species_directory(base_directory: Path, query: str) -> tuple[Path, str] | None:
    normalized_query = query.strip().casefold()
    for directory_path in iter_species_dirs(base_directory):
        display_name = read_display_name(directory_path / "metadata.json")
        if display_name and display_name.strip().casefold() == normalized_query:
            return directory_path, display_name
    for directory_path in iter_species_dirs(base_directory):
        if directory_path.name.strip().casefold() == normalized_query:
            name = read_display_name(directory_path / "metadata.json") or directory_path.name
            return directory_path, name
    return None


def sha1_digest_bytes(data: bytes) -> str:
    return hashlib.sha1(data, usedforsecurity=False).hexdigest()


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    with open(tmp, "wb") as f:
        f.write(content)
    tmp.replace(path)


def encode_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def gather_existing_hashes(*dirs: Path) -> set[str]:
    hashes: set[str] = set()
    for d in dirs:
        if not d.exists():
            continue
        for f in d.iterdir():
            if not f.is_file():
                continue
            try:
                with open(f, "rb") as fh:
                    data = fh.read()
                if data:
                    hashes.add(sha1_digest_bytes(data))
            except Exception:
                continue
    return hashes


def list_source_images(images_directory: Path) -> list[Path]:
    if not images_directory.exists():
        return []
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    files: list[Path] = []
    for f in sorted(images_directory.iterdir()):
        if f.is_file() and f.suffix.lower() in exts:
            files.append(f)
    return files


def load_image_rgb(path: Path) -> Image.Image | None:
    try:
        img = Image.open(path)
        return img.convert("RGB")
    except Exception:
        return None


def ensure_size(img: Image.Image, size: int | None) -> Image.Image:
    if not size:
        return img
    return img.resize((size, size), resample=Image.BICUBIC)


def aug_flip_horizontal(img: Image.Image) -> Image.Image:
    return ImageOps.mirror(img)


def aug_rotate(img: Image.Image, *, max_degrees: int = 25) -> Image.Image:
    angle = random.uniform(-max_degrees, max_degrees)
    return img.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor=(0, 0, 0)).resize(
        img.size, Image.BICUBIC
    )


def aug_random_crop(img: Image.Image, *, min_scale: float = 0.7) -> Image.Image:
    w, h = img.size
    scale = random.uniform(min_scale, 1.0)
    crop_w = max(1, int(w * scale))
    crop_h = max(1, int(h * scale))
    if crop_w == w and crop_h == h:
        return img
    left = random.randint(0, w - crop_w)
    top = random.randint(0, h - crop_h)
    cropped = img.crop((left, top, left + crop_w, top + crop_h))
    return cropped.resize((w, h), Image.BICUBIC)


def aug_quantize_color(img: Image.Image, *, min_bits: int = 4, max_bits: int = 7) -> Image.Image:
    bits = random.randint(min_bits, max_bits)
    levels = 2**bits
    step = 256 // levels
    arr = np.asarray(img, dtype=np.uint8)
    arr = (arr // step) * step + step // 2
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, mode="RGB")


def aug_gaussian_blur(
    img: Image.Image, *, min_sigma: float = 0.5, max_sigma: float = 1.5
) -> Image.Image:
    radius = random.uniform(min_sigma, max_sigma)
    return img.filter(ImageFilter.GaussianBlur(radius=radius))


def aug_gaussian_noise(
    img: Image.Image, *, min_std: float = 5.0, max_std: float = 20.0
) -> Image.Image:
    std = random.uniform(min_std, max_std)
    arr = np.asarray(img).astype(np.float32)
    noise = np.random.normal(0.0, std, size=arr.shape).astype(np.float32)
    out = np.clip(arr + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(out, mode="RGB")


AUGMENTATIONS: Sequence[Callable[[Image.Image], Image.Image]] = (
    aug_flip_horizontal,
    aug_rotate,
    aug_random_crop,
    aug_quantize_color,
    aug_gaussian_blur,
    aug_gaussian_noise,
)


@dataclass
class AugmentConfig:
    target_outputs: int
    output_subdir: str
    image_size: int | None
    max_ops_per_image: int
    overwrite: bool
    dry_run: bool


def augment_one(img: Image.Image, *, cfg: AugmentConfig) -> Image.Image:
    ops_count = random.randint(1, max(1, cfg.max_ops_per_image))
    ops = random.sample(AUGMENTATIONS, k=ops_count)
    out = img
    for op in ops:
        out = op(out)
    out = ensure_size(out, cfg.image_size)
    return out


def process_species(directory_path: Path, display_name: str, *, cfg: AugmentConfig) -> None:
    source_dir = directory_path / "images"
    out_directory = directory_path / cfg.output_subdir
    if cfg.overwrite and not cfg.dry_run and out_directory.exists():
        for f in out_directory.iterdir():
            try:
                if f.is_file():
                    f.unlink()
            except Exception:
                pass
    existing_hashes = gather_existing_hashes(source_dir, out_directory)
    source_files = list_source_images(source_dir)
    if not source_files:
        return
    existing_aug_count = 0
    if out_directory.exists():
        existing_aug_count = len([f for f in out_directory.iterdir() if f.is_file()])
    remaining = max(0, cfg.target_outputs - existing_aug_count)
    if remaining <= 0 and not cfg.overwrite:
        return
    added = 0
    while remaining > 0:
        source_path = random.choice(source_files)
        src_image = load_image_rgb(source_path)
        if src_image is None:
            continue
        aug_image = augment_one(src_image, cfg=cfg)
        png_bytes = encode_png_bytes(aug_image)
        digest = sha1_digest_bytes(png_bytes)
        if digest in existing_hashes:
            continue
        filename = f"{digest}.png"
        out_path = out_directory / filename
        if cfg.dry_run:
            existing_hashes.add(digest)
            remaining -= 1
            added += 1
            continue
        try:
            atomic_write(out_path, png_bytes)
            existing_hashes.add(digest)
            remaining -= 1
            added += 1
        except Exception:
            pass
    if cfg.dry_run:
        pass
    else:
        pass


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Augment Pokémon images (flip, rotate, crop, quantize, blur, noise)"
    )
    cli_utils.add_dry_run(p, help="Do not write files; only report actions")
    cli_utils.add_overwrite(p, help="Re-generate augmented images (clear output first)")
    cli_utils.add_pokemon(p, help="Only process a single Pokémon display name (e.g., 'Bulbasaur')")
    p.add_argument(
        "--num-augmented",
        type=int,
        default=150,
        help="Number of augmented images to generate per Pokémon (default: 150)",
    )
    p.add_argument(
        "--output-subdir",
        type=str,
        default="images_aug",
        help="Subdirectory under each species to store augmented images (default: images_aug)",
    )
    p.add_argument(
        "--size",
        type=int,
        default=None,
        help="Optional square output size in pixels (e.g., 224). If omitted, keep original size",
    )
    p.add_argument(
        "--max-ops",
        type=int,
        default=3,
        help="Maximum number of augmentation ops to compose per output (default: 3)",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    base = POKEMON_DATA_DIR
    if not base.exists():
        return 2
    cfg = AugmentConfig(
        target_outputs=max(1, args.number_augmented),
        output_subdir=args.output_subdir,
        image_size=args.size,
        max_ops_per_image=max(1, args.max_ops),
        overwrite=args.overwrite,
        dry_run=args.dry_run,
    )
    if args.pokemon:
        match = find_single_species_directory(base, args.pokemon)
        if not match:
            return 3
        directory_path, display_name = match
        process_species(directory_path, display_name, cfg=cfg)
        return 0
    for directory_path in iter_species_dirs(base):
        display_name = read_display_name(directory_path / "metadata.json") or directory_path.name
        with contextlib.suppress(Exception):
            process_species(directory_path, display_name, cfg=cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
