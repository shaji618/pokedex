from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cli
import requests
from browser_utils import PersistentBrowserSession
from bs4 import BeautifulSoup
from script_logger import get_script_logger
from validation_utils import (
    add_validation_args,
    compare_scraped_vs_real_data,
    get_real_pokemon_metadata,
    get_sample_pokemon,
    normalize_pokemon_name,
    should_proceed_after_validation_failure,
)


@dataclass
class PokemonData:
    pokedex_number: int
    name: str
    types: list[str]
    url: str


def normalize_name(name: str) -> str:
    name = name.strip().lower()
    name = re.sub(r"[^a-z0-9]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name or "unknown"


def polite_sleep() -> None:
    time.sleep(random.uniform(0.5, 1.5))


def create_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": "max-age=0",
            "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Referer": "https://www.pokemon.com/",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
    )
    return session


def normalize_pokemon_name_to_url_slug(name: str) -> str:
    """Normalize Pokemon name to URL slug using centralized function."""
    slug = normalize_pokemon_name(name, format_type="url")
    # Remove spaces for URL (pokemon.com doesn't use them)
    slug = slug.replace(" ", "")
    return slug


def build_pokemon_url(pokemon_input: str) -> str:
    if pokemon_input.isdigit():
        return f"https://www.pokemon.com/us/pokedex/{pokemon_input}"
    else:
        slug = normalize_pokemon_name_to_url_slug(pokemon_input)
        return f"https://www.pokemon.com/us/pokedex/{slug}"


def is_directory_name(name: str) -> bool:
    return ("_" in name and name.islower()) or (
        name.islower() and not any(c in name for c in " '.")
    )


def normalize_input_name(input_name: str) -> str:
    if is_directory_name(input_name):
        normalized = input_name.replace("_", " ").title()
        if normalized == "Farfetch D":
            return "Farfetch'd"
        elif normalized == "Sirfetch D":
            return "Sirfetch'd"
        elif normalized.startswith("Mr "):
            return normalized.replace("Mr ", "Mr. ")
        elif normalized.startswith("Ho Oh"):
            return "Ho-Oh"
        elif normalized == "Nidoran Female":
            return "Nidoran♀"
        elif normalized == "Nidoran Male":
            return "Nidoran♂"
        else:
            return normalized
    else:
        return input_name


def get_directory_name_for_pokemon(pokemon_name: str) -> str:
    normalized = pokemon_name.strip().lower()
    normalized = normalized.replace("♀", "_female").replace("♂", "_male")
    normalized = normalized.replace("'", "_").replace("'", "_")
    normalized = re.sub(r"[.\s-]+", "_", normalized)
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    normalized = normalized.strip("_")
    return normalized


async def extract_pokemon_data_with_playwright(url: str) -> PokemonData | None:
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=VizDisplayCompositor",
                    "--disable-web-security",
                    "--disable-features=VizDisplayCompositor,VizHitTestSurfaceLayer",
                    "--disable-ipc-flooding-protection",
                    "--disable-renderer-backgrounding",
                    "--disable-backgrounding-occluded-windows",
                    "--disable-field-trial-config",
                    "--disable-back-forward-cache",
                    "--enable-features=NetworkService,NetworkServiceLogging",
                    "--force-color-profile=srgb",
                    "--metrics-recording-only",
                    "--no-first-run",
                    "--enable-automation=false",
                    "--disable-extensions",
                    "--hide-scrollbars",
                    "--mute-audio",
                    "--no-default-browser-check",
                    "--no-pings",
                    "--password-store=basic",
                    "--use-gl=swiftshader",
                    "--use-angle=swiftshader",
                    "--disable-gpu-sandbox",
                ],
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1920, "height": 1080},
                locale="en-US",
                timezone_id="America/New_York",
                permissions=["geolocation"],
                geolocation={"latitude": 40.7128, "longitude": -74.0060},
                color_scheme="light",
                extra_http_headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Cache-Control": "max-age=0",
                    "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"macOS"',
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "none",
                    "Sec-Fetch-User": "?1",
                    "Upgrade-Insecure-Requests": "1",
                },
            )
            page = await context.new_page()
            await page.add_init_script("""
            """)
            import random

            if random.random() < 0.3:
                await page.goto("https://www.pokemon.com/", wait_until="domcontentloaded")
                await page.wait_for_timeout(random.randint(1000, 3000))
            await page.goto(url, wait_until="networkidle", timeout=45000)
            await page.wait_for_timeout(random.randint(2000, 4000))
            await page.evaluate("window.scrollTo(0, window.innerHeight / 2)")
            await page.wait_for_timeout(random.randint(1000, 2000))
            content = await page.content()
            await browser.close()
            soup = BeautifulSoup(content, "html.parser")
            if "Pardon Our Interruption" in content:
                return None
            return _extract_pokemon_data_from_soup(soup, url)
    except ImportError:
        return None
    except Exception:
        return None


