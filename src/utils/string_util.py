from __future__ import annotations

import pygame


def to_roman(number: int) -> str:
    try:
        value = int(number)
    except Exception:
        return str(number)
    if value <= 0:
        return str(value)
    numerals = [
        (1000, "M"),
        (900, "CM"),
        (500, "D"),
        (400, "CD"),
        (100, "C"),
        (90, "XC"),
        (50, "L"),
        (40, "XL"),
        (10, "X"),
        (9, "IX"),
        (5, "V"),
        (4, "IV"),
        (1, "I"),
    ]
    result: list[str] = []
    remaining = value
    for arabic, roman in numerals:
        if remaining == 0:
            break
        count, remaining = divmod(remaining, arabic)
        if count:
            result.append(roman * count)
    return "".join(result)


def wrap_text(font: pygame.font.Font, text: str, maximum_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        trial = (" ".join([*current, word])).strip()
        width, _ = font.size(trial)
        if width <= maximum_width or not current:
            current.append(word)
        else:
            lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines
