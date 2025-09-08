import contextlib
import os
from pathlib import Path

import pygame


class FontConfig:
    def __init__(self) -> None:
        self.font_path = "fonts/dejavu-fonts-ttf-2.37/ttf/DejaVuSans.ttf"
        self.scale_factor = 0.82
        self.fallback_fonts = ["fonts/dejavu-fonts-ttf-2.37/ttf/DejaVuSans-Bold.ttf"]


_font_config = FontConfig()
_font_cache: dict[tuple[str | None, int], pygame.font.Font] = {}
_original_pygame_font = pygame.font.Font


def _get_unicode_font_path() -> str:
    src_dir = Path(__file__).parent.parent
    font_path = src_dir / _font_config.font_path
    return str(font_path)


def _get_fallback_font_paths() -> list[str]:
    src_dir = Path(__file__).parent.parent
    return [str(src_dir / fallback_path) for fallback_path in _font_config.fallback_fonts]


def _scale_font_size(requested_size: int) -> int:
    return max(8, int(requested_size * _font_config.scale_factor))


def _unicode_font_replacement(font_file: str | None, size: int) -> pygame.font.Font:
    cache_key = (font_file, size)
    if cache_key in _font_cache:
        return _font_cache[cache_key]
    if font_file is None:
        scaled_size = _scale_font_size(size)
        unicode_path = _get_unicode_font_path()
        font = None
        if os.path.exists(unicode_path):
            with contextlib.suppress(Exception):
                font = _original_pygame_font(unicode_path, scaled_size)
        if font is None:
            for fallback_path in _get_fallback_font_paths():
                if os.path.exists(fallback_path):
                    try:
                        font = _original_pygame_font(fallback_path, scaled_size)
                        break
                    except Exception:
                        continue
        if font is None:
            font = _original_pygame_font(None, size)
    else:
        try:
            font = _original_pygame_font(font_file, size)
        except Exception:
            font = _original_pygame_font(None, size)
    _font_cache[cache_key] = font
    return font


pygame.font.Font = _unicode_font_replacement
