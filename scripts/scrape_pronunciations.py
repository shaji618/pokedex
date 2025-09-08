import argparse
import json
import re
import sys
from pathlib import Path

import cli
import requests
from bs4 import BeautifulSoup
from script_logger import get_script_logger
from validation_utils import (
    add_validation_args,
    normalize_pokemon_name,
    should_proceed_after_validation_failure,
)


MASTER_URL = "https://pokemonlp.fandom.com/wiki/Pok%C3%A9mon_Pronunciation_Guide"


def get_generation_url(generation: int) -> str:
    roman_numeral = cli.to_roman(generation)
    return f"https://pokemonlp.fandom.com/wiki/Pok%C3%A9mon_Pronunciation_Guide/Generation_{roman_numeral}"


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def fetch_generation_links(session: requests.Session) -> list[str]:
    resp = session.get(MASTER_URL, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    links: list[str] = []
    for a in soup.select('a[href*="Pronunciation_Guide/Generation_"]'):
        href = a.get("href") or ""
        if not href:
            continue
        url = href if href.startswith("http") else "https://pokemonlp.fandom.com" + href
        if url not in links:
            links.append(url)
    return links


def _find_pronunciation_table(
    soup: BeautifulSoup,
) -> tuple[list[str], list[BeautifulSoup]] | None:
    for table in soup.find_all("table"):
        header_cells = table.find_all("th")
        headers = [th.get_text(" ", strip=True) for th in header_cells]
        header_text = " ".join(h.lower() for h in headers)
        if ("pronunciation" in header_text) and ("ipa" in header_text):
            rows = table.find_all("tr")
            data_rows = [tr for tr in rows if tr.find("td")]
            if data_rows:
                return headers, data_rows
    return None


def _extract_from_row(tds: list) -> tuple[int, str, str] | None:
    dex_val: int | None = None
    for td in tds:
        txt = td.get_text(" ", strip=True)
        m = re.search(r"(\d+)", txt)
        if m:
            try:
                dex_val = int(m.group(1))
                break
            except Exception:
                continue
    if dex_val is None:
        return None
    ipa_idx = None
    for idx in range(len(tds) - 1, -1, -1):
        txt = tds[idx].get_text(" ", strip=True)
        if not txt:
            continue
        if "/" in txt:
            ipa_idx = idx
            break
    if ipa_idx is None:
        return None
    ipa_text = tds[ipa_idx].get_text(" ", strip=True)
    pron_idx = max(0, ipa_idx - 1)
    pron_text = tds[pron_idx].get_text(" ", strip=True)
    return dex_val, pron_text, ipa_text


def parse_generation_page(session: requests.Session, url: str) -> dict[int, tuple[str, str]]:
    resp = session.get(url, timeout=20)
    if resp.status_code != 200:
        return {}
    soup = BeautifulSoup(resp.text, "html.parser")
    found = _find_pronunciation_table(soup)
    if not found:
        return {}
    headers, rows = found
    out: dict[int, tuple[str, str]] = {}
    for tr in rows:
        tds = tr.find_all("td")
        if not tds:
            continue
        extracted = _extract_from_row(tds)
        if not extracted:
            continue
        dex, pron_text, ipa_text = extracted
        if not pron_text and not ipa_text:
            continue
        if dex not in out:
            out[dex] = (pron_text, ipa_text)
    return out


def find_pokemon_pronunciation_by_dex_number(
    session: requests.Session, generation: int, pokedex_number: int, pokemon_name: str
) -> tuple[str, str] | None:
    if generation < 1 or generation > 9:
        return None
    url = get_generation_url(generation)
    try:
        resp = session.get(url, timeout=20)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        found = _find_pronunciation_table(soup)
        if not found:
            return None
        headers, rows = found
        target_dex_formatted = f"#{pokedex_number:04d}"
        for _i, tr in enumerate(rows):
            tds = tr.find_all("td")
            if not tds or len(tds) < 6:
                continue
            dex_cell = tds[1]
            dex_text = dex_cell.get_text(" ", strip=True)
            if dex_text == target_dex_formatted:
                pokemon_name_cell = tds[2]
                name_text = pokemon_name_cell.get_text(" ", strip=True)
                name_similarity = names_are_similar(pokemon_name, name_text)
                if name_similarity:
                    if len(tds) >= 7:
                        pron_text = tds[5].get_text(" ", strip=True)
                        ipa_text = tds[6].get_text(" ", strip=True)
                    elif len(tds) == 6:
                        pron_text = tds[4].get_text(" ", strip=True)
                        ipa_text = tds[5].get_text(" ", strip=True)
                    else:
                        continue
                    if pron_text:
                        return (pron_text, ipa_text)
                    else:
                        return None
                else:
                    return None
        return None
    except Exception:
        return None


def find_pokemon_pronunciation_across_generations(
    session: requests.Session, pokedex_number: int, pokemon_name: str
) -> tuple[str, str] | None:
    for generation in range(1, 10):
        result = find_pokemon_pronunciation_by_dex_number(
            session, generation, pokedex_number, pokemon_name
        )
        if result:
            return result
    return None


def normalize_pokemon_name_for_comparison(name: str) -> str:
    """Normalize Pokemon name for simple comparison using centralized function."""
    return normalize_pokemon_name(name, format_type="simple")


def names_are_similar(name1: str, name2: str, threshold: float = 0.8) -> bool:
    norm1 = normalize_pokemon_name_for_comparison(name1)
    norm2 = normalize_pokemon_name_for_comparison(name2)
    if norm1 == norm2:
        return True
    if norm1 in norm2 or norm2 in norm1:
        return True
    min_len = min(len(norm1), len(norm2))
    max_len = max(len(norm1), len(norm2))
    if max_len == 0 or min_len / max_len < 0.6:
        return False
    matches = 0
    for i in range(min_len):
        if norm1[i] == norm2[i]:
            matches += 1
    similarity = matches / max_len
    return similarity >= threshold


def build_pronunciation_index(session: requests.Session) -> dict[int, tuple[str, str]]:
    index: dict[int, tuple[str, str]] = {}
    links = fetch_generation_links(session)
    for url in links:
        gen_map = parse_generation_page(session, url)
        for dex, vals in gen_map.items():
            if dex not in index:
                index[dex] = vals
        cli.polite_sleep(0.4)
    return index


def upsert_pronunciations(
    root: Path, index: dict[int, tuple[str, str]], *, overwrite: bool = False, dry_run: bool = False
) -> None:
    species_dirs = [p for p in sorted(root.iterdir()) if p.is_dir()]
    for species_directory in species_dirs:
        meta_path = species_directory / "metadata.json"
        meta = load_json(meta_path)
        dex = meta.get("pokedex_number")
        if not isinstance(dex, int):
            try:
                dex = int(dex)
            except Exception:
                continue
        if dex not in index:
            continue
        phonetic, ipa = index[dex]
        pronunciations = meta.get("pronunciations") or {}
        previous_phon = pronunciations.get("phonetic")
        previous_ipa = pronunciations.get("ipa")
        changed = False
        if previous_phon != phonetic or overwrite:
            pronunciations["phonetic"] = phonetic
            changed = True
        if previous_ipa != ipa or overwrite:
            pronunciations["ipa"] = ipa
            changed = True
        if changed:
            meta["pronunciations"] = pronunciations
            if dry_run:
                continue
            cli.atomic_write(
                meta_path, json.dumps(meta, indent=2, ensure_ascii=False).encode("utf-8")
            )
            parts = []
            if previous_phon != phonetic or overwrite:
                parts.append(f'phonetic: "{previous_phon}" -> "{phonetic}"')
            if previous_ipa != ipa or overwrite:
                parts.append(f'ipa: "{previous_ipa}" -> "{ipa}"')
            "; ".join(parts) if parts else "updated"
        else:
            pass


def process_single_pokemon(
    session: requests.Session, pokemon_name: str, *, overwrite: bool = False, dry_run: bool = False
) -> bool:
    species_directory = cli.find_pokemon_directory(pokemon_name)
    if not species_directory:
        return False
    meta_path = species_directory / "metadata.json"
    metadata = cli.load_pokemon_metadata(species_directory)
    if not metadata:
        return False
    generation = metadata.get("generation")
    display_name = metadata.get("name", species_directory.name)
    pokedex_number = metadata.get("pokedex_number")
    if not isinstance(pokedex_number, int) or pokedex_number < 1:
        return False
    if isinstance(generation, int) and 1 <= generation <= 9:
        result = find_pokemon_pronunciation_by_dex_number(
            session, generation, pokedex_number, display_name
        )
    else:
        result = find_pokemon_pronunciation_across_generations(
            session, pokedex_number, display_name
        )
    if not result:
        return False
    phonetic, ipa = result
    pronunciations = metadata.get("pronunciations") or {}
    previous_phon = pronunciations.get("phonetic")
    previous_ipa = pronunciations.get("ipa")
    phonetic_changed = previous_phon != phonetic
    ipa_changed = previous_ipa != ipa
    if not overwrite and not phonetic_changed and not ipa_changed:
        return True
    pronunciations["phonetic"] = phonetic
    pronunciations["ipa"] = ipa
    metadata["pronunciations"] = pronunciations
    if dry_run:
        changes = []
        if phonetic_changed:
            changes.append(f'phonetic: "{previous_phon}" -> "{phonetic}"')
        if ipa_changed:
            changes.append(f'ipa: "{previous_ipa}" -> "{ipa}"')
        "; ".join(changes) if changes else "would update"
        return True
    cli.atomic_write(meta_path, json.dumps(metadata, indent=2, ensure_ascii=False).encode("utf-8"))
    changes = []
    if phonetic_changed:
        changes.append(f'phonetic: "{previous_phon}" -> "{phonetic}"')
    if ipa_changed:
        changes.append(f'ipa: "{previous_ipa}" -> "{ipa}"')
    "; ".join(changes) if changes else "updated"
    return True


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Scrape and upsert pronunciations into metadata.json")
    cli.add_overwrite(p, help="Force writing even if unchanged")
    cli.add_dry_run(p)
    cli.add_pokemon(
        p,
        help="Process only a specific Pokemon by name/directory (uses generation-specific lookup or searches all generations)",
    )
    add_validation_args(p)
    return p.parse_args()


def validate_before_scraping(args: argparse.Namespace) -> bool:
    logger = get_script_logger()
    if args.skip_validation:
        logger.info("⏭️  Skipping validation checks")
        return True
    logger.info("🧪 Pre-flight validation for pronunciations scraper...")
    logger.info("  🌐 Testing pokemonlp.fandom.com availability...")
    try:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        test_url = get_generation_url(1)
        response = session.get(test_url, timeout=10)
        if response.status_code != 200:
            logger.info(f"  ❌ pokemonlp.fandom.com returned HTTP {response.status_code}")
            return False
        soup = BeautifulSoup(response.text, "html.parser")
        tables = soup.find_all("table")
        if not tables:
            logger.info("  ❌ No table elements found on page")
            return False
        table_text = " ".join(table.get_text() for table in tables).lower()
        page_text = response.text.lower()
        pokemon_indicators = ["pikachu", "bulbasaur", "charmander", "pronunciation", "pokemon"]
        has_pokemon_content = any(
            indicator in table_text or indicator in page_text for indicator in pokemon_indicators
        )
        if not has_pokemon_content:
            logger.info("  ❌ pokemonlp.fandom.com page doesn't contain expected Pokemon content")
            return False
        logger.info("  ✅ pokemonlp.fandom.com is accessible with valid pronunciation tables")
        logger.info("  ✅ Pre-flight validation passed")
        return True
    except Exception as e:
        logger.info(f"  ❌ Failed to access pokemonlp.fandom.com: {e}")
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
    root = cli.pokemon_data_root()
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
    if args.pokemon:
        success = process_single_pokemon(
            session, args.pokemon, overwrite=args.overwrite, dry_run=args.dry_run
        )
        if success:
            pass
        else:
            sys.exit(1)
        return
    index = build_pronunciation_index(session)
    upsert_pronunciations(root, index, overwrite=args.overwrite, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
