from __future__ import annotations

import random
from pathlib import Path

import pygame

from src.utils.path_util import project_root


def images_root() -> Path:
    return project_root() / "pokemon_data"


def index_images(root: str | Path | None = None) -> list[tuple[str, str]]:
    base = Path(root) if root else images_root()
    entries: list[tuple[str, str]] = []
    if not base.is_dir():
        return entries
    for species_directory in sorted(p for p in base.iterdir() if p.is_dir()):
        species = species_directory.name
        main_png = species_directory / "main.png"
        if main_png.exists():
            entries.append((species, str(main_png)))
            continue
        preferred = species_directory / f"{species}.png"
        if preferred.exists():
            entries.append((species, str(preferred)))
            continue
        found = None
        for f in sorted(species_directory.iterdir()):
            if f.suffix.lower() == ".png":
                found = f
                break
        if found:
            entries.append((species, str(found)))
    return entries


def list_species_pngs(root: str | Path | None = None) -> dict[str, str]:
    return dict(index_images(root))


def random_image(root: str | Path | None = None) -> tuple[str, str] | None:
    entries = index_images(root)
    if not entries:
        return None
    return random.choice(entries)


def random_images(n: int, root: str | Path | None = None) -> list[tuple[str, str]]:
    entries = index_images(root)
    if not entries:
        return []
    if n >= len(entries):
        random.shuffle(entries)
        return entries
    return random.sample(entries, n)


def make_silhouette(surface: pygame.Surface) -> pygame.Surface:
    silhouette = surface.copy().convert_alpha()
    silhouette.fill((0, 0, 0, 255), special_flags=pygame.BLEND_RGBA_MULT)
    return silhouette
