from __future__ import annotations

import contextlib

import pygame


def scale_surface_to_fit(surface: pygame.Surface, box_size: tuple[int, int]) -> pygame.Surface:
    box_width, box_height = box_size
    image_width, image_height = surface.get_size()
    if image_width == 0 or image_height == 0:
        return surface
    scale = min(box_width / image_width, box_height / image_height)
    new_size = (max(1, int(image_width * scale)), max(1, int(image_height * scale)))
    return pygame.transform.smoothscale(surface, new_size)


def grayscale_surface(surface: pygame.Surface) -> pygame.Surface:
    try:
        import numpy as np

        source = surface.convert_alpha()
        width, height = source.get_size()
        destination = pygame.Surface((width, height), flags=pygame.SRCALPHA).convert_alpha()
        rgb_array = pygame.surfarray.array3d(source)
        alpha_array = None
        with contextlib.suppress(Exception):
            alpha_array = pygame.surfarray.array_alpha(source)
        luminance = (
            0.2126 * rgb_array[:, :, 0] + 0.7152 * rgb_array[:, :, 1] + 0.0722 * rgb_array[:, :, 2]
        ).astype("uint8")
        gray_rgb_array = np.dstack((luminance, luminance, luminance))
        pygame.surfarray.blit_array(destination, gray_rgb_array)
        if alpha_array is not None:
            pixel_alpha = pygame.surfarray.pixels_alpha(destination)
            pixel_alpha[:, :] = alpha_array
            del pixel_alpha
        return destination
    except Exception:
        approx = surface.copy().convert_alpha()
        approx.fill((160, 160, 160, 255), special_flags=pygame.BLEND_RGBA_MULT)
        return approx
