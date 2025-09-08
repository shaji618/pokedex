from __future__ import annotations

import contextlib
import os
from typing import Any


def select_torch_device() -> str:
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def configure_torch_threads() -> None:
    try:
        import torch

        torch.set_num_threads(int(os.getenv("SCANNER_TORCH_THREADS", "2")))
        torch.set_num_interop_threads(int(os.getenv("SCANNER_TORCH_INTEROP_THREADS", "1")))
    except Exception:
        pass


def load_vit_model(local_model_directory: str) -> tuple[Any, Any, str]:
    import os

    from transformers import ViTForImageClassification, ViTImageProcessor

    if not os.path.isdir(local_model_directory):
        raise FileNotFoundError(f"Model directory not found: {local_model_directory}")
    device = select_torch_device()
    configure_torch_threads()
    model = ViTForImageClassification.from_pretrained(local_model_directory)
    model.eval()
    if device == "cpu" and os.getenv("SCANNER_DISABLE_INT8", "0") != "1":
        try:
            if getattr(__import__("torch").backends, "quantized", None) is not None:
                with contextlib.suppress(Exception):
                    __import__("torch").backends.quantized.engine = "qnnpack"
            from torch.ao.quantization import quantize_dynamic

            model = quantize_dynamic(
                model, {__import__("torch").nn.Linear}, dtype=__import__("torch").qint8
            )
        except Exception:
            pass
    model.to(device)
    try:
        processor = ViTImageProcessor.from_pretrained(local_model_directory)
    except Exception:
        from transformers import ViTFeatureExtractor

        processor = ViTFeatureExtractor.from_pretrained(local_model_directory)
    return model, processor, device


def warmup_model(model: Any, device: str, image_size: int | None = None) -> None:
    try:
        import torch

        size = 224
        with contextlib.suppress(Exception):
            size = int(image_size or getattr(model.config, "image_size", size))
        dummy = torch.zeros(1, 3, size, size, device=device)
        with torch.inference_mode():
            _ = model(pixel_values=dummy)
    except Exception:
        pass


def safe_forward_logits(model: Any, inputs: dict[str, Any], device: str) -> Any:
    import torch

    with torch.inference_mode():
        try:
            return model(**inputs).logits
        except Exception:
            with contextlib.suppress(Exception):
                model.to("cpu")
            inputs = {k: v.to("cpu") if hasattr(v, "to") else v for k, v in inputs.items()}
            return model(**inputs).logits
