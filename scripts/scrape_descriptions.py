import argparse
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

import cli
import requests
from bs4 import BeautifulSoup
from script_logger import get_script_logger
from validation_utils import (
    add_validation_args,
    has_complete_sentence,
    should_proceed_after_validation_failure,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))
BASE_URL = "https://pokelore.com/pokedex"


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def images_root() -> Path:
    return project_root() / "pokemon_data"


def polite_sleep(min_s: float = 0.25, max_s: float = 0.5) -> None:
    time.sleep(min_s)


def load_metadata(path: Path) -> dict:
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
    tmp.replace(path)


def slug_candidates(name: str) -> list[str]:
    original = name
    gender_variants: list[str] = []
    if "♀" in original:
        gender_variants.extend(
            [
                original.replace("♀", "-f"),
                original.replace("♀", "-female"),
            ]
        )
    if "♂" in original:
        gender_variants.extend(
            [
                original.replace("♂", "-m"),
                original.replace("♂", "-male"),
            ]
        )
    if "_female" in original.lower():
        base_name = original.lower().replace("_female", "")
        gender_variants.extend([f"{base_name}-f", f"{base_name}-female"])
    if "_male" in original.lower():
        base_name = original.lower().replace("_male", "")
        gender_variants.extend([f"{base_name}-m", f"{base_name}-male"])

    def ascii_lower(s: str) -> str:
        s = unicodedata.normalize("NFKD", s)
        s = s.encode("ascii", "ignore").decode("ascii")
        return s.lower()

    bases = [original, *gender_variants]
    variants: list[str] = []
    for b in bases:
        lowered = ascii_lower(b)
        lowered = lowered.replace("'", "").replace("’", "").replace(".", "")
        parts = re.split(r"[^a-z0-9]+", lowered)
        hyphenated = "-".join(p for p in parts if p)
        if hyphenated:
            variants.append(hyphenated)
        joined = "".join(p for p in parts if p)
        if joined and joined != hyphenated:
            variants.append(joined)
    seen = set()
    out: list[str] = []
    for v in variants:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def extract_description_from_html(html: str) -> tuple[str | None, int | None]:
    soup = BeautifulSoup(html, "html.parser")
    node = soup.select_one(".pkm_desc")
    if not node:
        return None, None
    text = node.get_text(" ", strip=True)
    if not text:
        return None, None
    generation: int | None = None
    gen_match = re.search(r"It was introduced in Generation\s+(\d+)\.", text, flags=re.IGNORECASE)
    if gen_match:
        try:
            generation = int(gen_match.group(1))
        except ValueError:
            generation = None
    text = re.sub(r"\s*It was introduced in Generation\s+\d+\.\s*$", "", text, flags=re.IGNORECASE)
    return text.strip(), generation


def fetch_description(
    session: requests.Session, name: str
) -> tuple[str | None, str | None, int | None]:
    for slug in slug_candidates(name):
        url = f"{BASE_URL}/{slug}"
        try:
            resp = session.get(url, timeout=20)
            if resp.status_code != 200:
                polite_sleep()
                continue
            desc, generation = extract_description_from_html(resp.text)
            if desc:
                return desc, url, generation
        except requests.RequestException:
            pass
        polite_sleep()
    return None, None, None


def process_species_directory(
    session: requests.Session,
    species_directory: Path,
    *,
    overwrite: bool = False,
    dry_run: bool = False,
) -> None:
    metadata_path = species_directory / "metadata.json"
    metadata = load_metadata(metadata_path)
    species_name = metadata.get("name") or species_directory.name
    desc, source_url, generation = fetch_description(session, species_name)
    if not desc:
        return
    description_changed = metadata.get("description") != desc
    generation_changed = generation is not None and metadata.get("generation") != generation
    if not overwrite and not description_changed and not generation_changed:
        return
    metadata["description"] = desc
    if generation is not None:
        metadata["generation"] = generation
    if dry_run:
        return
    atomic_write(metadata_path, json.dumps(metadata, indent=2, ensure_ascii=False).encode("utf-8"))
    if source_url:
        pass
    else:
        pass


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Fetch descriptions from pokelore.com into metadata.json (updates missing/incorrect descriptions by default)"
    )
    cli.add_overwrite(p, help="Force writing even if description is unchanged")
    cli.add_dry_run(p)
    cli.add_pokemon(p, help="Only process a specific Pokemon by name/directory")
    p.add_argument(
        "--progress", action="store_true", help="Show progress indicators during processing"
    )
    p.add_argument("--debug", action="store_true", help="Save debug information on failures")
    add_validation_args(p)
    return p.parse_args()


def validate_before_scraping(args: argparse.Namespace) -> bool:
    logger = get_script_logger()
    if args.skip_validation:
        logger.info("⏭️  Skipping validation checks")
        return True
    logger.info("🧪 Pre-flight validation for description scraper...")
    logger.info("  🌐 Testing pokelore.com availability...")
    try:
        session = requests.Session()
        response = session.get(BASE_URL, timeout=10)
        if response.status_code != 200:
            logger.info(f"  ❌ pokelore.com returned HTTP {response.status_code}")
            return False
        if not has_complete_sentence(response.text):
            logger.info("  ❌ pokelore.com page has no complete sentences (possible error page)")
            return False
        content = response.text.lower()
        pokemon_indicators = ["pokemon", "pokémon", "generation", "pokedex", "pokédx"]
        has_pokemon_content = any(indicator in content for indicator in pokemon_indicators)
        if not has_pokemon_content:
            logger.info("  ❌ pokelore.com page doesn't contain Pokemon-related content")
            return False
        if len(response.text) < 5000:
            logger.info(f"  ⚠️  pokelore.com page is quite small ({len(response.text)} chars)")
        logger.info("  ✅ pokelore.com is accessible with valid Pokemon content")
        logger.info("  ✅ Pre-flight validation passed")
        return True
    except Exception as e:
        logger.info(f"  ❌ Failed to access pokelore.com: {e}")
        return False


def main() -> None:
    args = parse_args()
    if args.validation_only:
        success = validate_before_scraping(args)
        if success:
            return
        else:
            exit(1)
    if not validate_before_scraping(args):
        if not should_proceed_after_validation_failure(args.force):
            exit(1)
    root = images_root()
    if not root.exists():
        return
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    species_dirs = cli.filter_pokemon_directories(args.pokemon, root)
    if args.pokemon and not species_dirs:
        return
    if args.pokemon:
        pass
    total_pokemon = len(species_dirs)
    for _i, species_directory in enumerate(species_dirs, 1):
        if args.progress and total_pokemon > 10:
            pass
        try:
            process_species_directory(
                session, species_directory, overwrite=args.overwrite, dry_run=args.dry_run
            )
            if args.progress and total_pokemon > 10:
                pass
        except Exception:
            if not args.progress or total_pokemon <= 10 or args.progress:
                pass
        polite_sleep()


if __name__ == "__main__":
    main()
