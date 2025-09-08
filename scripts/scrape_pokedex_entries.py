from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections.abc import Iterable
from pathlib import Path

import cli
import requests
from bs4 import BeautifulSoup


try:
    from script_logger import get_script_logger
    from validation_utils import (
        add_validation_args,
        has_complete_sentence,
        should_proceed_after_validation_failure,
    )
except ImportError:
    from scripts.script_logger import get_script_logger
    from scripts.validation_utils import (
        add_validation_args,
        has_complete_sentence,
        should_proceed_after_validation_failure,
    )
BASE_SPECIES_URL = "https://pokemondb.net/pokedex"
QUOTE_MAP = str.maketrans(
    {
        "\u2019": "'",
        "\u2018": "'",
        "`": "'",
        "\u201c": '"',
        "\u201d": '"',
    }
)


def normalize_quotes(s: str) -> str:
    return s.translate(QUOTE_MAP)


def canonical_key(s: str) -> str:
    t = normalize_quotes(" ".join((s or "").split())).casefold()
    t = unicodedata.normalize("NFKD", t)
    t = t.encode("ascii", "ignore").decode("ascii")
    return t


def find_repo_root(start: Path) -> Path:
    return start.resolve().parents[1]


def pokemon_data_root(repo_root: Path) -> Path:
    return repo_root / "pokemon_data"


def iter_species_dirs(pokemon_root: Path) -> Iterable[Path]:
    for child in sorted(pokemon_root.iterdir()):
        if child.is_dir() and (child / "metadata.json").exists():
            yield child


def load_metadata(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def atomic_write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
    tmp.replace(path)


def build_slug(display_name: str) -> str:
    s = display_name.strip().lower()
    s = s.replace("♀", "-f").replace("♂", "-m")
    s = s.replace("_female", "-f").replace("_male", "-m")
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii")
    s = s.replace("'", "").replace("'", "").replace("`", "")
    s = re.sub(r"[^a-z0-9-]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "unknown"


def fetch_entries_for_slug(session: requests.Session, slug: str) -> list[str]:
    url = f"{BASE_SPECIES_URL}/{slug}"
    resp = session.get(url, timeout=20)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code} for {url}")
    soup = BeautifulSoup(resp.text, "html.parser")
    entries: list[str] = []
    seen_keys: set[str] = set()
    for node in soup.select(".cell-med-text"):
        text = normalize_quotes(node.get_text(" ", strip=True))
        if not text:
            continue
        key = canonical_key(text)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        entries.append(text)
    return entries


def normalize_list(values: list[str] | None) -> list[str]:
    out: list[str] = []
    seen_keys: set[str] = set()
    if not values:
        return out
    for v in values:
        if not isinstance(v, str):
            continue
        t = normalize_quotes(" ".join(v.split()))
        if not t:
            continue
        key = canonical_key(t)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        out.append(t)
    return out


def compare_entries(
    existing: list[str] | None, fetched: list[str]
) -> tuple[bool, list[str], list[str]]:
    norm_existing = normalize_list(existing)
    norm_fetched = normalize_list(fetched)
    return norm_existing == norm_fetched, norm_existing, norm_fetched


def process_one(
    session: requests.Session, species_directory: Path, *, dry_run: bool, overwrite: bool
) -> None:
    meta_path = species_directory / "metadata.json"
    meta = load_metadata(meta_path)
    display_name = meta.get("name") or species_directory.name
    slug = build_slug(display_name)
    try:
        fetched = fetch_entries_for_slug(session, slug)
    except Exception:
        return
    if not fetched:
        return
    existing = (meta.get("pokedex_entries") or []) if isinstance(meta, dict) else []
    equal, old_norm, new_norm = compare_entries(existing, fetched)
    if equal and not overwrite:
        return
    meta["pokedex_entries"] = new_norm
    if dry_run:
        return
    atomic_write_json(meta_path, meta)
    if equal and overwrite:
        pass
    else:
        pass


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Fetch Pokédex entries from pokemondb.net into metadata.json"
    )
    cli.add_pokemon(p)
    cli.add_dry_run(p, help="Do not write files; only report diffs")
    cli.add_overwrite(p, help="Force writing even if entries are unchanged")
    add_validation_args(p)
    return p.parse_args()


def validate_before_scraping(args: argparse.Namespace) -> bool:
    logger = get_script_logger()
    if args.skip_validation:
        logger.info("⏭️  Skipping validation checks")
        return True
    logger.info("🧪 Pre-flight validation for Pokedex entries scraper...")
    logger.info("  🌐 Testing pokemondb.net availability...")
    try:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://pokemondb.net/",
            }
        )
        test_url = f"{BASE_SPECIES_URL}/pikachu"
        response = session.get(test_url, timeout=10)
        if response.status_code != 200:
            logger.info(f"  ❌ pokemondb.net returned HTTP {response.status_code}")
            return False
        if not has_complete_sentence(response.text):
            logger.info("  ❌ pokemondb.net page has no complete sentences (possible error page)")
            return False
        content = response.text.lower()
        entry_indicators = ["version", "description", "pokedex", "entry", ".cell-med-text"]
        has_entry_content = any(indicator in content for indicator in entry_indicators)
        if not has_entry_content:
            logger.info("  ❌ pokemondb.net page doesn't contain Pokedex entry indicators")
            return False
        if len(response.text) < 5000:
            logger.info(f"  ⚠️  pokemondb.net page is quite small ({len(response.text)} chars)")
        logger.info("  ✅ pokemondb.net is accessible with valid Pokemon entry content")
        logger.info("  ✅ Pre-flight validation passed")
        return True
    except Exception as e:
        logger.info(f"  ❌ Failed to access pokemondb.net: {e}")
        return False


def main() -> int:
    args = parse_args()
    if args.validation_only:
        success = validate_before_scraping(args)
        if success:
            return 0
        else:
            exit(1)
    if not validate_before_scraping(args):
        if not should_proceed_after_validation_failure(args.force):
            exit(1)
    repo_root = find_repo_root(Path(__file__))
    root = pokemon_data_root(repo_root)
    if not root.exists():
        return 1
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
            " (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://pokemondb.net/",
        }
    )
    if args.pokemon:
        pokemon_dir = cli.find_pokemon_directory(args.pokemon, root)
        if not pokemon_dir:
            return 2
        process_one(session, pokemon_dir, dry_run=args.dry_run, overwrite=args.overwrite)
        return 0
    for d in iter_species_dirs(root):
        process_one(session, d, dry_run=args.dry_run, overwrite=args.overwrite)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
