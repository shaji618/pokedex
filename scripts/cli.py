import argparse
import json
import time
from pathlib import Path

import requests


def add_overwrite(
    parser: argparse.ArgumentParser, *, help: str | None = None
) -> argparse.ArgumentParser:
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help=help or "Overwrite existing files even if unchanged",
    )
    return parser


def add_dry_run(
    parser: argparse.ArgumentParser, *, help: str | None = None
) -> argparse.ArgumentParser:
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=help or "Do not write files; only report actions",
    )
    return parser


def add_pokemon(
    parser: argparse.ArgumentParser, *, help: str | None = None
) -> argparse.ArgumentParser:
    parser.add_argument(
        "--pokemon",
        type=str,
        default=None,
        help=help or "Single Pokémon display name from metadata.json",
    )
    return parser


def add_debug(
    parser: argparse.ArgumentParser, *, help: str | None = None
) -> argparse.ArgumentParser:
    parser.add_argument(
        "--debug",
        action="store_true",
        help=help or "Write debug artifacts for troubleshooting",
    )
    return parser


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def pokemon_data_root() -> Path:
    return project_root() / "pokemon_data"


def polite_sleep(seconds: float = 0.3) -> None:
    time.sleep(seconds)


def atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
    tmp.replace(path)


def create_session(user_agent: str | None = None) -> requests.Session:
    session = requests.Session()
    default_headers = {
        "User-Agent": user_agent
        or (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    session.headers.update(default_headers)
    return session


VALID_POKEMON_TYPES = {
    "normal",
    "fire",
    "water",
    "electric",
    "grass",
    "ice",
    "fighting",
    "poison",
    "ground",
    "flying",
    "psychic",
    "bug",
    "rock",
    "ghost",
    "dragon",
    "dark",
    "steel",
    "fairy",
}


def is_valid_type(type_name: str) -> bool:
    return type_name.lower().strip() in VALID_POKEMON_TYPES


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
        if type_name.strip():
            try:
                normalized.append(normalize_type(type_name))
            except ValueError:
                continue
    return sorted(set(normalized))


def get_all_types() -> list[str]:
    return sorted(VALID_POKEMON_TYPES)


def to_roman(n: int) -> str:
    try:
        value = int(n)
    except Exception:
        return str(n)
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
    result = []
    remaining = value
    for arabic, roman in numerals:
        if remaining == 0:
            break
        count, remaining = divmod(remaining, arabic)
        if count:
            result.append(roman * count)
    return "".join(result)


def find_pokemon_directory(query: str, root: Path | None = None) -> Path | None:
    try:
        from validation_utils import find_pokemon_directory_robust

        return find_pokemon_directory_robust(query, root, verbose=False)
    except ImportError:
        from scripts.validation_utils import find_pokemon_directory_robust

        return find_pokemon_directory_robust(query, root, verbose=False)


def filter_pokemon_directories(query: str | None = None, root: Path | None = None) -> list[Path]:
    if root is None:
        root = pokemon_data_root()
    if not root.exists():
        return []
    if query is None:
        return [d for d in sorted(root.iterdir()) if d.is_dir() and not d.name.startswith(".")]
    found = find_pokemon_directory(query, root)
    return [found] if found else []


def load_pokemon_metadata(directory: Path) -> dict:
    metadata_path = directory / "metadata.json"
    if not metadata_path.exists():
        return {}
    try:
        with open(metadata_path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}