def _extract_pokemon_data_from_soup(soup: BeautifulSoup, url: str) -> PokemonData | None:
    pokedex_number = None
    title_div = soup.select_one("div.pokedex-pokemon-pagination-title")
    if title_div:
        title_text = title_div.get_text(strip=True)
        number_match = re.search(r"#(\d+)", title_text)
        if number_match:
            pokedex_number = int(number_match.group(1))
    if not pokedex_number:
        pokemon_number_spans = soup.select("span.pokemon-number")
        for span in pokemon_number_spans:
            number_text = span.get_text(strip=True)
            number_match = re.search(r"#(\d+)", number_text)
            if number_match:
                candidate_number = int(number_match.group(1))
                if 1 <= candidate_number <= 9999:
                    pokedex_number = candidate_number
                    break
    if not pokedex_number:
        page_text = soup.get_text()
        number_matches = re.findall(r"#(\d+)", page_text)
        if number_matches:
            for match in number_matches:
                num = int(match)
                if 1 <= num <= 9999:
                    pokedex_number = num
                    break
    if not pokedex_number:
        return None
    pokemon_name = None
    if title_div:
        title_text = title_div.get_text(strip=True)
        name_part = re.sub(r"#\d+\s*", "", title_text).strip()
        if name_part:
            pokemon_name = name_part
    if not pokemon_name and soup.title:
        title_text = soup.title.get_text()
        title_match = re.search(r"^([^|]+)", title_text.strip())
        if title_match:
            potential_name = title_match.group(1).strip()
            if potential_name and not potential_name.startswith("#"):
                pokemon_name = potential_name
    if not pokemon_name:
        url_parts = url.rstrip("/").split("/")
        if url_parts:
            url_name = url_parts[-1]
            if url_name == "farfetchd" or url_name == "83":
                pokemon_name = "Farfetch'd"
            elif url_name == "sirfetchd":
                pokemon_name = "Sirfetch'd"
            elif url_name.isdigit():
                pokemon_name = f"Pokemon #{url_name}"
            else:
                pokemon_name = url_name.replace("-", " ").title()
    if not pokemon_name:
        return None
    types: list[str] = []
    type_list_items = soup.select("div.pokedex-pokemon-attributes.active div.dtm-type li")
    for li in type_list_items:
        type_text = li.get_text(strip=True).lower()
        if cli.is_valid_type(type_text) and type_text not in types:
            types.append(type_text)
    if not types:
        type_section = soup.find(string=re.compile(r"Type", re.I))
        if type_section:
            type_parent = type_section.find_parent()
            if type_parent:
                type_area_text = type_parent.get_text().lower()
                for ptype in cli.get_all_types():
                    if ptype in type_area_text and ptype not in types:
                        types.append(ptype)
    types = cli.normalize_types(types)[:2]
    return PokemonData(pokedex_number=pokedex_number, name=pokemon_name, types=types, url=url)


