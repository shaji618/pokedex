#!/usr/bin/env python3
"""Download hunt assets (sprites and audio) for Pokemon Hunt game."""

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

import aiohttp
import cli
from bs4 import BeautifulSoup
from script_logger import get_script_logger
from validation_utils import (
    add_validation_args,
    find_pokemon_directory_robust,
    normalize_pokemon_name,
    should_proceed_after_validation_failure,
)


# URLs
SPRITE_INDEX_URL = "https://projectpokemon.org/home/docs/spriteindex_148"
AUDIO_BASE_URL = "https://play.pokemonshowdown.com/audio/cries/"

# Base URL for Project Pokemon pages (we'll extract relative URLs from sprite index)
PROJECT_POKEMON_BASE = "https://projectpokemon.org"


async def discover_generation_pages(session: aiohttp.ClientSession) -> list[str]:
    """Scrape sprite index to find all '3D Models: Generation X Pokémon' pages.

    Returns list of full URLs to scrape.
    """
    logger = get_script_logger()
    logger.substep("🔍 Discovering generation pages from sprite index...")

    async with session.get(SPRITE_INDEX_URL) as response:
        if response.status != 200:
            raise Exception(f"Failed to fetch sprite index: {response.status}")
        html = await response.text()

    soup = BeautifulSoup(html, "html.parser")
    generation_urls = []

    # Find all links matching "3D Models: Generation X Pokémon" pattern
    for link in soup.find_all("a", href=True):
        text = link.get_text(strip=True)
        if re.match(r"3D Models: Generation \d+ Pokémon", text):
            href = link["href"]
            # Convert relative URL to absolute
            if href.startswith("/"):
                href = PROJECT_POKEMON_BASE + href
            generation_urls.append(href)
            logger.substep(f"📄 Found: {text} -> {href}")

    logger.success(f"✅ Found {len(generation_urls)} generation pages")
    return generation_urls


async def scrape_generation_page(
    session: aiohttp.ClientSession, url: str, target_pokemon: set[str] | None = None
) -> dict[str, list[tuple[str, str, str]]]:
    """Scrape a single generation page for Pokemon sprites.

    Returns: {pokemon_name: [(sprite_url, modifier, file_ext), ...]}
    """
    logger = get_script_logger()
    generation = re.search(r"generation-(\d+)", url.lower())
    gen_num = generation.group(1) if generation else "?"
    logger.substep(f"🕷️  Scraping Generation {gen_num} sprites from: {url}")

    async with session.get(url) as response:
        if response.status != 200:
            logger.substep(f"❌ Failed to fetch {url}: {response.status}")
            return {}
        html = await response.text()

    soup = BeautifulSoup(html, "html.parser")
    pokemon_sprites = {}

    # Find all image tags - Project Pokemon uses img tags with src pointing to sprites
    img_count = 0
    for img in soup.find_all("img", src=True):
        src = img["src"]

        # Skip non-sprite images (headers, icons, etc.)
        if not src.endswith((".gif", ".png")):
            continue

        # Extract pokemon name from image alt text or filename first
        alt_text = img.get("alt", "")
        pokemon_name = extract_pokemon_name_from_alt_or_url(alt_text, src)

        if not pokemon_name:
            continue

        # Convert to directory name format
        dir_name = normalize_pokemon_name_to_directory(pokemon_name)

        # If we're targeting specific Pokemon, skip irrelevant ones early
        if target_pokemon and dir_name not in target_pokemon:
            continue

        img_count += 1
        logger.substep(f"🖼️  Found target image {img_count}: {src}")

        # Extract modifier and file extension from URL
        modifier, file_ext = extract_modifier_and_extension(src)

        if dir_name not in pokemon_sprites:
            pokemon_sprites[dir_name] = []

        # Convert relative URL to absolute
        if src.startswith("/"):
            src = PROJECT_POKEMON_BASE + src

        pokemon_sprites[dir_name].append((src, modifier, file_ext))

        modifier_text = f" ({modifier})" if modifier else ""
        logger.substep(f"✅ {pokemon_name} -> {dir_name}{modifier_text}: {src}")

    if target_pokemon:
        target_found = len([p for p in pokemon_sprites if p in target_pokemon])
        if target_found > 0:
            target_sprite_count = sum(
                len(pokemon_sprites[p]) for p in pokemon_sprites if p in target_pokemon
            )
            logger.success(
                f"✅ Found {target_sprite_count} sprites for target Pokemon in Gen {gen_num}"
            )
        else:
            logger.substep(f"⏭️  No target Pokemon found in Gen {gen_num}")
    else:
        logger.success(
            f"✅ Found sprites for {len(pokemon_sprites)} Pokemon in Gen {gen_num} ({img_count} total images)"
        )
    return pokemon_sprites


