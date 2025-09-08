from __future__ import annotations

from collections.abc import Iterable, Sequence

import pygame

from src.utils.pill_util import draw_pill


def filter_names_by_prefix(all_names: Sequence[str], prefix: str) -> list[str]:
    if not prefix:
        return list(all_names)
    p = prefix.lower()
    return [n for n in all_names if n.lower().startswith(p)]


def compute_next_letters(candidates: Iterable[str], prefix: str) -> list[str]:
    pos = len(prefix)
    next_letters: set[str] = set()
    p = prefix.lower()
    for name in candidates:
        s = name.lower()
        if not s.startswith(p):
            continue
        if len(s) > pos:
            next_letters.add(s[pos].upper())
    return sorted(next_letters)


def draw_letter_strip(
    screen: pygame.Surface,
    rect: pygame.Rect,
    letters: Sequence[str],
    prefix: str,
) -> list[tuple[str, pygame.Rect]]:
    pygame.draw.rect(screen, (35, 35, 40), rect, border_radius=8)
    pygame.draw.rect(screen, (80, 160, 240), rect, width=2, border_radius=8)
    hits: list[tuple[str, pygame.Rect]] = []
    clear_width = 0
    clear_rect: pygame.Rect | None = None
    pad_x = 12
    pad_y = 6
    if prefix:
        pill_h = 28
        pill_font = pygame.font.Font(None, 22)
        text_w, _ = pill_font.size("CLEAR")
        pill_pad_x = 12
        pill_w = text_w + pill_pad_x * 2
        clear_width = pill_w + pad_x
        clear_rect = pygame.Rect(
            rect.right - pad_x - pill_w, rect.centery - pill_h // 2, pill_w, pill_h
        )
    avail_w = rect.width - (pad_x * 2) - clear_width
    avail_h = rect.height - pad_y * 2
    font_size = min(32, max(16, int(avail_h * 0.8)))
    font = pygame.font.Font(None, font_size)
    spacing = max(8, int(font_size * 0.4))
    total_letters_w = 0
    widths: list[int] = []
    for ch in letters:
        w, _ = font.size(ch)
        widths.append(w)
        total_letters_w += w
    if letters:
        total_letters_w += spacing * (len(letters) - 1)
    while letters and total_letters_w > avail_w and font_size > 14:
        font_size -= 1
        font = pygame.font.Font(None, font_size)
        spacing = max(6, int(font_size * 0.35))
        total_letters_w = 0
        widths = []
        for ch in letters:
            w, _ = font.size(ch)
            widths.append(w)
            total_letters_w += w
        total_letters_w += spacing * (len(letters) - 1)
    x = rect.left + pad_x + max(0, (avail_w - total_letters_w) // 2)
    y_center = rect.centery
    text_color = (235, 235, 245)
    for ch, w in zip(letters, widths, strict=False):
        surf = font.render(ch, True, text_color)
        letter_rect = surf.get_rect()
        letter_rect.center = (x + w // 2, y_center)
        screen.blit(surf, letter_rect)
        hit_rect = pygame.Rect(letter_rect.left - 6, rect.top, letter_rect.width + 12, rect.height)
        hits.append((ch, hit_rect))
        x += w + spacing
    if prefix and clear_rect is not None:
        top_c = (200, 80, 80)
        bot_c = (160, 40, 40)
        pill_font = pygame.font.Font(None, 22)
        draw_pill(screen, clear_rect, top_c, bot_c, "CLEAR", pill_font)
        hits.append(("CLEAR", clear_rect))
    return hits