def extract_pokemon_data(
    session: requests.Session, url: str, use_playwright_fallback: bool = True
) -> PokemonData | None:
    try:
        polite_sleep()
        response = session.get(url, timeout=30)
        response.raise_for_status()
        if len(response.text) < 5000 or "Pardon Our Interruption" in response.text:
            if use_playwright_fallback:
                import asyncio

                return asyncio.run(extract_pokemon_data_with_playwright(url))
            else:
                return None
        soup = BeautifulSoup(response.text, "html.parser")
        return _extract_pokemon_data_from_soup(soup, url)
    except requests.RequestException:
        if use_playwright_fallback:
            import asyncio

            return asyncio.run(extract_pokemon_data_with_playwright(url))
        return None
    except Exception:
        return None


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def validate_and_update_metadata(
    pokemon: PokemonData, directory_name: str, *, update: bool = False
) -> dict[str, Any]:
    pokemon_directory = cli.pokemon_data_root() / directory_name
    result = {"action": "none", "changes": {}, "status": "unchanged"}
    if not pokemon_directory.exists():
        result.update(
            {
                "action": "directory_missing",
                "status": "no_directory",
                "error": f"Directory {pokemon_directory} does not exist",
            }
        )
        return result
    ensure_directory(pokemon_directory)
    metadata_path = pokemon_directory / "metadata.json"
    pokemon_com_data = {
        "pokedex_number": pokemon.pokedex_number,
        "name": pokemon.name,
        "types": pokemon.types,
    }
    if not metadata_path.exists():
        if update:
            with open(metadata_path, mode="w", encoding="utf-8") as f:
                json.dump(pokemon_com_data, f, indent=2, ensure_ascii=False)
            result.update(
                {"action": "created", "status": "new_pokemon", "changes": pokemon_com_data}
            )
        else:
            result.update(
                {"action": "would_create", "status": "new_pokemon", "changes": pokemon_com_data}
            )
        return result
    try:
        with open(metadata_path, encoding="utf-8") as f:
            existing_data = json.load(f)
        existing_core = {
            "pokedex_number": existing_data.get("pokedex_number"),
            "name": existing_data.get("name"),
            "types": cli.normalize_types(existing_data.get("types", [])),
        }
        pokemon_com_data["types"] = cli.normalize_types(pokemon_com_data["types"])
        changes = {}
        for key, new_value in pokemon_com_data.items():
            old_value = existing_core.get(key)
            if old_value != new_value:
                changes[key] = {"old": old_value, "new": new_value}
        if not changes:
            result.update({"action": "validated", "status": "correct"})
            return result
        result["changes"] = changes
        if update:
            updated_data = existing_data.copy()
            updated_data.update(pokemon_com_data)
            with open(metadata_path, mode="w", encoding="utf-8") as f:
                json.dump(updated_data, f, indent=2, ensure_ascii=False)
            result.update({"action": "updated", "status": "corrected"})
            for key, _change in changes.items():
                pass
        else:
            result.update({"action": "would_update", "status": "differences_found"})
            for key, _change in changes.items():
                pass
    except (OSError, json.JSONDecodeError) as e:
        result.update({"action": "error", "status": "read_error", "error": str(e)})
    return result


def check_pokemon_exists_on_official_site(session: requests.Session, pokemon_input: str) -> bool:
    url = build_pokemon_url(pokemon_input)
    try:
        response = session.head(url, timeout=15)
        return response.status_code == 200
    except requests.RequestException:
        try:
            response = session.get(url, timeout=15)
            if response.status_code == 404:
                return False
            if "Pardon Our Interruption" in response.text:
                return True
            soup = BeautifulSoup(response.text, "html.parser")
            has_pokemon_content = (
                soup.select_one("div.pokedex-pokemon-pagination-title")
                or soup.select_one("span.pokemon-number")
                or "#" in response.text
            )
            return has_pokemon_content
        except requests.RequestException:
            return True


