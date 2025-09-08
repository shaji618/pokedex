#!/usr/bin/env python3
"""Fast sprite downloader from pokemondb.net/sprites."""

import argparse
import asyncio
import re
import sys
from pathlib import Path

import aiohttp
import cli
from bs4 import BeautifulSoup
from script_logger import get_script_logger
from validation_utils import add_validation_args, should_proceed_after_validation_failure


async def get_all_pokemon_sprites() -> dict[str, str]:
    """Scrape pokemondb.net/sprites to get all Pokemon sprite URLs."""
    logger = get_script_logger()
    logger.substep("🕷️  Scraping pokemondb.net/sprites...")

    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

    async with (
        aiohttp.ClientSession(headers=headers) as session,
        session.get("https://pokemondb.net/sprites") as response,
    ):
        if response.status != 200:
            raise Exception(f"Failed to fetch sprites page: {response.status}")

        html = await response.text()

    soup = BeautifulSoup(html, "html.parser")
    pokemon_sprites = {}

    # Find all Pokemon sprite links - they're in the format:
    # <a href="/pokedex/bulbasaur"><img src="..." alt="Bulbasaur"></a>
    sprite_links = soup.find_all("img", src=re.compile(r"/sprites/"))

    for img in sprite_links:
        # Extract Pokemon name from alt text
        pokemon_name = img.get("alt", "").strip()
        if not pokemon_name:
            continue

        # Get the sprite URL
        sprite_url = img.get("src", "")
        if not sprite_url.startswith("http"):
            sprite_url = f"https://img.pokemondb.net{sprite_url}"

        # Convert name to directory format using centralized function
        try:
            from validation_utils import normalize_pokemon_name
        except ImportError:
            from scripts.validation_utils import normalize_pokemon_name

        dir_name = normalize_pokemon_name(pokemon_name, format_type="directory")

        if dir_name and sprite_url:
            pokemon_sprites[dir_name] = sprite_url

    logger.success(f"✅ Found {len(pokemon_sprites)} Pokemon sprites")
    return pokemon_sprites


async def download_sprite(
    session: aiohttp.ClientSession, pokemon_name: str, sprite_url: str, output_path: Path
) -> tuple[str, bool, str]:
    """Download a single sprite."""
    try:
        async with session.get(sprite_url) as response:
            if response.status != 200:
                return pokemon_name, False, f"HTTP {response.status}"

            content = await response.read()

            # Verify it's a valid image
            if not content.startswith(b"\x89PNG") and not content.startswith(b"\xff\xd8\xff"):
                return pokemon_name, False, "Invalid image format"

            # Write to file
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(content)

            return pokemon_name, True, f"Downloaded {len(content)} bytes"

    except Exception as e:
        return pokemon_name, False, str(e)


async def download_all_sprites(
    pokemon_sprites: dict[str, str], pokemon_data_dir: Path, *, overwrite: bool = False
) -> None:
    """Download all sprites concurrently."""
    logger = get_script_logger()

    # Check what's already downloaded
    to_download = []
    already_exist = 0

    for pokemon_name, sprite_url in pokemon_sprites.items():
        sprite_path = pokemon_data_dir / pokemon_name / "sprite.png"

        if sprite_path.exists() and not overwrite:
            already_exist += 1
            continue

        to_download.append((pokemon_name, sprite_url, sprite_path))

    if already_exist > 0:
        logger.substep(f"⏭️  Skipping {already_exist} existing sprites")

    if not to_download:
        logger.success("✅ All sprites already downloaded!")
        return

    logger.info(f"📥 Downloading {len(to_download)} sprites...")

    # Download concurrently with reasonable limits
    connector = aiohttp.TCPConnector(limit=10, limit_per_host=5)
    timeout = aiohttp.ClientTimeout(total=30)
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

    async with aiohttp.ClientSession(
        connector=connector, timeout=timeout, headers=headers
    ) as session:
        # Process in chunks to avoid overwhelming the server
        chunk_size = 20
        successful = 0
        failed = 0

        for i in range(0, len(to_download), chunk_size):
            chunk = to_download[i : i + chunk_size]

            # Download chunk concurrently
            tasks = [
                download_sprite(session, pokemon_name, sprite_url, sprite_path)
                for pokemon_name, sprite_url, sprite_path in chunk
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


def get_existing_pokemon_dirs(pokemon_data_dir: Path) -> set[str]:
    """Get list of existing Pokemon directories."""
    if not pokemon_data_dir.exists():
        return set()

    return {d.name for d in pokemon_data_dir.iterdir() if d.is_dir()}


async def validate_before_scraping() -> bool:
    """Quick validation that pokemondb.net is accessible."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }

        async with (
            aiohttp.ClientSession(headers=headers) as session,
            session.get("https://pokemondb.net/sprites") as response,
        ):
            return response.status == 200
    except Exception:
        return False


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Download Pokemon sprites from pokemondb.net/sprites",
        epilog="Downloads all sprites concurrently for maximum speed.",
    )

    cli.add_dry_run(parser, help="Show what would be downloaded without downloading")
    cli.add_overwrite(parser, help="Re-download existing sprites")
    cli.add_pokemon(parser, help="Download sprite for specific Pokemon only")
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
            logger.error("❌ pokemondb.net is not accessible")
            if not should_proceed_after_validation_failure(args.force):
                sys.exit(1)

    # Get all Pokemon sprites from the website
    pokemon_sprites = await get_all_pokemon_sprites()

    # Filter if specific Pokemon requested
    if args.pokemon:
        target_name = args.pokemon.lower().replace("-", "_").replace(" ", "_")
        filtered_sprites = {k: v for k, v in pokemon_sprites.items() if target_name in k.lower()}

        if not filtered_sprites:
            logger.error(f"❌ No sprites found matching '{args.pokemon}'")
            # Show available options
            matches = [k for k in pokemon_sprites if args.pokemon.lower() in k.lower()]
            if matches:
                logger.substep(f"💡 Did you mean: {', '.join(matches[:5])}")
            sys.exit(1)

        pokemon_sprites = filtered_sprites
        logger.info(f"🎯 Targeting {len(pokemon_sprites)} Pokemon matching '{args.pokemon}'")

    if args.dry_run:
        logger.info(f"🔍 DRY RUN: Would download {len(pokemon_sprites)} sprites")

        for pokemon_name in sorted(pokemon_sprites):
            sprite_path = pokemon_data_dir / pokemon_name / "sprite.png"
            if sprite_path.exists() and not args.overwrite:
                logger.substep(f"⏭️  {pokemon_name}: [skip] exists")
            else:
                logger.substep(f"📥 {pokemon_name}: would download")
        return

    # Download sprites
    await download_all_sprites(pokemon_sprites, pokemon_data_dir, overwrite=args.overwrite)


if __name__ == "__main__":
    asyncio.run(main())