def extract_modifier_and_extension(url: str) -> tuple[str, str]:
    """Extract modifier (shiny, mega, etc.) and file extension from sprite URL.

    Returns: (modifier, file_ext) where modifier is empty string for "normal".
    """
    # Look for patterns in URL that indicate variants
    modifiers = ["shiny", "mega", "megax", "megay", "alola", "galar", "hisui", "paldea"]

    url_lower = url.lower()
    found_modifier = ""

    for modifier in modifiers:
        if modifier in url_lower:
            found_modifier = modifier
            break

    # Extract file extension
    file_ext = Path(url).suffix

    return found_modifier, file_ext


def extract_pokemon_name_from_alt_or_url(alt_text: str, url: str) -> str:
    """Extract pokemon name from image alt text or URL."""
    # Try alt text first
    if alt_text:
        # Clean up alt text - remove common suffixes and artifacts
        name = alt_text.strip()
        # Remove things like "sprite", "front", "back", etc.
        name = re.sub(r"\b(sprite|front|back|gif|png)\b", "", name, flags=re.IGNORECASE)
        name = re.sub(r"[^a-zA-Z\s]", " ", name)
        name = " ".join(name.split())  # Normalize whitespace
        if name:
            return name

    # Fall back to extracting from URL
    filename = Path(url).stem
    # Remove common prefixes/suffixes and numbers
    name = re.sub(r"[^a-zA-Z]", " ", filename)
    name = " ".join(name.split())  # Normalize whitespace

    return name if name else ""


def normalize_pokemon_name_to_directory(pokemon_name: str) -> str:
    """Convert Pokemon name to directory format using centralized validation_utils function.

    Maps all Pokemon variants (shiny, mega, regional forms, etc.) to their base Pokemon name
    so all assets go into the same hunt_assets folder.
    """
    # First normalize the name
    normalized = normalize_pokemon_name(pokemon_name, format_type="directory")

    # Extract base Pokemon name (everything before first underscore)
    # This maps variants like "charizard_megax", "pikachu_f", "vulpix_alola" to base names
    base_name = normalized.split("_")[0]

    return base_name


