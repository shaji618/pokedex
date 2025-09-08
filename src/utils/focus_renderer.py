from __future__ import annotations

import pygame

from src.utils.ui_constants import FOCUS_BORDER


class FocusRenderer:
    def __init__(
        self,
        color: tuple[int, int, int] = FOCUS_BORDER,
        thickness: int = 3,
        corner_size_factor: float = 0.15,
        padding: int = 26,
    ) -> None:
        self.color = color
        self.thickness = thickness
        self.corner_size_factor = corner_size_factor
        self.padding = padding

    def draw_focus_indicator(self, screen: pygame.Surface, rect: pygame.Rect) -> None:
        focus_rect = rect.inflate(self.padding * 2, self.padding * 2)
        corner_length = max(
            8,
            min(
                int(focus_rect.width * self.corner_size_factor),
                int(focus_rect.height * self.corner_size_factor),
                20,
            ),
        )
        self._draw_corner_brackets(screen, focus_rect, corner_length)

    def _draw_corner_brackets(
        self, screen: pygame.Surface, rect: pygame.Rect, corner_length: int
    ) -> None:
        self._draw_corner(screen, rect.topleft, corner_length, "top-left")
        self._draw_corner(screen, rect.topright, corner_length, "top-right")
        self._draw_corner(screen, rect.bottomleft, corner_length, "bottom-left")
        self._draw_corner(screen, rect.bottomright, corner_length, "bottom-right")

    def _draw_corner(
        self, screen: pygame.Surface, point: tuple[int, int], length: int, corner_type: str
    ) -> None:
        x, y = point
        if corner_type == "top-left":
            pygame.draw.line(screen, self.color, (x, y), (x + length, y), self.thickness)
            pygame.draw.line(screen, self.color, (x, y), (x, y + length), self.thickness)
        elif corner_type == "top-right":
            pygame.draw.line(screen, self.color, (x, y), (x - length, y), self.thickness)
            pygame.draw.line(screen, self.color, (x, y), (x, y + length), self.thickness)
        elif corner_type == "bottom-left":
            pygame.draw.line(screen, self.color, (x, y), (x + length, y), self.thickness)
            pygame.draw.line(screen, self.color, (x, y), (x, y - length), self.thickness)
        elif corner_type == "bottom-right":
            pygame.draw.line(screen, self.color, (x, y), (x - length, y), self.thickness)
            pygame.draw.line(screen, self.color, (x, y), (x, y - length), self.thickness)


class CompactFocusRenderer(FocusRenderer):
    def __init__(self) -> None:
        super().__init__(thickness=2, corner_size_factor=0.25, padding=2)


class ProminentFocusRenderer(FocusRenderer):
    def __init__(self) -> None:
        super().__init__(thickness=4, corner_size_factor=0.12, padding=6)


def draw_focus_indicator(
    screen: pygame.Surface, rect: pygame.Rect, renderer: FocusRenderer | None = None
) -> None:
    if renderer is None:
        renderer = FocusRenderer()
    renderer.draw_focus_indicator(screen, rect)


def create_focus_overlay(
    base_surface: pygame.Surface, focused_rect: pygame.Rect, renderer: FocusRenderer | None = None
) -> pygame.Surface:
    overlay = pygame.Surface(base_surface.get_size(), pygame.SRCALPHA)
    draw_focus_indicator(overlay, focused_rect, renderer)
    return overlay


DEFAULT_FOCUS_RENDERER = FocusRenderer()
COMPACT_FOCUS_RENDERER = CompactFocusRenderer()
PROMINENT_FOCUS_RENDERER = ProminentFocusRenderer()
