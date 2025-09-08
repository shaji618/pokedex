from __future__ import annotations

import pygame


def draw_pill(
    screen: pygame.Surface,
    rect: pygame.Rect,
    top_color: tuple[int, int, int],
    bottom_color: tuple[int, int, int],
    label_text: str,
    font: pygame.font.Font,
) -> None:
    radius = max(6, rect.height // 4)
    pygame.draw.rect(screen, bottom_color, rect, border_radius=radius)
    layer = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    pygame.draw.rect(layer, top_color, layer.get_rect(), border_radius=radius)
    screen.blit(layer, rect.topleft, area=pygame.Rect(0, 0, rect.width, rect.height // 2))
    border_color = (
        max(0, ((top_color[0] + bottom_color[0]) // 2) - 30),
        max(0, ((top_color[1] + bottom_color[1]) // 2) - 30),
        max(0, ((top_color[2] + bottom_color[2]) // 2) - 30),
    )
    pygame.draw.rect(screen, border_color, rect, width=2, border_radius=radius)
    surface = font.render(label_text, True, (255, 255, 255))
    screen.blit(surface, surface.get_rect(center=rect.center))


def draw_pill_list(
    screen: pygame.Surface,
    start_x: int,
    start_y: int,
    max_width: int,
    labels: list[str],
    font: pygame.font.Font,
    color_lookup: dict,
    pill_height: int = 28,
    gap_x: int = 8,
    gap_y: int = 8,
    pad_x: int = 12,
) -> int:
    x = start_x
    y = start_y
    for label in labels:
        top_color, bottom_color = color_lookup.get(
            label.lower(), ((180, 180, 180), (180, 180, 180))
        )
        text_surf = font.render(label, True, (0, 0, 0))
        pill_width = text_surf.get_width() + pad_x * 2
        if x + pill_width > start_x + max_width and x > start_x:
            x = start_x
            y += pill_height + gap_y
        rect = pygame.Rect(x, y, pill_width, pill_height)
        draw_pill(screen, rect, top_color, bottom_color, label.upper(), font)
        x += pill_width + gap_x
    return y + pill_height