async def scrape_pokemon_audio(
    session: aiohttp.ClientSession, target_pokemon: str | None = None
) -> dict[str, list[tuple[str, str]]]:
    """Scrape Pokemon Showdown for all audio cries.

    Returns: {pokemon_name: [(url, filename), ...]}
    """
    logger = get_script_logger()
    if target_pokemon:
        logger.substep(f"🕷️  Scraping Pokemon Showdown audio cries for {target_pokemon}...")
    else:
        logger.substep("🕷️  Scraping Pokemon Showdown audio cries...")

    async with session.get(AUDIO_BASE_URL) as response:
        if response.status != 200:
            raise Exception(f"Failed to fetch audio directory: {response.status}")
        html = await response.text()

    soup = BeautifulSoup(html, "html.parser")
    pokemon_audio = {}
    numeric_files = []  # Store numeric files for later processing

    # Find all audio file links
    audio_count = 0
    matched_count = 0
    for link in soup.find_all("a", href=True):
        href = link["href"]
        if not href.endswith((".mp3", ".wav", ".ogg")):
            continue

        audio_count += 1
        filename = href

        # Map filename to pokemon directory name
        pokemon_dir = map_audio_filename_to_pokemon_directory(filename)

        # Early filtering - skip if we're targeting a specific Pokemon and this doesn't match
        if target_pokemon:
            target_normalized = target_pokemon.lower().replace("-", "_").replace(" ", "_")
            if pokemon_dir and target_normalized not in pokemon_dir.lower():
                continue  # Skip non-matching Pokemon
            elif not pokemon_dir:
                # For numeric files, we'll check them later with pokedex mapping
                base_name = Path(filename).stem
                if base_name.isdigit():
                    numeric_files.append((AUDIO_BASE_URL + href, filename))
                continue

        matched_count += 1
        if not target_pokemon or matched_count <= 10:  # Limit verbose logging when targeting
            logger.substep(f"🔊 Found audio {matched_count}: {filename}")

        full_url = AUDIO_BASE_URL + href if not href.startswith("http") else href

        if pokemon_dir:
            if pokemon_dir not in pokemon_audio:
                pokemon_audio[pokemon_dir] = []
            pokemon_audio[pokemon_dir].append((full_url, filename))
            if not target_pokemon or matched_count <= 10:
                logger.substep(f"✅ Mapped {filename} -> {pokemon_dir}")
        else:
            # Store numeric files for later processing with pokedex mapping
            numeric_files.append((full_url, filename))
            if not target_pokemon or matched_count <= 10:
                logger.substep(f"📋 Stored numeric file for later mapping: {filename}")

    if target_pokemon and matched_count > 10:
        logger.substep(f"... (found {matched_count} total matches, showing first 10)")

    if target_pokemon:
        total_found = len(pokemon_audio) + len(numeric_files)
        logger.success(f"✅ Found {total_found} audio files for target Pokemon")
    else:
        logger.success(
            f"✅ Found {len(pokemon_audio)} named audio files, {len(numeric_files)} numeric files"
        )
    return pokemon_audio, numeric_files


def map_audio_filename_to_pokemon_directory(filename: str) -> str:
    """Map audio filename to pokemon directory name.

    Handles both named files and numeric files.
    """
    base_name = Path(filename).stem

    # If filename contains pokemon name, extract it
    if not base_name.isdigit():
        return normalize_pokemon_name_to_directory(base_name)

    # For numeric files like "001.mp3", return empty string for later processing
    return ""


def get_pokemon_generation(pokemon_query: str, pokemon_data_dir: Path) -> int:
    """Get the generation number for a specific Pokemon from their metadata.json."""
    pokemon_dir = find_pokemon_directory_robust(pokemon_query, pokemon_data_dir, verbose=False)

    if not pokemon_dir:
        return None

    metadata_path = pokemon_dir / "metadata.json"
    if not metadata_path.exists():
        return None

    try:
        with open(metadata_path, encoding="utf-8") as f:
            metadata = json.load(f)
            return metadata.get("generation")
    except (json.JSONDecodeError, KeyError):
        return None


def load_pokemon_pokedex_mapping(pokemon_data_dir: Path) -> dict[int, str]:
    """Load mapping of pokedex_number to directory name from metadata.json files."""
    logger = get_script_logger()
    logger.substep("📚 Loading Pokedex number mappings from metadata.json files...")

    mapping = {}

    for pokemon_dir in pokemon_data_dir.iterdir():
        if not pokemon_dir.is_dir() or pokemon_dir.name.startswith("."):
            continue

        metadata_path = pokemon_dir / "metadata.json"
        if metadata_path.exists():
            try:
                with open(metadata_path, encoding="utf-8") as f:
                    metadata = json.load(f)
                    pokedex_num = metadata.get("pokedex_number")
                    if pokedex_num:
                        mapping[int(pokedex_num)] = pokemon_dir.name
            except (json.JSONDecodeError, ValueError, KeyError):
                continue

    logger.success(f"✅ Loaded {len(mapping)} Pokedex number mappings")
    return mapping


