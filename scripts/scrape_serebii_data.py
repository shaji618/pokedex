from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import time
from dataclasses import dataclass
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


NATIONAL_DEX_URL = "https://www.serebii.net/pokemon/nationalpokedex.shtml"


@dataclass
class Species:
    dex: int
    name: str
    types: list[str]
    speed: int = 50  # Default speed if not found


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def images_root() -> Path:
    return project_root() / "pokemon_data"


def normalize_name(name: str) -> str:
    name = name.strip().lower()
    if "♀" in name:
        name = name.replace("♀", "")
        name = re.sub(r"[^a-z0-9]+", "_", name)
        name = re.sub(r"_+", "_", name).strip("_")
        name = f"{name}_female"
    elif "♂" in name:
        name = name.replace("♂", "")
        name = re.sub(r"[^a-z0-9]+", "_", name)
        name = re.sub(r"_+", "_", name).strip("_")
        name = f"{name}_male"
    else:
        name = re.sub(r"[^a-z0-9]+", "_", name)
        name = re.sub(r"_+", "_", name).strip("_")
    return name or "unknown"


def fetch_index(session: requests.Session) -> str:
    logger = get_script_logger()
    resp = session.get(NATIONAL_DEX_URL, timeout=20)
    resp.raise_for_status()
    text = resp.text
    logger.info(f"Index status={resp.status_code} bytes={len(text)}")
    return text


def parse_species(html: str) -> list[Species]:
    logger = get_script_logger()
    soup = BeautifulSoup(html, "html.parser")
    species: list[Species] = []
    table = soup.select_one("#content main table")
    logger.info(f"Anchored table found: {bool(table)}")
    if not table:
        all_tables = soup.find_all("table")
        logger.info(f"Total tables found: {len(all_tables)}")
        for i, t in enumerate(all_tables):
            table_text = t.get_text()
            if "#" in table_text and ("pokemon" in table_text.lower() or len(table_text) > 1000):
                table = t
                logger.info(f"Using fallback table #{i} (contains # and Pokemon-like content)")
                break
    candidate_rows = table.select("tr") if table else soup.find_all("tr")
    logger.info(f"Scanning rows: {len(candidate_rows)}")
    for tr in candidate_rows:
        tds = tr.find_all("td")
        if len(tds) < 3:
            continue
        no_td = tds[0]
        raw_no = no_td.get_text(" ", strip=True)
        m = re.search(r"(\d{1,4})", raw_no)
        if not m:
            continue
        dex = int(m.group(1))
        a = tr.select_one('td a[href^="/pokemon/"]')
        raw_name = a.get_text(strip=True) if a else ""
        if not raw_name:
            fallback_name = ""
            if len(tds) >= 4:
                for idx in (2, 3):
                    txt = tds[idx].get_text(" ", strip=True)
                    if txt:
                        fallback_name = txt
                        break
            raw_name = fallback_name
        if not raw_name:
            continue
        types: list[str] = []
        for img in tr.find_all("img"):
            src = img.get("src", "")
            mtype = re.search(r"/type/([a-z]+)\.gif", src)
            if mtype:
                types.append(mtype.group(1))
        types = list(dict.fromkeys(types))

        # Extract speed stat from 12th column (index 11, 0-based)
        speed = 50  # Default speed
        try:
            if len(tds) >= 12:
                speed_text = tds[11].get_text(strip=True)
                if speed_text.isdigit():
                    speed = int(speed_text)
        except (IndexError, ValueError):
            pass  # Keep default speed

        species.append(Species(dex=dex, name=raw_name, types=types, speed=speed))
    dedup: dict[int, Species] = {}
    for sp in species:
        if sp.dex not in dedup:
            dedup[sp.dex] = sp
    out = [dedup[k] for k in sorted(dedup.keys())]
    logger.info(f"Unique species parsed: {len(out)}")
    return out