def delete_pokemon_directory(directory_name: str, reason: str) -> bool:
    pokemon_directory = cli.pokemon_data_root() / directory_name
    if not pokemon_directory.exists():
        return True
    try:
        shutil.rmtree(pokemon_directory)
        return True
    except OSError:
        return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate Pokemon metadata against pokemon.com (SAFE: only touches metadata.json, never images/audio)"
    )
    cli.add_dry_run(parser, help="Show what would be done without making changes")
    cli.add_pokemon(
        parser,
        help="Single Pokemon name, directory name, or Pokedex number (e.g., 'Farfetch\\'d', 'farfetch_d', '83')",
    )
    parser.add_argument(
        "--batch",
        nargs="+",
        metavar="POKEMON",
        help="Batch mode: process multiple Pokemon with persistent browser session",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Actually update metadata.json files when differences are found (default: validate only)",
    )
    add_validation_args(parser)
    return parser.parse_args()


async def process_single_pokemon(
    pokemon_input: str,
    *,
    update: bool = False,
    dry_run: bool = False,
    browser_session: PersistentBrowserSession | None = None,
) -> dict[str, Any]:
    session = create_session()
    try:
        import cli
        from validation_utils import resolve_pokemon_query

        resolved_dir, message = resolve_pokemon_query(pokemon_input, cli.pokemon_data_root())
        if resolved_dir:
            directory_name = resolved_dir
            metadata_path = cli.pokemon_data_root() / resolved_dir / "metadata.json"
            if metadata_path.exists():
                import json

                with open(metadata_path) as f:
                    metadata = json.load(f)
                pokemon_for_url = metadata.get("name", pokemon_input)
            else:
                pokemon_for_url = pokemon_input
        else:
            if pokemon_input.isdigit():
                directory_name = None
                pokemon_for_url = pokemon_input
            else:
                normalized_name = normalize_input_name(pokemon_input)
                directory_name = get_directory_name_for_pokemon(normalized_name)
                pokemon_for_url = normalized_name
    except ImportError:
        if pokemon_input.isdigit():
            directory_name = None
            pokemon_for_url = pokemon_input
        else:
            normalized_name = normalize_input_name(pokemon_input)
            directory_name = get_directory_name_for_pokemon(normalized_name)
            pokemon_for_url = normalized_name
    pokemon_url = build_pokemon_url(pokemon_for_url)
    if not check_pokemon_exists_on_official_site(session, pokemon_for_url):
        if directory_name and not dry_run:
            known_tricky_cases = [
                "nidoran_female",
                "nidoran_male",
                "farfetch_d",
                "mr_mime",
                "ho_oh",
            ]
            if pokemon_input.lower() in known_tricky_cases:
                return {
                    "pokemon": pokemon_input,
                    "status": "skipped_deletion",
                    "reason": "safety check",
                }
            success = delete_pokemon_directory(directory_name, "not found on pokemon.com")
            if success:
                return {
                    "pokemon": pokemon_input,
                    "status": "deleted",
                    "reason": "not found on pokemon.com",
                }
            else:
                return {"pokemon": pokemon_input, "status": "delete_failed"}
        elif directory_name and dry_run:
            return {
                "pokemon": pokemon_input,
                "status": "would_delete",
                "reason": "not found on pokemon.com",
            }
        return {"pokemon": pokemon_input, "status": "not_found"}
    if browser_session:
        pokemon_data = await browser_session.extract_pokemon_data(pokemon_url)
    else:
        pokemon_data = extract_pokemon_data(session, pokemon_url, use_playwright_fallback=True)
    if not pokemon_data:
        return {"pokemon": pokemon_input, "status": "extraction_failed"}
    if not directory_name:
        directory_name = get_directory_name_for_pokemon(pokemon_data.name)
    if not dry_run:
        result = validate_and_update_metadata(pokemon_data, directory_name, update=update)
        result["pokemon"] = pokemon_input
        return result
    else:
        return {"pokemon": pokemon_input, "status": "dry_run", "directory": directory_name}