async def download_assets(
    sprites: dict[str, list[tuple[str, str, str]]],
    audio: dict[str, list[tuple[str, str]]],
    pokemon_data_dir: Path,
    overwrite: bool = False,
    dry_run: bool = False,
) -> None:
    """Download all sprites and audio to hunt_assets/ directories."""
    logger = get_script_logger()

    # Validate that we only download for canonical Pokemon
    from scrape_serebii_data import fetch_index, parse_species, normalize_name
    import requests

    try:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"})

        html = fetch_index(session)
        species_list = parse_species(html)
        canonical_names = {normalize_name(sp.name) for sp in species_list}

        # Filter out non-canonical Pokemon
        original_sprite_count = len(sprites)
        original_audio_count = len(audio)

        sprites = {k: v for k, v in sprites.items() if k in canonical_names}
        audio = {k: v for k, v in audio.items() if k in canonical_names}

        filtered_sprite_count = original_sprite_count - len(sprites)
        filtered_audio_count = original_audio_count - len(audio)

        if filtered_sprite_count > 0 or filtered_audio_count > 0:
            logger.substep(f"🔍 Filtered out {filtered_sprite_count} non-canonical sprite Pokemon")
            logger.substep(f"🔍 Filtered out {filtered_audio_count} non-canonical audio Pokemon")

        logger.substep(f"✅ Validated: Only downloading for canonical Pokemon")

    except Exception as e:
        logger.warning(f"⚠️  Could not validate canonical Pokemon: {e}")
        logger.substep("Proceeding without validation filter...")

    # Combine all downloads into one list for efficient processing
    downloads = []

    # Add sprite downloads
    logger.substep("📋 Preparing sprite download list...")
    for pokemon_name, sprite_list in sprites.items():
        hunt_assets_dir = pokemon_data_dir / pokemon_name / "hunt_assets"

        for sprite_url, modifier, file_ext in sprite_list:
            # Generate filename: pokemon_modifier.ext (skip modifier for "normal")
            if modifier and modifier != "normal":
                filename = f"{pokemon_name}_{modifier}{file_ext}"
            else:
                filename = f"{pokemon_name}{file_ext}"

            target_path = hunt_assets_dir / filename
            downloads.append(("sprite", pokemon_name, sprite_url, target_path))

    # Add audio downloads
    logger.substep("📋 Preparing audio download list...")
    for pokemon_name, audio_list in audio.items():
        hunt_assets_dir = pokemon_data_dir / pokemon_name / "hunt_assets"

        for audio_url, original_filename in audio_list:
            target_path = hunt_assets_dir / original_filename
            downloads.append(("audio", pokemon_name, audio_url, target_path))

    logger.info(f"📦 Total assets to process: {len(downloads)}")

    if dry_run:
        logger.info(f"🔍 DRY RUN: Would download {len(downloads)} assets")

        # Group by pokemon for cleaner output
        by_pokemon = {}
        for asset_type, pokemon_name, url, target_path in downloads:
            if pokemon_name not in by_pokemon:
                by_pokemon[pokemon_name] = {"sprite": [], "audio": []}
            by_pokemon[pokemon_name][asset_type].append((url, target_path))

        for pokemon_name in sorted(by_pokemon.keys()):
            data = by_pokemon[pokemon_name]
            sprite_count = len(data["sprite"])
            audio_count = len(data["audio"])

            if sprite_count > 0 or audio_count > 0:
                logger.substep(
                    f"🎯 {pokemon_name}: {sprite_count} sprites, {audio_count} audio files"
                )

                for url, target_path in data["sprite"]:
                    if target_path.exists() and not overwrite:
                        logger.substep(f"    ⏭️  [skip] {target_path.name} (exists)")
                    else:
                        relative_path = target_path.relative_to(Path.cwd())
                        logger.substep(f"    📥 [download] {target_path.name} -> {relative_path}")

                for url, target_path in data["audio"]:
                    if target_path.exists() and not overwrite:
                        logger.substep(f"    ⏭️  [skip] {target_path.name} (exists)")
                    else:
                        relative_path = target_path.relative_to(Path.cwd())
                        logger.substep(f"    🔊 [download] {target_path.name} -> {relative_path}")
        return

    # Filter existing files
    to_download = []
    skipped = 0
    for item in downloads:
        asset_type, pokemon_name, url, target_path = item
        if target_path.exists() and not overwrite:
            skipped += 1
            continue
        to_download.append(item)

    if skipped > 0:
        logger.substep(f"⏭️  Skipping {skipped} existing files")

    if not to_download:
        logger.success("✅ All assets already downloaded!")
        return

    logger.info(f"📥 Downloading {len(to_download)} assets...")

    # Download with rate limiting (same pattern as download_sprites.py)
    connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
    timeout = aiohttp.ClientTimeout(total=30)
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

    async with aiohttp.ClientSession(
        connector=connector, timeout=timeout, headers=headers
    ) as session:
        # Process in chunks
        chunk_size = 20
        successful = 0
        failed = 0

        for i in range(0, len(to_download), chunk_size):
            chunk = to_download[i : i + chunk_size]

            tasks = [
                download_single_asset(session, asset_type, pokemon_name, url, target_path)
                for asset_type, pokemon_name, url, target_path in chunk
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, Exception):
                    failed += 1
                    logger.substep(f"❌ Error: {result}")
                else:
                    pokemon_name, success, message = result
                    if success:
                        successful += 1
                        logger.substep(f"✅ {pokemon_name}: {message}")
                    else:
                        failed += 1
                        logger.substep(f"❌ {pokemon_name}: {message}")

            # Brief pause between chunks
            if i + chunk_size < len(to_download):
                await asyncio.sleep(0.5)

    logger.success(f"🎉 Download complete! ✅ {successful} success, ❌ {failed} failed")


