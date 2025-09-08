from __future__ import annotations

from src.utils.pokemon_types import PokemonType, PokemonVariant


GEN_COLOR_MAP: dict[int, tuple[int, int, int]] = {
    1: (0x80, 0xBB, 0x1D),
    2: (0xCA, 0xC0, 0x2E),
    3: (0x67, 0xC1, 0xAB),
    4: (0x90, 0x72, 0xA3),
    5: (0x6B, 0xAE, 0xCE),
    6: (0xCB, 0x0B, 0x4F),
    7: (0xDC, 0x5A, 0x40),
    8: (0xAC, 0x37, 0x9E),
    9: (0xE1, 0x9F, 0x3E),
}
TYPE_COLOR_MAP: dict[PokemonType, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
    PokemonType.NORMAL: ((0xA4, 0xAC, 0xAF), (0xA4, 0xAC, 0xAF)),
    PokemonType.FIRE: ((0xFD, 0x7D, 0x24), (0xFD, 0x7D, 0x24)),
    PokemonType.WATER: ((0x45, 0x92, 0xC4), (0x45, 0x92, 0xC4)),
    PokemonType.GRASS: ((0x9B, 0xCC, 0x50), (0x9B, 0xCC, 0x50)),
    PokemonType.FLYING: ((0x3D, 0xC7, 0xEF), (0xBD, 0xB9, 0xB8)),
    PokemonType.FIGHTING: ((0xD5, 0x67, 0x23), (0xD5, 0x67, 0x23)),
    PokemonType.POISON: ((0xB9, 0x7F, 0xC9), (0xB9, 0x7F, 0xC9)),
    PokemonType.ELECTRIC: ((0xEE, 0xD5, 0x35), (0xEE, 0xD5, 0x35)),
    PokemonType.GROUND: ((0xF7, 0xDE, 0x3F), (0xAB, 0x98, 0x42)),
    PokemonType.ROCK: ((0xA3, 0x8C, 0x21), (0xA3, 0x8C, 0x21)),
    PokemonType.PSYCHIC: ((0xF3, 0x66, 0xB9), (0xF3, 0x66, 0xB9)),
    PokemonType.ICE: ((0x51, 0xC4, 0xE7), (0x51, 0xC4, 0xE7)),
    PokemonType.BUG: ((0x72, 0x9F, 0x3F), (0x72, 0x9F, 0x3F)),
    PokemonType.GHOST: ((0x7B, 0x62, 0xA3), (0x7B, 0x62, 0xA3)),
    PokemonType.STEEL: ((0x9E, 0xB7, 0xB8), (0x9E, 0xB7, 0xB8)),
    PokemonType.DRAGON: ((0x53, 0xA4, 0xCF), (0xF1, 0x6E, 0x57)),
    PokemonType.DARK: ((0x70, 0x70, 0x70), (0x70, 0x70, 0x70)),
    PokemonType.FAIRY: ((0xFD, 0xB9, 0xE9), (0xFD, 0xB9, 0xE9)),
}

# Pokemon variant colors for pills/badges (top_color, bottom_color)
VARIANT_COLOR_MAP: dict[PokemonVariant, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
    PokemonVariant.SHINY: ((255, 215, 0), (255, 165, 0)),  # Gold
    PokemonVariant.MEGA: ((138, 43, 226), (75, 0, 130)),  # Purple
    PokemonVariant.MEGAX: ((138, 43, 226), (75, 0, 130)),  # Purple
    PokemonVariant.MEGAY: ((138, 43, 226), (75, 0, 130)),  # Purple
    PokemonVariant.GIGANTAMAX: ((255, 20, 147), (199, 21, 133)),  # Hot pink
    PokemonVariant.PRIMAL: ((255, 69, 0), (139, 69, 19)),  # Red-orange
    PokemonVariant.ALOLAN: ((70, 130, 180), (25, 25, 112)),  # Steel blue
    PokemonVariant.GALARIAN: ((105, 105, 105), (47, 79, 79)),  # Gray
    PokemonVariant.HISUIAN: ((210, 180, 140), (160, 82, 45)),  # Tan/brown
    PokemonVariant.PALDEAN: ((255, 140, 0), (255, 69, 0)),  # Orange
    PokemonVariant.FEMALE: ((255, 192, 203), (255, 20, 147)),  # Pink
    PokemonVariant.MALE: ((173, 216, 230), (30, 144, 255)),  # Light blue
    PokemonVariant.SHADOW: ((72, 61, 139), (25, 25, 112)),  # Dark slate blue
    PokemonVariant.PURIFIED: ((255, 255, 255), (220, 220, 220)),  # White
}


def darken_color(color: tuple[int, int, int], factor: float = 0.7) -> tuple[int, int, int]:
    """Darken a color by the given factor."""
    return (int(color[0] * factor), int(color[1] * factor), int(color[2] * factor))


def get_text_color(background_color: tuple[int, int, int]) -> tuple[int, int, int]:
    """Get appropriate text color (white/black) for background color."""
    luminance = (0.2126 * background_color[0] + 0.7152 * background_color[1] + 0.0722 * background_color[2]) / 255.0
    return (255, 255, 255) if luminance < 0.56 else (20, 22, 24)