async def process_pokemon_batch(
    pokemon_list: list[str],
    *,
    update: bool = False,
    dry_run: bool = False,
    browser_session: PersistentBrowserSession | None = None,
) -> dict[str, Any]:
    total_pokemon = len(pokemon_list)
    results = {
        "total": total_pokemon,
        "processed": 0,
        "successful": 0,
        "failed": 0,
        "deleted": 0,
        "updated": 0,
        "validated": 0,
        "details": [],
    }
    if browser_session:
        for i, pokemon_input in enumerate(pokemon_list, 1):
            try:
                result = await process_single_pokemon(
                    pokemon_input, update=update, dry_run=dry_run, browser_session=browser_session
                )
                results["processed"] += 1
                results["details"].append(result)
                status = result.get("status", "unknown")
                if status in [
                    "correct",
                    "new_pokemon",
                    "corrected",
                    "would_create",
                    "would_update",
                    "differences_found",
                    "dry_run",
                ]:
                    results["successful"] += 1
                    if status in ["corrected", "new_pokemon"]:
                        results["updated"] += 1
                    elif status in ["correct", "dry_run"]:
                        results["validated"] += 1
                elif status in ["deleted", "would_delete"]:
                    results["deleted"] += 1
                else:
                    results["failed"] += 1
                if (
                    status == "correct"
                    or status in ["corrected", "new_pokemon"]
                    or status in ["would_update", "differences_found"]
                    or status == "dry_run"
                    or status in ["deleted", "would_delete"]
                ):
                    pass
                else:
                    pass
                if i < total_pokemon:
                    time.sleep(0.3)
            except Exception as e:
                results["failed"] += 1
                results["details"].append(
                    {"pokemon": pokemon_input, "status": "exception", "error": str(e)}
                )
    else:
        async with PersistentBrowserSession() as own_browser:
            for i, pokemon_input in enumerate(pokemon_list, 1):
                try:
                    result = await process_single_pokemon(
                        pokemon_input, update=update, dry_run=dry_run, browser_session=own_browser
                    )
                    results["processed"] += 1
                    results["details"].append(result)
                    status = result.get("status", "unknown")
                    if status in [
                        "correct",
                        "new_pokemon",
                        "corrected",
                        "would_create",
                        "would_update",
                        "differences_found",
                        "dry_run",
                    ]:
                        results["successful"] += 1
                        if status in ["corrected", "new_pokemon"]:
                            results["updated"] += 1
                        elif status in ["correct", "dry_run"]:
                            results["validated"] += 1
                    elif status in ["deleted", "would_delete"]:
                        results["deleted"] += 1
                    else:
                        results["failed"] += 1
                    if (
                        status == "correct"
                        or status in ["corrected", "new_pokemon"]
                        or status in ["would_update", "differences_found"]
                        or status == "dry_run"
                        or status in ["deleted", "would_delete"]
                    ):
                        pass
                    else:
                        pass
                    if i < total_pokemon:
                        time.sleep(0.3)
                except Exception as e:
                    results["failed"] += 1
                    results["details"].append(
                        {"pokemon": pokemon_input, "status": "exception", "error": str(e)}
                    )
    return results


