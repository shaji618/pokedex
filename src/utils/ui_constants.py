from __future__ import annotations

from typing import ClassVar


Color = tuple[int, int, int]
DARK_BG: Color = (18, 18, 22)
DARKER_BG: Color = (16, 16, 22)
CARD_BG: Color = (245, 246, 250)
TILE_BG: Color = (30, 30, 34)
INPUT_BG: Color = (35, 35, 40)
LIGHT_TEXT: Color = (235, 235, 245)
DARK_TEXT: Color = (20, 20, 30)
MUTED_TEXT: Color = (150, 150, 160)
HINT_TEXT: Color = (180, 180, 190)
LABEL_TEXT: Color = (170, 200, 255)
BLUE_ACCENT: Color = (80, 160, 240)
BLUE_BORDER: Color = (40, 90, 180)
GREEN_ACCENT: Color = (120, 200, 120)
RED_ACCENT: Color = (227, 53, 13)
POKEMON_YELLOW: Color = (255, 203, 5)
LIGHT_BORDER: Color = (60, 60, 68)
MEDIUM_BORDER: Color = (190, 192, 200)
FOCUS_BORDER: Color = BLUE_ACCENT


class Theme:
    DARK_BACKGROUND = DARK_BG
    DARK_TEXT_ON_DARK = LIGHT_TEXT
    DARK_MUTED_TEXT = MUTED_TEXT
    DARK_ACCENT = BLUE_ACCENT
    LIGHT_BACKGROUND = CARD_BG
    LIGHT_TEXT_ON_LIGHT = DARK_TEXT
    LIGHT_BORDER = LIGHT_BORDER
    BUTTON_PRIMARY = BLUE_ACCENT
    BUTTON_SUCCESS = GREEN_ACCENT
    BUTTON_WARNING = RED_ACCENT
    TILE: ClassVar[dict[str, tuple[int, int, int]]] = {
        "bg": TILE_BG,
        "border": LIGHT_BORDER,
        "text": LIGHT_TEXT,
    }
    INPUT: ClassVar[dict[str, tuple[int, int, int]]] = {
        "bg": INPUT_BG,
        "border": LIGHT_BORDER,
        "focus_border": FOCUS_BORDER,
        "text": LIGHT_TEXT,
    }
    MODAL: ClassVar[dict[str, tuple[int, int, int]]] = {
        "bg": CARD_BG,
        "border": BLUE_BORDER,
        "text": DARK_TEXT,
    }


class Spacing:
    XS = 4
    SM = 8
    MD = 16
    LG = 24
    XL = 32
    CARD_PADDING = MD
    TILE_PADDING = SM
    BUTTON_PADDING = 12
    ELEMENT_MARGIN = SM
    SECTION_MARGIN = LG


class Size:
    BORDER_RADIUS_SM = 8
    BORDER_RADIUS_MD = 12
    BORDER_RADIUS_LG = 20
    BUTTON_HEIGHT_SM = 32
    BUTTON_HEIGHT_MD = 40
    BUTTON_HEIGHT_LG = 50
    INPUT_HEIGHT = 50
    ICON_SM = 16
    ICON_MD = 24
    ICON_LG = 32
