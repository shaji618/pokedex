from __future__ import annotations

import argparse
from collections.abc import Iterable, Sequence
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from transformers import AutoImageProcessor, AutoModelForImageClassification


def list_image_files(target: Path, *, recursive: bool = False) -> list[Path]:
    exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    files: list[Path] = []
    if target.is_file():
        return [target] if target.suffix.lower() in exts else []
    if target.is_directory():
        if recursive:
            for f in target.rglob("*"):
                if f.is_file() and f.suffix.lower() in exts:
                    files.append(f)
        else:
            for f in target.iterdir():
                if f.is_file() and f.suffix.lower() in exts:
                    files.append(f)
    return sorted(files)


def load_image_rgb(path: Path) -> Image.Image:
    try:
        return Image.open(path).convert("RGB")
    except Exception:
        return Image.new("RGB", (224, 224), (0, 0, 0))


def batched(iterable: Sequence[Path], n: int) -> Iterable[list[Path]]:
    for i in range(0, len(iterable), n):
        yield list(iterable[i : i + n])


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Run inference with a fine-tuned ViT Pokémon classifier"
    )
    p.add_argument(
        "--model-dir", type=str, default="pokemon_classifier", help="Path to saved model directory"
    )
    p.add_argument(
        "--input", type=str, required=True, help="Path to an image file or a directory of images"
    )
    p.add_argument(
        "--recursive",
        action="store_true",
        help="Recurse into subdirectories when --input is a directory",
    )
    p.add_argument("--batch-size", type=int, default=16)
    p.add_argument("--top-k", type=int, default=5)
    p.add_argument("--json", action="store_true", help="Output JSON lines (one per image)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    model_directory = Path(args.model_directory)
    if not model_directory.exists():
        return 2
    input_path = Path(args.input)
    files = list_image_files(input_path, recursive=args.recursive)
    if not files:
        return 3
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    processor = AutoImageProcessor.from_pretrained(model_directory)
    model = AutoModelForImageClassification.from_pretrained(model_directory).to(device)
    model.eval()
    top_k = max(1, args.top_k)
    batch_size = max(1, args.batch_size)
    for batch_paths in batched(files, batch_size):
        images = [load_image_rgb(p) for p in batch_paths]
        inputs = processor(images=images, return_tensors="pt").to(device)
        with torch.no_grad():
            outputs = model(**inputs)
            logits = outputs.logits
            probs = torch.softmax(logits, dim=-1).cpu().numpy()
        id2label: dict[int, str] = {int(k): v for k, v in model.config.id2label.items()}
        for path, prob in zip(batch_paths, probs, strict=False):
            idxs = np.argsort(prob)[::-1][:top_k]
            preds = [(id2label.get(int(i), str(i)), float(prob[i])) for i in idxs]
            if args.json:
                {
                    "image": str(path),
                    "predictions": [{"label": label, "score": score} for (label, score) in preds],
                }
            else:
                for label, score in preds:
                    pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
