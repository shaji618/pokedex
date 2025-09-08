from enum import Enum


class PokemonType(str, Enum):
    NORMAL = "normal"
    FIRE = "fire"
    WATER = "water"
    ELECTRIC = "electric"
    GRASS = "grass"
    ICE = "ice"
    FIGHTING = "fighting"
    POISON = "poison"
    GROUND = "ground"
    FLYING = "flying"
    PSYCHIC = "psychic"
    BUG = "bug"
    ROCK = "rock"
    GHOST = "ghost"
    DRAGON = "dragon"
    DARK = "dark"
    STEEL = "steel"
    FAIRY = "fairy"


class PokemonVariant(str, Enum):
    SHINY = "shiny"
    MEGA = "mega"
    MEGAX = "megax"
    MEGAY = "megay"
    GIGANTAMAX = "gigantamax"
    PRIMAL = "primal"
    ALOLAN = "alolan"
    GALARIAN = "galarian"
    HISUIAN = "hisuian"
    PALDEAN = "paldean"
    FEMALE = "female"
    MALE = "male"
    SHADOW = "shadow"
    PURIFIED = "purified"


def is_valid_variant(variant_name: str) -> bool:
    try:
        PokemonVariant(variant_name.lower())
        return True
    except ValueError:
        return False


def normalize_variant(variant_name: str) -> str:
    normalized = variant_name.strip().lower()
    if not is_valid_variant(normalized):
        raise ValueError(f"Invalid Pokemon variant: {variant_name}")
    return normalized


def normalize_variants(variants: list[str]) -> list[str]:
    if not variants:
        return []
    normalized = []
    for variant_name in variants:
        normalized.append(normalize_variant(variant_name))
    return sorted(set(normalized))


def get_all_variants() -> list[str]:
    return sorted([variant.value for variant in PokemonVariant])


def is_valid_type(type_name: str) -> bool:
    try:
        PokemonType(type_name.lower())
        return True
    except ValueError:
        return False


def normalize_type(type_name: str) -> str:
    normalized = type_name.strip().lower()
    if not is_valid_type(normalized):
        raise ValueError(f"Invalid Pokemon type: {type_name}")
    return normalized


def normalize_types(types: list[str]) -> list[str]:
    if not types:
        return []
    normalized = []
    for type_name in types:
        normalized.append(normalize_type(type_name))
    return sorted(set(normalized))


def get_all_types() -> list[str]:
    return sorted([ptype.value for ptype in PokemonType])


TYPE_STRONG_AGAINST = {
    PokemonType.BUG: {PokemonType.GRASS, PokemonType.PSYCHIC, PokemonType.DARK},
    PokemonType.DARK: {PokemonType.GHOST, PokemonType.PSYCHIC},
    PokemonType.DRAGON: {PokemonType.DRAGON},
    PokemonType.ELECTRIC: {PokemonType.WATER, PokemonType.FLYING},
    PokemonType.FAIRY: {PokemonType.FIGHTING, PokemonType.DRAGON, PokemonType.DARK},
    PokemonType.FIGHTING: {
        PokemonType.NORMAL,
        PokemonType.ICE,
        PokemonType.ROCK,
        PokemonType.DARK,
        PokemonType.STEEL,
    },
    PokemonType.FIRE: {PokemonType.GRASS, PokemonType.ICE, PokemonType.BUG, PokemonType.STEEL},
    PokemonType.FLYING: {PokemonType.GRASS, PokemonType.FIGHTING, PokemonType.BUG},
    PokemonType.GHOST: {PokemonType.GHOST, PokemonType.PSYCHIC},
    PokemonType.GRASS: {PokemonType.WATER, PokemonType.GROUND, PokemonType.ROCK},
    PokemonType.GROUND: {
        PokemonType.FIRE,
        PokemonType.ELECTRIC,
        PokemonType.POISON,
        PokemonType.ROCK,
        PokemonType.STEEL,
    },
    PokemonType.ICE: {
        PokemonType.GRASS,
        PokemonType.GROUND,
        PokemonType.FLYING,
        PokemonType.DRAGON,
    },
    PokemonType.NORMAL: set(),
    PokemonType.POISON: {PokemonType.GRASS, PokemonType.FAIRY},
    PokemonType.PSYCHIC: {PokemonType.FIGHTING, PokemonType.POISON},
    PokemonType.ROCK: {PokemonType.FIRE, PokemonType.ICE, PokemonType.FLYING, PokemonType.BUG},
    PokemonType.STEEL: {PokemonType.ICE, PokemonType.ROCK, PokemonType.FAIRY},
    PokemonType.WATER: {PokemonType.FIRE, PokemonType.GROUND, PokemonType.ROCK},
}
TYPE_WEAK_TO = {
    PokemonType.BUG: {PokemonType.FIRE, PokemonType.FLYING, PokemonType.ROCK},
    PokemonType.DARK: {PokemonType.FIGHTING, PokemonType.BUG, PokemonType.FAIRY},
    PokemonType.DRAGON: {PokemonType.ICE, PokemonType.DRAGON, PokemonType.FAIRY},
    PokemonType.ELECTRIC: {PokemonType.GROUND},
    PokemonType.FAIRY: {PokemonType.POISON, PokemonType.STEEL},
    PokemonType.FIGHTING: {PokemonType.FLYING, PokemonType.PSYCHIC, PokemonType.FAIRY},
    PokemonType.FIRE: {PokemonType.WATER, PokemonType.GROUND, PokemonType.ROCK},
    PokemonType.FLYING: {PokemonType.ELECTRIC, PokemonType.ICE, PokemonType.ROCK},
    PokemonType.GHOST: {PokemonType.GHOST, PokemonType.DARK},
    PokemonType.GRASS: {
        PokemonType.FIRE,
        PokemonType.ICE,
        PokemonType.POISON,
        PokemonType.FLYING,
        PokemonType.BUG,
    },
    PokemonType.GROUND: {PokemonType.WATER, PokemonType.GRASS, PokemonType.ICE},
    PokemonType.ICE: {PokemonType.FIRE, PokemonType.FIGHTING, PokemonType.ROCK, PokemonType.STEEL},
    PokemonType.NORMAL: {PokemonType.FIGHTING},
    PokemonType.POISON: {PokemonType.GROUND, PokemonType.PSYCHIC},
    PokemonType.PSYCHIC: {PokemonType.BUG, PokemonType.GHOST, PokemonType.DARK},
    PokemonType.ROCK: {
        PokemonType.WATER,
        PokemonType.GRASS,
        PokemonType.FIGHTING,
        PokemonType.GROUND,
        PokemonType.STEEL,
    },
    PokemonType.STEEL: {PokemonType.FIRE, PokemonType.FIGHTING, PokemonType.GROUND},
    PokemonType.WATER: {PokemonType.ELECTRIC, PokemonType.GRASS},
}


def is_type_strong_against(attacker_type: str, defender_type: str) -> bool:
    try:
        attacker_enum = PokemonType(normalize_type(attacker_type))
        defender_enum = PokemonType(normalize_type(defender_type))
        return defender_enum in TYPE_STRONG_AGAINST.get(attacker_enum, set())
    except ValueError:
        return False


def is_type_weak_to(defender_type: str, attacker_type: str) -> bool:
    try:
        defender_enum = PokemonType(normalize_type(defender_type))
        attacker_enum = PokemonType(normalize_type(attacker_type))
        return attacker_enum in TYPE_WEAK_TO.get(defender_enum, set())
    except ValueError:
        return False