def extract_max_dex(html: str) -> int:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("#content main table")
    scope = str(table) if table else html
    nums = [int(n) for n in re.findall(r"#(\d{1,4})", scope)]
    if not nums:
        return 1025
    max_found = max(nums)
    return max_found if 1 <= max_found <= 5000 else 1025


def fetch_species_name_by_dex(session: requests.Session, dex: int) -> str:
    dex_str = str(dex).zfill(3)
    detail_url = f"https://www.serebii.net/pokemon/nationaldex/{dex_str}.shtml"
    try:
        resp = session.get(detail_url, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        title = soup.title.get_text(strip=True) if soup.title else ""
        m = re.search(r"^([^\-#]+)\s+-\s+#?\d+", title)
        if m:
            return m.group(1).strip()
        strong = soup.find("strong")
        if strong and strong.get_text(strip=True):
            return strong.get_text(strip=True)
    except requests.RequestException:
        pass
    return f"pokemon_{dex_str}"


def build_image_url(dex: int) -> str:
    dex_str = str(dex).zfill(3)
    return f"https://www.serebii.net/pokemon/art/{dex_str}.png"


def target_path_for(name: str) -> Path:
    norm = normalize_name(name)
    folder = images_root() / norm
    return folder / "main.png"


def _canon_types(types: list[str]) -> list[str]:
    return cli.normalize_types(types)


def write_metadata(
    name: str, dex: int, types: list[str], speed: int = 50, *, overwrite: bool = False
) -> bool:
    folder = images_root() / normalize_name(name)
    ensure_parent_directory(folder / "_placeholder")
    path = folder / "metadata.json"
    new_data = {"pokedex_number": dex, "name": name, "types": _canon_types(types), "speed": speed}
    if path.exists() and not overwrite:
        try:
            with open(path) as f:
                old = json.load(f)
            old_types = _canon_types(old.get("types", []))
            old_data = {
                "pokedex_number": old.get("pokedex_number"),
                "name": old.get("name"),
                "types": old_types,
                "speed": old.get("speed", 50),  # Default to 50 if speed missing
            }
            if old_data == new_data:
                return False
        except Exception:
            pass
    with open(path, "w") as f:
        json.dump(new_data, f, indent=2)
    return True


def ensure_parent_directory(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def atomic_write(path: Path, content: bytes) -> None:
    ensure_parent_directory(path)
    tmp = path.with_suffix(path.suffix + ".part")
    with open(tmp, "wb") as f:
        f.write(content)
    tmp.replace(path)


def polite_sleep() -> None:
    time.sleep(random.uniform(0.2, 0.5))


def delete_pokemon_directory(directory_name: str, reason: str) -> bool:
    logger = get_script_logger()
    pokemon_directory = images_root() / directory_name
    if not pokemon_directory.exists():
        return True
    try:
        logger.info(f"  🗑️ Deleting directory {directory_name} ({reason})")
        shutil.rmtree(pokemon_directory)
        return True
    except OSError as e:
        logger.error(f"  ❌ Failed to delete {directory_name}: {e}")
        return False


def get_existing_pokemon_directories() -> set[str]:
    pokemon_root = images_root()
    if not pokemon_root.exists():
        return set()
    directories = set()
    for item in pokemon_root.iterdir():
        if item.is_dir() and not item.name.startswith("."):
            directories.add(item.name)
    return directories


def cleanup_invalid_directories(
    valid_species: list[Species], *, dry_run: bool = False
) -> tuple[int, int]:
    logger = get_script_logger()
    existing_dirs = get_existing_pokemon_directories()
    valid_dirs = {normalize_name(sp.name) for sp in valid_species}
    invalid_dirs = existing_dirs - valid_dirs
    if not invalid_dirs:
        logger.info("✅ No invalid directories found")
        return 0, 0
    logger.info(f"🧹 Found {len(invalid_dirs)} directories not in Serebii data:")
    for dir_name in sorted(invalid_dirs):
        logger.info(f"  • {dir_name}")
    if dry_run:
        logger.info(f"🔍 DRY RUN: Would delete {len(invalid_dirs)} invalid directories")
        return len(invalid_dirs), 0
    removed_count = 0
    failed_count = 0
    for dir_name in invalid_dirs:
        success = delete_pokemon_directory(dir_name, "not found in Serebii national pokédex")
        if success:
            removed_count += 1
        else:
            failed_count += 1
    logger.info(f"🧹 Cleanup complete: {removed_count} removed, {failed_count} failed")
    return removed_count, failed_count


def download_one(
    session: requests.Session, sp: Species, *, overwrite: bool, dry_run: bool
) -> tuple[int, str, str]:
    url = build_image_url(sp.dex)
    out_path = target_path_for(sp.name)
    if (out_path.exists() and out_path.stat().st_size > 0) and not overwrite:
        return (sp.dex, sp.name, "skip_exists")
    if dry_run:
        return (sp.dex, sp.name, "would_download")
    try:
        logger = get_script_logger()
        logger.info(f"Downloading {normalize_name(sp.name)} from {url}")
        resp = session.get(url, timeout=20)
        if resp.status_code == 404:
            return (sp.dex, sp.name, "not_found")
        resp.raise_for_status()
        ctype = resp.headers.get("Content-Type", "")
        if "image" not in ctype:
            return (sp.dex, sp.name, f"bad_content_type:{ctype}")
        atomic_write(out_path, resp.content)
        return (sp.dex, sp.name, "ok")
    except requests.RequestException as ex:
        return (sp.dex, sp.name, f"error:{type(ex).__name__}")


def validate_before_scraping(args: argparse.Namespace) -> bool:
    logger = get_script_logger()
    if args.skip_validation:
        logger.info("⏭️  Skipping validation checks")
        return True
    logger.info("🧪 Pre-flight validation for Serebii scraper...")
    logger.info("  🌐 Testing serebii.net national pokédx availability...")
    try:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.serebii.net/",
            }
        )
        response = session.get(NATIONAL_DEX_URL, timeout=15)
        if response.status_code != 200:
            logger.info(f"  ❌ serebii.net returned HTTP {response.status_code}")
            return False
        if not has_complete_sentence(response.text):
            logger.info("  ❌ serebii.net page has no complete sentences (possible error page)")
            return False
        content = response.text.lower()
        pokemon_indicators = ["pokemon", "pokémon", "national", "pokédx", "serebii"]
        has_pokemon_content = any(indicator in content for indicator in pokemon_indicators)
        if not has_pokemon_content:
            logger.info("  ❌ serebii.net page doesn't contain Pokemon-related content")
            return False
        if "<table" not in content:
            logger.info("  ❌ serebii.net page doesn't contain table structure")
            return False
        if len(response.text) < 10000:
            logger.info(f"  ⚠️  serebii.net page is quite small ({len(response.text)} chars)")
        logger.info("  🧪 Testing Pokemon data parsing...")
        try:
            test_species = parse_species(response.text)
            if not test_species:
                logger.info("  ❌ No Pokemon species could be parsed from the page")
                return False
            logger.info(f"  ✅ Successfully parsed {len(test_species)} Pokemon species")
            edge_cases = [
                {"name": "Nidoran♀", "dex": 29, "expected_normalized": "nidoran_female"},
                {"name": "Nidoran♂", "dex": 32, "expected_normalized": "nidoran_male"},
                {"name": "Mr. Mime", "dex": 122, "expected_normalized": "mr_mime"},
                {"name": "Farfetch'd", "dex": 83, "expected_normalized": "farfetch_d"},
                {"name": "Ho-Oh", "dex": 250, "expected_normalized": "ho_oh"},
            ]
            logger.info("  🎯 Testing edge case Pokemon parsing:")
            edge_case_success = 0
            species_by_dex = {sp.dex: sp for sp in test_species}
            for edge_case in edge_cases:
                expected_name = edge_case["name"]
                expected_dex = edge_case["dex"]
                expected_normalized = edge_case["expected_normalized"]
                found_species = species_by_dex.get(expected_dex)
                if not found_species:
                    logger.info(
                        f"    ❌ {expected_name} (#{expected_dex}): Not found in parsed data"
                    )
                    continue
                actual_normalized = normalize_name(found_species.name)
                if actual_normalized == expected_normalized:
                    logger.info(
                        f"    ✅ {expected_name} (#{expected_dex}): '{found_species.name}' → '{actual_normalized}'"
                    )
                    edge_case_success += 1
                else:
                    logger.info(
                        f"    ❌ {expected_name} (#{expected_dex}): '{found_species.name}' → '{actual_normalized}' (expected '{expected_normalized}')"
                    )
            edge_case_rate = edge_case_success / len(edge_cases)
            logger.info(
                f"  📊 Edge case success: {edge_case_success}/{len(edge_cases)} ({edge_case_rate:.1%})"
            )
            if edge_case_rate < 0.8:
                logger.info("  ❌ Edge case parsing below 80% - critical parsing issues detected")
                return False
            valid_entries = 0
            for sp in test_species[:20]:
                if sp.dex > 0 and sp.name and sp.name != "unknown":
                    valid_entries += 1
            quality_rate = valid_entries / min(20, len(test_species))
            logger.info(
                f"  📊 General data quality: {valid_entries}/{min(20, len(test_species))} entries valid ({quality_rate:.1%})"
            )
            if quality_rate < 0.9:
                logger.info("  ⚠️  General data quality below 90% - parsing may have issues")
                return False
        except Exception as e:
            logger.info(f"  ❌ Pokemon parsing test failed: {e}")
            return False
        logger.info("  ✅ serebii.net is accessible with valid Pokemon data structure")
        logger.info("  ✅ Pre-flight validation passed")
        return True
    except Exception as e:
        logger.info(f"  ❌ Failed to access serebii.net: {e}")
        return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Serebii Pokédex artwork and write metadata"
    )
    cli.add_overwrite(parser, help="Overwrite existing images and metadata even if unchanged")
    cli.add_dry_run(parser, help="Do not write files; only report actions")
    cli.add_pokemon(parser, help="Only process a single Pokémon (name or Pokédex number)")
    parser.add_argument(
        "--images-only",
        action="store_true",
        help="Only download images; do not create or update metadata.json",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Remove directories for Pokémon not found in Serebii national pokédx (use with caution)",
    )
    add_validation_args(parser)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logger = get_script_logger()
    if args.validation_only:
        logger.info("🧪 Validation-only mode")
        success = validate_before_scraping(args)
        logger.info("\n" + "=" * 50)
        if success:
            logger.info("✅ Validation passed - Serebii scraping would be safe to run")
            return
        else:
            logger.error("❌ Validation failed - fix issues before scraping")
            exit(1)
    if not validate_before_scraping(args):
        if not should_proceed_after_validation_failure(args.force):
            exit(1)
    root = images_root()
    root.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.serebii.net/",
            "Connection": "keep-alive",
        }
    )
    logger.info(f"Fetching index: {NATIONAL_DEX_URL}")
    html = fetch_index(session)
    logger.info("Parsing Serebii national Pokédex data...")
    full_species_list = parse_species(html)
    logger.info(f"Unique species parsed: {len(full_species_list)}")
    if not full_species_list:
        max_dex = extract_max_dex(html)
        logger.warning(f"Index parse returned 0 rows. Falling back to detail pages 1..{max_dex}")
        tmp: list[Species] = []
        for dex in range(1, max_dex + 1):
            if dex % 25 == 0:
                logger.info(f"Fetching detail for dex {dex:03}")
            name = fetch_species_name_by_dex(session, dex)
            logger.info(f"dex {dex:03} -> {name}")
            tmp.append(Species(dex=dex, name=name, types=[], speed=50))
            polite_sleep()
        full_species_list = tmp
    species_list = full_species_list.copy()
    if getattr(args, "pokemon", None):
        query = str(args.pokemon).strip()
        target_list: list[Species] = []
        if query.isdigit():
            wanted = int(query)
            target_list = [sp for sp in species_list if sp.dex == wanted]
            logger.info(f"🔍 Searching for Pokédex #{wanted}")
        else:
            qnorm = normalize_name(query)
            target_list = [sp for sp in species_list if normalize_name(sp.name) == qnorm]
            if not target_list:
                query_lower = query.lower()
                target_list = [sp for sp in species_list if query_lower in sp.name.lower()]
            logger.info(f"🔍 Searching for Pokémon name: {query} -> {qnorm}")
        if not target_list:
            logger.error(f"❌ No species matched: {query}")
            logger.info(
                f"💡 Available in first 10 results: {[sp.name for sp in species_list[:10]]}"
            )
            return
        elif len(target_list) > 1:
            logger.warning("⚠️  Multiple matches found:")
            for sp in target_list:
                logger.info(f"  • #{sp.dex:03d} {sp.name}")
            target_list = target_list[:1]
            logger.info(f"📌 Using first match: #{target_list[0].dex:03d} {target_list[0].name}")
        else:
            logger.info(f"✅ Found: #{target_list[0].dex:03d} {target_list[0].name}")
        species_list = target_list
    logger.info(f"📊 Processing {len(species_list)} species")
    for sp in species_list:
        dex, name, status = download_one(
            session, sp, overwrite=args.overwrite, dry_run=args.dry_run
        )
        if status == "ok":
            logger.info(f"Downloaded {name} [{dex:03}]")
        elif status == "skip_exists":
            logger.info(f"Skipped image download for {name} [{dex:03}] (already exists)")
        elif status == "would_download":
            logger.info(f"Would download {name} [{dex:03}]")
        else:
            logger.warning(f"Failed {name} [{dex:03}] -> {status}")
        if not args.images_only:
            if args.dry_run:
                folder = images_root() / normalize_name(name)
                path = folder / "metadata.json"
                new_data = {
                    "pokedex_number": dex,
                    "name": name,
                    "types": _canon_types(sp.types),
                    "speed": sp.speed,
                }
                would_update = True
                if path.exists() and not args.overwrite:
                    try:
                        with open(path) as f:
                            old = json.load(f)
                        old_types = _canon_types(old.get("types", []))
                        old_data = {
                            "pokedex_number": old.get("pokedex_number"),
                            "name": old.get("name"),
                            "types": old_types,
                            "speed": old.get("speed", 50),  # Default to 50 if speed missing
                        }
                        would_update = old_data != new_data
                    except Exception:
                        would_update = True
                if would_update:
                    logger.info(f"Would update metadata for {name}")
            else:
                updated = write_metadata(name, dex, sp.types, sp.speed, overwrite=args.overwrite)
                if updated:
                    logger.info(f"Updated metadata for {name}")
        polite_sleep()
    if args.cleanup:
        logger.info("\n🧹 Cleaning up directories not found in Serebii data...")
        logger.info(
            f"  📊 Comparing local directories with Serebii's {len(full_species_list)} Pokemon"
        )
        logger.info("  🎯 Will remove orphaned directories and add missing Pokemon")
        removed, failed = cleanup_invalid_directories(full_species_list, dry_run=args.dry_run)
        if removed > 0 or failed > 0:
            logger.info(f"🧹 Cleanup results: {removed} removed, {failed} failed")
        else:
            logger.info("🧹 Cleanup complete: No changes needed")
    logger.info("Done")


if __name__ == "__main__":
    main()