def validate_before_scraping(args: argparse.Namespace) -> bool:
    logger = get_script_logger()
    if args.skip_validation:
        logger.info("⏭️  Skipping validation checks")
        return True
    logger.info("🧪 Pre-flight validation for pokemon.com scraper...")
    session = create_session()
    test_pokemon = get_sample_pokemon()
    logger.info(
        f"  🌐 Testing pokemon.com with {len(test_pokemon)} edge cases (with Playwright fallback)..."
    )
    success_count = 0
    accuracy_count = 0
    total_testable = 0
    for pokemon in test_pokemon:
        try:
            real_metadata = get_real_pokemon_metadata(pokemon)
            if not real_metadata:
                logger.info(f"    ⚠️  {pokemon}: No real metadata found, skipping accuracy test")
                continue
            total_testable += 1
            url = build_pokemon_url(pokemon)
            exists = check_pokemon_exists_on_official_site(session, pokemon)
            if not exists:
                logger.info(f"    ❌ {pokemon}: Not found on pokemon.com")
                continue
            pokemon_data = extract_pokemon_data(session, url, use_playwright_fallback=True)
            if not pokemon_data:
                logger.info(f"    ❌ {pokemon}: Extraction failed even with Playwright")
                continue
            success_count += 1
            scraped_dict = {
                "pokedex_number": pokemon_data.pokedex_number,
                "name": pokemon_data.name,
                "types": pokemon_data.types,
            }
            differences = compare_scraped_vs_real_data(scraped_dict, real_metadata)
            if not differences:
                accuracy_count += 1
                logger.info(f"    ✅ {pokemon}: Scraped data matches real metadata perfectly")
            else:
                logger.info(f"    ⚠️  {pokemon}: Scraped but data differs from real metadata:")
                for diff in differences:
                    logger.info(f"      - {diff}")
        except Exception as e:
            logger.info(f"    💥 {pokemon}: Error - {e}")
    success_rate = success_count / len(test_pokemon) if test_pokemon else 0
    accuracy_rate = accuracy_count / total_testable if total_testable > 0 else 0
    logger.info(
        f"  📊 Extraction results: {success_count}/{len(test_pokemon)} successful ({success_rate:.1%})"
    )
    logger.info(
        f"  🎯 Accuracy results: {accuracy_count}/{total_testable} exact matches ({accuracy_rate:.1%})"
    )
    if success_count > 0 and accuracy_rate >= 0.7:
        logger.info(
            f"  ✅ Pokemon.com validation passed - {success_count} extractions, {accuracy_rate:.1%} accurate!"
        )
    elif success_count > 0:
        logger.info(f"  ⚠️  Pokemon.com extraction works but accuracy is low ({accuracy_rate:.1%})")
        logger.info("  ℹ️  This may indicate website changes or scraping logic issues")
    else:
        logger.info("  ⚠️  No successful extractions, but main script may work with Playwright")
    logger.info("  ✅ Pre-flight validation passed")
    return True


def main() -> None:
    args = parse_args()
    if args.validation_only:
        success = validate_before_scraping(args)
        if success:
            return
        else:
            exit(1)
    if not args.pokemon and not args.batch:
        exit(1)
    if not validate_before_scraping(args):
        if not should_proceed_after_validation_failure(args.force):
            exit(1)
    cli.pokemon_data_root()
    if args.dry_run:
        pass
    if args.batch:

        async def run_batch() -> dict[str, Any]:
            return await process_pokemon_batch(args.batch, update=args.update, dry_run=args.dry_run)

        batch_results = asyncio.run(run_batch())
        if batch_results["failed"] > 0:
            for detail in batch_results["details"]:
                if detail.get("status") not in [
                    "correct",
                    "corrected",
                    "new_pokemon",
                    "deleted",
                    "would_delete",
                    "would_update",
                    "differences_found",
                    "dry_run",
                ]:
                    pass
    else:

        async def run_single() -> dict[str, Any]:
            return await process_single_pokemon(
                args.pokemon, update=args.update, dry_run=args.dry_run
            )

        result = asyncio.run(run_single())
        status = result.get("status", "unknown")
        if (
            status == "correct"
            or status == "new_pokemon"
            or status == "corrected"
            or status == "no_directory"
            or status == "read_error"
            or status in ["deleted", "would_delete"]
            or status == "dry_run"
        ):
            pass
        else:
            pass
        if status in ["corrected", "new_pokemon"]:
            pass


if __name__ == "__main__":
    main()