async def download_single_asset(
    session: aiohttp.ClientSession, asset_type: str, pokemon_name: str, url: str, target_path: Path
) -> tuple[str, bool, str]:
    """Download a single asset file."""
    try:
        async with session.get(url) as response:
            if response.status != 200:
                return pokemon_name, False, f"HTTP {response.status}"

            content = await response.read()

            # Create directory
            target_path.parent.mkdir(parents=True, exist_ok=True)

            # Write file
            with open(target_path, "wb") as f:
                f.write(content)

            return pokemon_name, True, f"Downloaded {target_path.name} ({len(content)} bytes)"

    except Exception as e:
        return pokemon_name, False, str(e)


async def validate_before_scraping() -> bool:
    """Quick validation that target sites are accessible."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }

        async with aiohttp.ClientSession(headers=headers) as session:
            # Test sprite index
            async with session.get(SPRITE_INDEX_URL) as response:
                if response.status != 200:
                    return False

            # Test audio directory
            async with session.get(AUDIO_BASE_URL) as response:
                if response.status != 200:
                    return False

        return True
    except Exception:
        return False


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Download hunt assets (sprites and audio) for Pokemon Hunt game",
        epilog="Auto-discovers generation pages and downloads all available sprites and audio.",
    )

    # Asset type filters
    parser.add_argument("--sprites-only", action="store_true", help="Download only sprites")
    parser.add_argument("--audio-only", action="store_true", help="Download only audio")

    # Standard CLI helpers
    cli.add_dry_run(parser, help="Show what would be downloaded without downloading")
    cli.add_overwrite(parser, help="Re-download existing assets")
    cli.add_pokemon(parser, help="Download assets for specific Pokemon only")
    cli.add_debug(parser, help="Save debug artifacts for troubleshooting")
    add_validation_args(parser)

    return parser.parse_args()


async def main() -> None:
    """Main entry point."""
    args = parse_args()
    logger = get_script_logger()

    if args.validation_only:
        success = await validate_before_scraping()
        sys.exit(0 if success else 1)

    pokemon_data_dir = cli.pokemon_data_root()

    if not args.skip_validation:
        if not await validate_before_scraping():
            logger.error("❌ Target websites are not accessible")
            if not should_proceed_after_validation_failure(args.force):
                sys.exit(1)

    # Setup session
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

    all_sprites = {}
    all_audio = {}

    async with aiohttp.ClientSession(headers=headers) as session:
        # Download sprites
        if not args.audio_only:
            logger.info("🎨 Starting sprite discovery and scraping...")

            # Create target set for filtering (convert to directory name format)
            target_pokemon = None
            if args.pokemon:
                target_pokemon = {normalize_pokemon_name_to_directory(args.pokemon)}
                logger.substep(f"🎯 Targeting sprites for: {args.pokemon}")

            # If targeting specific Pokemon, try to find their generation to limit scraping
            if args.pokemon:
                target_generation = get_pokemon_generation(args.pokemon, pokemon_data_dir)
                if target_generation:
                    logger.substep(
                        f"🎯 {args.pokemon} is from Generation {target_generation} - limiting sprite search"
                    )
                    generation_urls = await discover_generation_pages(session)
                    # Filter to just the target generation
                    filtered_urls = [
                        url
                        for url in generation_urls
                        if f"generation-{target_generation}" in url.lower()
                    ]
                    if filtered_urls:
                        generation_urls = filtered_urls
                    else:
                        logger.substep(
                            f"⚠️  Couldn't find Generation {target_generation} page, scraping all generations"
                        )
                else:
                    logger.substep(
                        f"⚠️  Couldn't determine generation for {args.pokemon}, scraping all generations"
                    )
                    generation_urls = await discover_generation_pages(session)
            else:
                generation_urls = await discover_generation_pages(session)

            for url in generation_urls:
                sprites = await scrape_generation_page(session, url, target_pokemon)
                # Merge with existing sprites
                for pokemon_name, sprite_list in sprites.items():
                    if pokemon_name not in all_sprites:
                        all_sprites[pokemon_name] = []
                    all_sprites[pokemon_name].extend(sprite_list)

            sprite_count = sum(len(v) for v in all_sprites.values())
            if target_pokemon:
                logger.success(f"✅ Found {sprite_count} sprites for {args.pokemon}")
            else:
                logger.success(
                    f"✅ Total sprites found: {sprite_count} across {len(all_sprites)} Pokemon"
                )

        # Download audio
        if not args.sprites_only:
            logger.info("🔊 Starting audio discovery and scraping...")
            # Pass target pokemon for early filtering
            target_for_audio = args.pokemon if args.pokemon else None
            audio_data, numeric_files = await scrape_pokemon_audio(session, target_for_audio)

            # Handle numeric audio files by mapping to pokedex numbers
            pokedex_mapping = load_pokemon_pokedex_mapping(pokemon_data_dir)

            # Process named audio files
            all_audio.update(audio_data)

            # Process numeric files
            numeric_mapped = 0
            for audio_url, original_filename in numeric_files:
                base_name = Path(original_filename).stem
                if base_name.isdigit():
                    pokedex_num = int(base_name)
                    if pokedex_num in pokedex_mapping:
                        pokemon_dir = pokedex_mapping[pokedex_num]
                        if pokemon_dir not in all_audio:
                            all_audio[pokemon_dir] = []
                        all_audio[pokemon_dir].append((audio_url, original_filename))
                        numeric_mapped += 1
                        logger.substep(f"📋 Mapped #{pokedex_num:03d}.mp3 -> {pokemon_dir}")

            audio_count = sum(len(v) for v in all_audio.values())
            if target_for_audio:
                logger.success(f"✅ Found {audio_count} audio files for {args.pokemon}")
            else:
                logger.success(
                    f"✅ Total audio found: {audio_count} files across {len(all_audio)} Pokemon ({numeric_mapped} numeric files mapped)"
                )

    # Filter by specific pokemon if requested
    if args.pokemon:
        target_name = args.pokemon.lower().replace("-", "_").replace(" ", "_")

        filtered_sprites = {k: v for k, v in all_sprites.items() if target_name in k.lower()}
        filtered_audio = {k: v for k, v in all_audio.items() if target_name in k.lower()}

        if not filtered_sprites and not filtered_audio:
            logger.error(f"❌ No assets found matching '{args.pokemon}'")
            # Show available options
            all_pokemon = set(list(all_sprites.keys()) + list(all_audio.keys()))
            matches = [k for k in all_pokemon if args.pokemon.lower() in k.lower()]
            if matches:
                logger.substep(f"💡 Did you mean: {', '.join(sorted(matches)[:5])}")
            sys.exit(1)

        all_sprites = filtered_sprites
        all_audio = filtered_audio

        logger.info(
            f"🎯 Targeting Pokemon matching '{args.pokemon}': {len(all_sprites)} with sprites, {len(all_audio)} with audio"
        )

    # Download everything
    await download_assets(
        all_sprites, all_audio, pokemon_data_dir, overwrite=args.overwrite, dry_run=args.dry_run
    )


if __name__ == "__main__":
    asyncio.run(main())
