from __future__ import annotations

import os
import time
from importlib import resources
from pathlib import Path

import pygame
from PIL import Image

from src.utils.logger import get_logger
from src.utils.surface_util import scale_surface_to_fit


def load_image_safe(path: str | Path, *, convert_alpha: bool = True) -> pygame.Surface | None:
    logger = get_logger()
    try:
        if not path or not os.path.exists(str(path)):
            return None
        logger.debug(f"🖼️  Loading image: {Path(path).name}")
        image = pygame.image.load(str(path))
        return image.convert_alpha() if convert_alpha else image.convert()
    except Exception as error:
        logger.warning(f"🖼️  Failed to load image {Path(path).name}: {error}")
        return None


def load_image_from_resources(
    package: str, filename: str, *, convert_alpha: bool = True
) -> pygame.Surface | None:
    try:
        with resources.files(package).joinpath(filename).open("rb") as file:
            image = pygame.image.load(file, filename)
            return image.convert_alpha() if convert_alpha else image.convert()
    except Exception:
        return None


def load_and_scale_image(
    path: str | Path, target_size: tuple[int, int], *, convert_alpha: bool = True
) -> pygame.Surface | None:
    image = load_image_safe(path, convert_alpha=convert_alpha)
    if image is None:
        return None
    return scale_surface_to_fit(image, target_size)


def create_placeholder_image(
    size: tuple[int, int],
    *,
    bg_color: tuple[int, int, int] = (80, 80, 90),
    border_color: tuple[int, int, int] = (120, 120, 130),
) -> pygame.Surface:
    width, height = size
    surface = pygame.Surface((width, height), pygame.SRCALPHA)
    surface.fill(bg_color)
    pygame.draw.rect(surface, border_color, surface.get_rect(), width=2)
    font_size = min(width, height) // 3
    if font_size > 8:
        font = pygame.font.Font(None, font_size)
        text = font.render("?", True, border_color)
        text_rect = text.get_rect(center=(width // 2, height // 2))
        surface.blit(text, text_rect)
    return surface


class ImageCache:
    def __init__(self, max_size: int = 100) -> None:
        self._cache: dict[str, pygame.Surface] = {}
        self._max_size = max_size

    def get(self, path: str | Path, *, convert_alpha: bool = True) -> pygame.Surface | None:
        key = str(path)
        if key in self._cache:
            return self._cache[key]
        img = load_image_safe(path, convert_alpha=convert_alpha)
        if img is not None:
            if len(self._cache) >= self._max_size:
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
            self._cache[key] = img
        return img

    def clear(self) -> None:
        self._cache.clear()

    def size(self) -> int:
        return len(self._cache)


_global_cache = ImageCache()


def get_cached_image(path: str | Path, *, convert_alpha: bool = True) -> pygame.Surface | None:
    return _global_cache.get(path, convert_alpha=convert_alpha)


def clear_image_cache() -> None:
    _global_cache.clear()


class AnimatedGif:
    """Manages animated GIF playback with automatic frame cycling."""
    
    def __init__(self, frames: list[pygame.Surface], durations: list[float]):
        """Initialize with frames and their durations in seconds."""
        self.frames = frames
        self.durations = durations  # Duration in seconds for each frame
        self.start_time = time.time()
        
    def get_current_frame(self) -> pygame.Surface:
        """Get the current frame based on elapsed time."""
        if not self.frames:
            return self.frames[0] if self.frames else None
            
        elapsed = time.time() - self.start_time
        
        # Calculate total animation duration
        total_duration = sum(self.durations)
        if total_duration <= 0:
            return self.frames[0]
            
        # Find current frame based on elapsed time (loop)
        time_in_cycle = elapsed % total_duration
        cumulative_time = 0
        
        for i, duration in enumerate(self.durations):
            cumulative_time += duration
            if time_in_cycle <= cumulative_time:
                return self.frames[i]
                
        # Fallback to first frame
        return self.frames[0]
        
    def reset(self):
        """Reset animation to start from beginning."""
        self.start_time = time.time()
        
    def get_frame_count(self) -> int:
        """Get the number of frames in the animation."""
        return len(self.frames)


def load_animated_gif(file_path: str | Path) -> AnimatedGif | pygame.Surface | None:
    """
    Load a GIF file. Returns AnimatedGif for animated GIFs, 
    pygame.Surface for static images, or None on error.
    """
    try:
        with Image.open(str(file_path)) as img:
            if not getattr(img, 'is_animated', False):
                # Not an animated GIF, load as single static surface
                frame = img.convert('RGBA')
                pygame_surface = pygame.image.frombuffer(
                    frame.tobytes(), frame.size, 'RGBA'
                ).convert_alpha()
                return pygame_surface
                
            frames = []
            durations = []
            
            # Extract all frames
            for frame_index in range(img.n_frames):
                img.seek(frame_index)
                
                # Get frame duration (in milliseconds, convert to seconds)
                duration = img.info.get('duration', 100) / 1000.0  # Default 100ms
                if duration <= 0:
                    duration = 0.1  # Minimum 100ms
                    
                # Convert PIL image to pygame surface
                frame = img.convert('RGBA')
                pygame_surface = pygame.image.frombuffer(
                    frame.tobytes(), frame.size, 'RGBA'
                ).convert_alpha()
                
                frames.append(pygame_surface)
                durations.append(duration)
                
            return AnimatedGif(frames, durations)
            
    except Exception as e:
        logger = get_logger()
        logger.warning(f"Failed to load GIF {Path(file_path).name}: {e}")
        return None


def is_animated_gif_path(file_path: str | Path) -> bool:
    """Check if a file path points to an animated GIF."""
    try:
        with Image.open(str(file_path)) as img:
            return getattr(img, 'is_animated', False)
    except Exception:
        return False
