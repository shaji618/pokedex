from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from typing import Any

import cli
import requests
from download_pokemon_logo_font_names import process_all as generate_pokemon_logos
from scrape_serebii_data import fetch_index, normalize_name, parse_species
from script_logger import get_script_logger


def get_canonical_pokemon_data() -> dict[str, dict]:
    try:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            }
        )
        html = fetch_index(session)
        species_list = parse_species(html)
        canonical_data = {}
        for sp in species_list:
            normalized_name = normalize_name(sp.name)
            canonical_data[normalized_name] = {
                "name": sp.name,
                "dex": sp.dex,
                "types": cli.normalize_types(sp.types),
                "normalized_name": normalized_name,
            }
        return canonical_data
    except Exception as e:
        logger = get_script_logger()
        logger.error(f"❌ Failed to get canonical data: {e}")
        return {}


def verify_and_cleanup_pokemon_data(dry_run: bool = False) -> tuple[set[str], set[str]]:
    logger = get_script_logger()
    logger.info("🔍 Step 0: Smart verification and cleanup...")
    logger.info("  📊 Analyzing existing Pokemon data against Serebii canonical source")
    canonical_data = get_canonical_pokemon_data()
    if not canonical_data:
        logger.error("  ❌ Could not get canonical data - skipping smart verification")
        return get_existing_pokemon_directories(), set()
    logger.info(f"  ✅ Retrieved canonical data for {len(canonical_data)} Pokemon from Serebii")
    existing_dirs = get_existing_pokemon_directories()
    logger.info(f"  📁 Found {len(existing_dirs)} existing Pokemon directories")
    valid_dirs = set()
    corrupted_dirs = set()
    for dir_name in existing_dirs:
        if dir_name in canonical_data:
            valid_dirs.add(dir_name)
        else:
            corrupted_dirs.add(dir_name)
    logger.info(f"  ✅ Valid directories: {len(valid_dirs)}")
    logger.info(f"  🚨 Corrupted directories: {len(corrupted_dirs)}")
    removed_dirs = set()
    if corrupted_dirs:
        logger.info(f"  🧹 {'Would remove' if dry_run else 'Removing'} corrupted directories...")
        for dir_name in corrupted_dirs:
            dir_path = cli.pokemon_data_root() / dir_name
            if dry_run:
                logger.info(f"    🔍 Would delete: {dir_name}")
                removed_dirs.add(dir_name)
            else:
                try:
                    import shutil

                    shutil.rmtree(dir_path)
                    logger.info(f"    ✅ Deleted: {dir_name}")
                    removed_dirs.add(dir_name)
                except OSError as e:
                    logger.error(f"    ❌ Failed to delete {dir_name}: {e}")
    missing_pokemon = set(canonical_data.keys()) - valid_dirs
    if missing_pokemon:
        logger.info(f"  📋 Missing Pokemon: {len(missing_pokemon)}")
        logger.info("      Will be added by Serebii scraper...")
        if len(missing_pokemon) <= 10:
            for pokemon in sorted(missing_pokemon):
                canonical_info = canonical_data[pokemon]
                logger.info(
                    f"        • #{canonical_info['dex']:03d} {canonical_info['name']} ({pokemon})"
                )
        else:
            logger.info(f"        • {len(missing_pokemon)} Pokemon need to be added")
    logger.info(
        f"  🎯 Result: {len(valid_dirs)} valid + {len(missing_pokemon)} missing = {len(canonical_data)} total Pokemon"
    )
    return valid_dirs, removed_dirs


def analyze_pokemon_completeness(
    pokemon_dirs: set[str], canonical_data: dict[str, dict]
) -> dict[str, set[str]]:
    logger = get_script_logger()
    logger.info("  🔍 Analyzing data completeness for smart updates...")
    analysis = {
        "missing_main_png": set(),
        "missing_sprites": set(),
        "missing_names": set(),
        "missing_descriptions": set(),
        "missing_pokedex_entries": set(),
        "missing_metadata": set(),
        "incomplete_metadata": set(),
    }
    pokemon_data_root = cli.pokemon_data_root()
    for dir_name in pokemon_dirs:
        pokemon_dir = pokemon_data_root / dir_name
        if not pokemon_dir.exists():
            continue
        if not (pokemon_dir / "main.png").exists():
            analysis["missing_main_png"].add(dir_name)
        if not (pokemon_dir / "sprite.png").exists():
            analysis["missing_sprites"].add(dir_name)
        if not (pokemon_dir / "name.png").exists():
            analysis["missing_names"].add(dir_name)
        metadata_path = pokemon_dir / "metadata.json"
        if not metadata_path.exists():
            analysis["missing_metadata"].add(dir_name)
        else:
            try:
                import json

                with open(metadata_path) as f:
                    metadata = json.load(f)
                canonical_info = canonical_data.get(dir_name, {})
                if (
                    not metadata.get("description")
                    or not metadata.get("generation")
                    or metadata.get("pokedex_number") != canonical_info.get("dex")
                    or metadata.get("name") != canonical_info.get("name")
                    or metadata.get("types") != canonical_info.get("types")
                ):
                    analysis["incomplete_metadata"].add(dir_name)
            except (json.JSONDecodeError, OSError):
                analysis["missing_metadata"].add(dir_name)
        if (
            dir_name not in analysis["missing_metadata"]
            and dir_name not in analysis["incomplete_metadata"]
        ):
            try:
                import json

                with open(metadata_path) as f:
                    metadata = json.load(f)
                if not metadata.get("description") or not metadata.get("generation"):
                    analysis["missing_descriptions"].add(dir_name)
            except Exception:
                analysis["missing_descriptions"].add(dir_name)
        if not (pokemon_dir / "pokedex_entries.json").exists():
            analysis["missing_pokedex_entries"].add(dir_name)
    total_pokemon = len(pokemon_dirs)
    logger.info(f"    📊 Completeness analysis for {total_pokemon} Pokemon:")
    logger.info(
        f"      Main artwork: {total_pokemon - len(analysis['missing_main_png'])}/{total_pokemon} complete"
    )
    logger.info(
        f"      Sprites: {total_pokemon - len(analysis['missing_sprites'])}/{total_pokemon} complete"
    )
    logger.info(
        f"      Name images: {total_pokemon - len(analysis['missing_names'])}/{total_pokemon} complete"
    )
    logger.info(
        f"      Descriptions: {total_pokemon - len(analysis['missing_descriptions'])}/{total_pokemon} complete"
    )
    logger.info(
        f"      Pokédex entries: {total_pokemon - len(analysis['missing_pokedex_entries'])}/{total_pokemon} complete"
    )
    logger.info(
        f"      Metadata: {total_pokemon - len(analysis['missing_metadata']) - len(analysis['incomplete_metadata'])}/{total_pokemon} complete"
    )
    return analysis


# Imports moved to top


def get_existing_pokemon_directories() -> set[str]:
    pokemon_root = cli.pokemon_data_root()
    if not pokemon_root.exists():
        return set()
    directories = set()
    for item in pokemon_root.iterdir():
        if item.is_dir() and not item.name.startswith("."):
            directories.add(item.name)
    return directories


def get_pokemon_from_serebii() -> set[str]:
    return get_existing_pokemon_directories()


def run_serebii_scraper(
    overwrite: bool = False,
    dry_run: bool = False,
    pokemon_filter: str | None = None,
    cleanup: bool = False,
) -> bool:
    logger = get_script_logger()
    logger.info("🌐 Step 1: Running Serebii scraper to build directory structure...")
    cmd = [sys.executable, "scripts/scrape_serebii_data.py"]
    if pokemon_filter:
        cmd.extend(["--pokemon", pokemon_filter])
        logger.info(f"  🎯 Targeting single Pokemon: {pokemon_filter}")
    if overwrite:
        cmd.append("--overwrite")
    if cleanup:
        cmd.append("--cleanup")
        logger.info("  🧹 Will cleanup orphaned directories not found on Serebii")
    if dry_run:
        cmd.append("--dry-run")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=cli.project_root())
        if result.returncode == 0:
            logger.info("  ✅ Serebii scraper completed successfully")
            if not dry_run:
                directories = get_existing_pokemon_directories()
                logger.info(f"  📊 Total Pokemon directories: {len(directories)}")
            return True
        else:
            logger.error("  ❌ Serebii scraper failed:")
            logger.error(f"    stderr: {result.stderr}")
            return False
    except Exception as e:
        logger.error(f"  ❌ Failed to run Serebii scraper: {e}")
        return False


# Official Pokemon site validation has been removed from the build pipeline
# All Pokemon data now comes from Serebii.net as the single authoritative source
async def run_logo_generation_step(
    pokemon_directories: set[str],
    dry_run: bool = False,
    pokemon_filter: str | None = None,
    skip_logos: bool = False,
) -> dict[str, Any]:
    """Generate Pokemon logos using browser automation for font rendering."""
    results = {
        "logos": {"success": False, "message": "Not run"},
        "browser_used": False,
    }

    if skip_logos:
        logger = get_script_logger()
        logger.step("\nStep 2: Skipping logo generation (--skip-logos)", "⏭️")
        results["logos"] = {"success": True, "message": "Skipped by user request"}
        return results
    elif pokemon_filter:
        logger = get_script_logger()
        logger.step("\nStep 2: Skipping logo generation (filtered mode)", "⏭️")
        results["logos"] = {"success": True, "message": "Skipped in filtered mode"}
        return results
    else:
        logger = get_script_logger()
        logger.step("\nStep 2: Generating Pokemon logos...", "🎨")
        logger.substep("🎭 Using browser session for font generation")
        try:
            await generate_pokemon_logos(
                cli.pokemon_data_root(),
                overwrite=False,
                debug=False,
            )
            results["logos"] = {"success": True, "message": "Logo generation completed"}
            results["browser_used"] = True
            logger.success("Logo generation completed successfully")
        except Exception as e:
            results["logos"] = {"success": False, "message": f"Logo generation failed: {e}"}
            logger.warning(f"Logo generation failed: {e}")
    return results


# Browser-dependent steps fallback removed - no longer needed without official site validation
def run_sprite_download(dry_run: bool = False, pokemon_filter: str | None = None) -> bool:
    logger = get_script_logger()
    if pokemon_filter:
        logger.step(f"\nStep 3: Downloading sprite for {pokemon_filter}...", "🖼️")
    else:
        logger.step("\nStep 3: Downloading all Pokemon sprites...", "🖼️")
    logger.substep("📥 Downloading missing sprites (default behavior)")
    logger.substep("🔄 Starting sprite download process...")
    cmd = [sys.executable, "scripts/download_sprites.py"]
    if pokemon_filter:
        cmd.extend(["--pokemon", pokemon_filter])
    if dry_run:
        cmd.append("--dry-run")
    logger.substep(f"💻 Running: {' '.join(cmd[-4:])}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=cli.project_root())
        if result.returncode == 0:
            logger.success("Sprite download completed successfully")
            stdout = result.stdout
            wrote_count = stdout.count("Wrote sprite:")
            skip_count = stdout.count("[skip] sprite exists")
            warn_count = stdout.count("[warn]")
            if not dry_run:
                logger.substep(f"Downloaded: {wrote_count} new sprites", 2)
                logger.substep(f"Skipped: {skip_count} existing sprites", 2)
                if warn_count > 0:
                    logger.substep(f"Warnings: {warn_count}", 2)
            return True
        elif result.returncode == 1:
            logger.warning("Sprite download validation failed (site may be inaccessible)")
            logger.substep(f"Details: {result.stderr.strip()}", 2)
            logger.substep("⏭️  Skipping sprite download, continuing with other steps")
            return False
        else:
            logger.failure(f"Sprite download failed (exit code {result.returncode}):")
            logger.substep(f"stderr: {result.stderr}", 2)
            return False
    except Exception as e:
        logger.failure(f"Failed to run sprite downloader: {e}")
        return False


# Official Pokemon site validation removed from the build pipeline
# Pokemon data integrity is now ensured by Serebii.net as the single authoritative source
def run_description_scraper(dry_run: bool = False, pokemon_filter: str | None = None) -> bool:
    logger = get_script_logger()
    if pokemon_filter:
        logger.step(f"\nStep 4: Scraping description for {pokemon_filter}...", "📖")
    else:
        logger.step("\nStep 4: Scraping Pokemon descriptions...", "📖")
    logger.substep("🌐 Fetching descriptions from pokelore.com")
    cmd = [sys.executable, "scripts/scrape_descriptions.py"]
    if pokemon_filter:
        cmd.extend(["--pokemon", pokemon_filter])
    if dry_run:
        cmd.append("--dry-run")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=cli.project_root())
        if result.returncode == 0:
            logger.success("Description scraping completed successfully")
            stdout = result.stdout
            updated_count = stdout.count("Updated description for")
            skipped_count = stdout.count("Skipped description for")
            no_description_count = stdout.count("No description found for")
            if not dry_run:
                logger.substep(f"Updated: {updated_count} descriptions", 2)
                logger.substep(f"Skipped: {skipped_count} unchanged", 2)
                if no_description_count > 0:
                    logger.substep(f"Not found: {no_description_count}", 2)
            return True
        elif result.returncode == 1:
            logger.warning("Description scraping validation failed (site may be inaccessible)")
            logger.substep(f"Details: {result.stderr.strip()}", 2)
            logger.substep("⏭️  Skipping description scraping, continuing with other steps")
            return False
        else:
            logger.failure(f"Description scraping failed (exit code {result.returncode}):")
            logger.substep(f"stderr: {result.stderr}", 2)
            return False
    except Exception as e:
        logger.failure(f"Failed to run description scraper: {e}")
        return False


def run_pokedex_entries_scraper(dry_run: bool = False, pokemon_filter: str | None = None) -> bool:
    logger = get_script_logger()
    if pokemon_filter:
        logger.step(f"\nStep 5: Scraping Pokédex entries for {pokemon_filter}...", "📚")
    else:
        logger.step("\nStep 5: Scraping all Pokédex entries...", "📚")
    logger.substep("🌐 Fetching entries from pokemondb.net")
    logger.substep("🔄 Starting Pokédex entries scraper...")
    cmd = [sys.executable, "scripts/scrape_pokedex_entries.py"]
    if pokemon_filter:
        cmd.extend(["--pokemon", pokemon_filter])
    if dry_run:
        cmd.append("--dry-run")
    logger.substep(f"💻 Running: {' '.join(cmd[-3:])}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=cli.project_root())
        if result.returncode == 0:
            logger.success("Pokédex entries scraping completed successfully")
            stdout = result.stdout
            updated_count = stdout.count("[ok]")
            skipped_count = stdout.count("[skip]")
            diff_count = stdout.count("[diff]")
            warn_count = stdout.count("[warn]")
            if not dry_run:
                logger.substep(f"Updated: {updated_count} entries")
                logger.substep(f"Skipped: {skipped_count} unchanged")
                if warn_count > 0:
                    logger.substep(f"Warnings: {warn_count}", 2)
            else:
                if diff_count > 0:
                    logger.substep(f"Would update: {diff_count} entries")
                if skipped_count > 0:
                    logger.substep(f"Would skip: {skipped_count} unchanged", 2)
            return True
        else:
            logger.failure(" Pokédex entries scraping failed:")
            logger.substep(f"stderr: {result.stderr}", 2)
            return False
    except Exception as e:
        logger.failure(f"Failed to run Pokédx entries scraper: {e}")
        return False


def run_evolution_chains_scraper(dry_run: bool = False, pokemon_filter: str | None = None) -> bool:
    logger = get_script_logger()
    if pokemon_filter:
        logger.step(f"\nStep 6: Scraping evolution chains for {pokemon_filter}...", "🔗")
    else:
        logger.step("\nStep 6: Scraping Pokemon evolution chains...", "🔗")
    logger.substep("🌐 Fetching evolution data from pokemondb.net")
    logger.substep("🔄 Starting evolution chains scraper...")
    cmd = [sys.executable, "scripts/scrape_evolution_chains.py"]
    if pokemon_filter:
        cmd.extend(["--pokemon", pokemon_filter])
    if dry_run:
        cmd.append("--dry-run")
    logger.substep(f"💻 Running: {' '.join(cmd[-3:])}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=cli.project_root())
        if result.returncode == 0:
            logger.success(" Evolution chains scraping completed successfully")
            stdout = result.stdout
            updated_count = stdout.count("Updated evolution data for")
            would_write_count = stdout.count("Would write for")
            if not dry_run:
                if updated_count > 0:
                    logger.substep(f"Updated: {updated_count} evolution chains")
                else:
                    logger.substep("No evolution chains needed updating", 2)
            else:
                if would_write_count > 0:
                    logger.substep(f"Would update: {would_write_count} evolution chains")
                else:
                    logger.substep("No evolution chains would change")
            return True
        else:
            logger.failure(" Evolution chains scraping failed:")
            logger.substep(f"stderr: {result.stderr}", 2)
            return False
    except Exception as e:
        logger.failure(f"Failed to run evolution chains scraper: {e}")
        return False


def run_normalize_metadata(dry_run: bool = False, pokemon_filter: str | None = None) -> bool:
    logger = get_script_logger()
    if pokemon_filter:
        logger.step(f"\nStep 8: Normalizing metadata for {pokemon_filter}...", "📝")
    else:
        logger.step("\nStep 8: Normalizing all Pokemon metadata...", "📝")
    logger.substep("🧹 Cleaning up text inconsistencies and formatting issues")
    logger.substep("🔄 Starting metadata normalization...")
    cmd = [sys.executable, "scripts/normalize_metadata.py"]
    if pokemon_filter:
        cmd.extend(["--pokemon", pokemon_filter])
    if dry_run:
        cmd.append("--dry-run")
    if not pokemon_filter:
        cmd.append("--progress")
    logger.substep(f"💻 Running: {' '.join(cmd[-3:])}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=cli.project_root())
        if result.returncode == 0:
            logger.success(" Metadata normalization completed successfully")
            stdout = result.stdout
            updated_count = stdout.count("🔧") + stdout.count("updated")
            unchanged_count = stdout.count("✓") + stdout.count("unchanged")
            if not dry_run:
                if pokemon_filter:
                    if updated_count > 0:
                        logger.substep(f"Normalized: metadata for {pokemon_filter}", 2)
                    elif unchanged_count > 0:
                        logger.substep("No changes: metadata already clean")
                else:
                    logger.substep(f"Normalized: {updated_count} Pokemon", 2)
                    logger.substep(f"Unchanged: {unchanged_count} already clean")
            else:
                would_update_count = stdout.count("📝") + stdout.count("Would")
                if pokemon_filter:
                    if would_update_count > 0:
                        logger.substep(f"Would normalize: metadata for {pokemon_filter}", 2)
                    else:
                        logger.substep("Would skip: metadata already clean")
                else:
                    if would_update_count > 0:
                        logger.substep(f"Would normalize: {would_update_count} Pokemon")
                    if unchanged_count > 0:
                        logger.substep(f"Would skip: {unchanged_count} already clean")
            return True
        else:
            logger.failure(" Metadata normalization failed:")
            logger.substep(f"stderr: {result.stderr}", 2)
            return False
    except Exception as e:
        logger.failure(f"Failed to run metadata normalizer: {e}")
        return False


def run_pronunciations_scraper(dry_run: bool = False, pokemon_filter: str | None = None) -> bool:
    logger = get_script_logger()
    if pokemon_filter:
        logger.step(f"\nStep 7: Scraping pronunciations for {pokemon_filter}...", "🗣️")
        logger.substep("🎯 Using generation-specific lookup for faster processing")
    else:
        logger.step("\nStep 7: Scraping all Pokemon pronunciations...", "🗣️")
        logger.substep("🌐 Fetching pronunciations from pokemonlp.fandom.com")
    logger.substep("🔄 Starting pronunciations scraper...")
    cmd = [sys.executable, "scripts/scrape_pronunciations.py"]
    if pokemon_filter:
        cmd.extend(["--pokemon", pokemon_filter])
    if dry_run:
        cmd.append("--dry-run")
    logger.substep(f"💻 Running: {' '.join(cmd[-3:])}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=cli.project_root())
        if result.returncode == 0:
            logger.success(" Pronunciations scraping completed successfully")
            stdout = result.stdout
            updated_count = stdout.count("Updated pronunciations for")
            skipped_count = stdout.count("Skipped pronunciations for")
            if not dry_run:
                if pokemon_filter:
                    if updated_count > 0:
                        logger.substep(f"Updated: pronunciation for {pokemon_filter}")
                    elif skipped_count > 0:
                        logger.substep("Skipped: pronunciation unchanged")
                    else:
                        logger.substep("No pronunciation found")
                else:
                    logger.substep(f"Updated: {updated_count} pronunciations")
                    logger.substep(f"Skipped: {skipped_count} unchanged")
            else:
                would_update_count = stdout.count("Would update pronunciations for")
                if pokemon_filter:
                    if would_update_count > 0:
                        logger.substep(f"Would update: pronunciation for {pokemon_filter}")
                    elif skipped_count > 0:
                        logger.substep("Would skip: pronunciation unchanged")
                else:
                    if would_update_count > 0:
                        logger.substep(f"Would update: {would_update_count} pronunciations")
                    if skipped_count > 0:
                        logger.substep(f"Would skip: {skipped_count} unchanged")
            return True
        else:
            logger.failure(" Pronunciations scraping failed:")
            logger.substep(f"stderr: {result.stderr}", 2)
            return False
    except Exception as e:
        logger.failure(f"Failed to run pronunciations scraper: {e}")
        return False


def check_pokemon_count_match() -> dict[str, Any]:
    logger = get_script_logger()
    logger.step("\nStep 9: Verifying Pokemon count matches official source...", "🔍")
    local_directories = get_existing_pokemon_directories()
    local_count = len(local_directories)
    logger.substep(f"📁 Local Pokemon directories: {local_count}")
    pokemon_with_numbers = []
    dirs_without_numbers = []
    max_local_number = 0
    for pokemon_directory in local_directories:
        metadata_path = cli.pokemon_data_root() / pokemon_directory / "metadata.json"
        if metadata_path.exists():
            try:
                with open(metadata_path) as f:
                    metadata = json.load(f)
                    dex_number = metadata.get("pokedex_number", 0)
                    if isinstance(dex_number, int) and dex_number > 0:
                        pokemon_with_numbers.append(
                            (dex_number, pokemon_directory, metadata.get("name", pokemon_directory))
                        )
                        max_local_number = max(max_local_number, dex_number)
                    else:
                        dirs_without_numbers.append(pokemon_directory)
            except Exception:
                dirs_without_numbers.append(pokemon_directory)
        else:
            dirs_without_numbers.append(pokemon_directory)
    logger.substep(f"🔢 Pokemon with valid numbers: {len(pokemon_with_numbers)}")
    logger.substep(f"📝 Highest Pokedex number found: #{max_local_number}")
    if dirs_without_numbers:
        logger.warning(f"Directories without valid pokedex_number: {len(dirs_without_numbers)}")
        for _i, dir_name in enumerate(sorted(dirs_without_numbers)[:5]):
            logger.substep(f"• {dir_name}", 3)
        if len(dirs_without_numbers) > 5:
            logger.substep(f"... and {len(dirs_without_numbers) - 5} more", 3)
    pokemon_numbers = {num for num, _, _ in pokemon_with_numbers}
    expected_range = set(range(1, max_local_number + 1))
    missing_numbers = sorted(expected_range - pokemon_numbers)
    if missing_numbers:
        logger.warning(f"Missing Pokedex numbers in sequence: {missing_numbers[:10]}")
        if len(missing_numbers) > 10:
            logger.substep(f"... and {len(missing_numbers) - 10} more", 3)
    SEREBII_MAX_POKEMON = 1025
    complete = None
    missing_pokemon = []
    if max_local_number > 0:
        logger.substep(f"🌐 Verifying against Serebii (max Pokemon: #{SEREBII_MAX_POKEMON})")
        if max_local_number >= SEREBII_MAX_POKEMON:
            if max_local_number == SEREBII_MAX_POKEMON:
                logger.substep(f"✅ Local max #{max_local_number} matches Serebii's max", 3)
                complete = True
            else:
                logger.substep(
                    f"⚠️  Local max #{max_local_number} exceeds Serebii's max #{SEREBII_MAX_POKEMON}",
                    3,
                )
                logger.substep("  🔍 You may have extra Pokemon beyond Serebii's official list")
                complete = True
        else:
            missing_count = SEREBII_MAX_POKEMON - max_local_number
            logger.substep(
                f"⚠️  Missing {missing_count} Pokemon (#{max_local_number + 1} to #{SEREBII_MAX_POKEMON})",
                3,
            )
            complete = False
            for num in range(
                max_local_number + 1, min(max_local_number + 6, SEREBII_MAX_POKEMON + 1)
            ):
                missing_pokemon.append((num, "Unknown (not scraped from Serebii)"))
    else:
        logger.failure(" Could not determine max Pokedex number")
    issues = []
    if dirs_without_numbers:
        issues.append(f"{len(dirs_without_numbers)} directories without valid metadata")
    if missing_numbers:
        issues.append(f"{len(missing_numbers)} gaps in Pokedex numbering")
    if missing_pokemon:
        issues.append(f"{len(missing_pokemon)} missing Pokemon found on pokemon.com")
    if issues:
        logger.substep("\n📋 Issues detected:")
        for issue in issues:
            logger.substep(f"• {issue}", 3)
        if missing_pokemon:
            logger.substep("🔍 Missing Pokemon details:")
            for num, name in missing_pokemon:
                logger.substep(f"• #{num}: {name}", 3)
    return {
        "local_count": local_count,
        "max_pokedex_number": max_local_number,
        "appears_complete": complete,
        "dirs_without_metadata": len(dirs_without_numbers),
        "missing_numbers": len(missing_numbers),
        "missing_pokemon": missing_pokemon,
        "issues": issues,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build complete Pokemon dataset by orchestrating scraping scripts",
        epilog="""
        """,
    )
    cli.add_dry_run(parser, help="Show what would be done without making changes")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Force re-download of ALL data (very slow, only use for complete refresh)",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Skip Serebii scraping, only run data processing on existing directories",
    )
    parser.add_argument(
        "--skip-count-check", action="store_true", help="Skip the final count verification step"
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="DEPRECATED: Cleanup is now automatic. This flag is ignored.",
    )
    parser.add_argument(
        "--pokemon",
        type=str,
        metavar="NAME",
        help="Process only a specific Pokemon by name/directory (for testing)",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=20,
        metavar="SIZE",
        help="Number of Pokemon per batch chunk (default: 20)",
    )
    parser.add_argument(
        "--test-validation",
        action="store_true",
        help="Run validation-only mode on all scraping scripts to test infrastructure",
    )
    parser.add_argument(
        "--core-only",
        action="store_true",
        help="Only run essential scripts (Serebii + sprites + normalize)",
    )
    parser.add_argument(
        "--skip-expensive",
        action="store_true",
        help="Skip expensive operations (logos + pronunciations)",
    )
    parser.add_argument(
        "--skip-browser-heavy",
        action="store_true",
        help="Skip browser-heavy operations (logos only, keep Pokemon.com validation)",
    )
    parser.add_argument(
        "--skip-logos",
        action="store_true",
        help="Skip Pokemon logo font generation (fallback text will be used)",
    )
    parser.add_argument(
        "--skip-descriptions",
        action="store_true",
        help="Skip description scraping from pokelore.com",
    )
    parser.add_argument(
        "--skip-pokedex-entries",
        action="store_true",
        help="Skip Pokédex entries scraping from pokemondb.net",
    )
    parser.add_argument(
        "--skip-evolution-chains", action="store_true", help="Skip evolution relationships scraping"
    )
    parser.add_argument(
        "--skip-pronunciations",
        action="store_true",
        help="Skip pronunciation scraping from pokemonlp.fandom.com",
    )
    return parser.parse_args()


def resolve_skip_flags(args: argparse.Namespace) -> dict[str, bool]:
    skip_map = {
        "logos": False,
        "descriptions": False,
        "pokedex_entries": False,
        "evolution_chains": False,
        "pronunciations": False,
    }
    if args.core_only:
        skip_map.update(
            {
                "logos": True,
                "descriptions": True,
                "pokedex_entries": True,
                "evolution_chains": True,
                "pronunciations": True,
            }
        )
    if args.skip_expensive:
        skip_map.update(
            {
                "logos": True,
                "pronunciations": True,
            }
        )
    if args.skip_browser_heavy:
        skip_map.update(
            {
                "logos": True,
            }
        )
    if args.skip_logos:
        skip_map["logos"] = True
    if args.skip_descriptions:
        skip_map["descriptions"] = True
    if args.skip_pokedex_entries:
        skip_map["pokedex_entries"] = True
    if args.skip_evolution_chains:
        skip_map["evolution_chains"] = True
    if args.skip_pronunciations:
        skip_map["pronunciations"] = True
    return skip_map


def test_all_validation_infrastructure() -> bool:
    logger = get_script_logger()
    logger.info("🧪 Testing validation infrastructure for all scraping scripts...")
    validation_scripts = [
        ("scrape_serebii_data.py", "Serebii scraper"),
        ("download_sprites.py", "Sprite downloader"),
        ("scrape_descriptions.py", "Description scraper"),
        ("scrape_pokedex_entries.py", "Pokedex entries scraper"),
        ("scrape_pronunciations.py", "Pronunciations scraper"),
        ("scrape_evolution_chains.py", "Evolution chains scraper"),
        ("download_pokemon_logo_font_names.py", "Logo font generator"),
    ]
    results = []
    for script_name, description in validation_scripts:
        logger.info(f"\n  🧪 Testing {description}...")
        cmd = [sys.executable, f"scripts/{script_name}", "--validation-only"]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=cli.project_root(),
                timeout=60,
            )
            if result.returncode == 0:
                logger.info(f"      ✅ {description} validation passed")
                results.append((script_name, True, "Passed"))
            else:
                logger.info(
                    f"      ❌ {description} validation failed (exit code: {result.returncode})"
                )
                logger.info(f"         stderr: {result.stderr.strip()}")
                results.append((script_name, False, f"Failed (exit {result.returncode})"))
        except subprocess.TimeoutExpired:
            logger.info(f"      ⏰ {description} validation timed out")
            results.append((script_name, False, "Timed out"))
        except Exception as e:
            logger.info(f"      💥 {description} validation error: {e}")
            results.append((script_name, False, f"Error: {e}"))
    passed = sum(1 for _, success, _ in results if success)
    total = len(results)
    logger.info("\n📊 Validation Infrastructure Test Results:")
    logger.info(f"   Passed: {passed}/{total}")
    if passed == total:
        logger.info("   ✅ All validation infrastructure is working!")
    else:
        logger.info("   ❌ Some validation infrastructure issues found:")
        for script_name, success, status in results:
            if not success:
                logger.info(f"      • {script_name}: {status}")
    return passed == total


def main() -> None:
    import time

    logger = get_script_logger()
    start_time = time.time()
    args = parse_args()
    if args.test_validation:
        logger.step("Testing validation infrastructure for all scraping scripts", "🧪")
        logger.substep("=" * 60)
        success = test_all_validation_infrastructure()
        logger.substep("\n" + "=" * 60)
        if success:
            logger.success("All validation infrastructure tests passed!")
            logger.success("🚀 Ready to run full data build process")
        else:
            logger.failure("Some validation infrastructure issues found")
            logger.failure("🔧 Fix the issues above before running data build")
            sys.exit(1)
        return
    skip_flags = resolve_skip_flags(args)
    logger.step("Building complete Pokemon dataset", "🎮")
    logger.substep("=" * 50)
    logger.substep(f"⏰ Process started at: {time.strftime('%H:%M:%S')}")
    if args.dry_run:
        logger.substep("🔍 DRY RUN MODE - No files will be modified")
    smart_mode = not args.overwrite
    if args.overwrite:
        logger.substep("🔄 OVERWRITE MODE: Force re-downloading ALL data (slow)")
    else:
        logger.substep("🧠 SMART MODE: Only updating missing/incorrect data (default)")
        logger.substep("Automatically removes corrupted directories", 2)
        logger.substep("Preserves good existing data", 2)
    skipped_scripts = [name for name, skip in skip_flags.items() if skip]
    if skipped_scripts:
        logger.substep(f"⏭️  SKIPPING: {', '.join(skipped_scripts)}")
        logger.substep("(Use individual --skip-* flags or category flags to control)", 2)
    if args.core_only:
        logger.substep("🎯 CORE-ONLY MODE: Running essential scripts only")
    elif args.skip_expensive:
        logger.substep("⚡ FAST MODE: Skipping expensive operations")
    elif args.skip_browser_heavy:
        logger.substep("🌐 MINIMAL BROWSER MODE: Skipping browser-heavy operations")
    valid_pokemon_dirs = set()
    canonical_data = {}
    completeness_analysis = {}
    if smart_mode and not args.validate_only:
        valid_pokemon_dirs, removed_dirs = verify_and_cleanup_pokemon_data(dry_run=args.dry_run)
        if removed_dirs:
            logger.substep(f"🧹 Removed {len(removed_dirs)} corrupted directories")
        canonical_data = get_canonical_pokemon_data()
        if canonical_data:
            completeness_analysis = analyze_pokemon_completeness(valid_pokemon_dirs, canonical_data)
    logger.substep("")
    if not args.validate_only:
        if smart_mode and completeness_analysis:
            missing_serebii_data = (
                completeness_analysis.get("missing_main_png", set())
                | completeness_analysis.get("missing_metadata", set())
                | completeness_analysis.get("incomplete_metadata", set())
            )
            if missing_serebii_data:
                logger.step(
                    f"Step 1: Smart Serebii update for {len(missing_serebii_data)} Pokemon...", "🌐"
                )
                logger.substep("🎯 Only updating Pokemon with missing/incorrect Serebii data")
                serebii_success = run_serebii_scraper(
                    overwrite=False,
                    dry_run=args.dry_run,
                    pokemon_filter=args.pokemon,
                    cleanup=True,  # Enable cleanup to remove invalid directories
                )
            else:
                logger.step(
                    "Step 1: Skipping Serebii scraper - all Pokemon have complete Serebii data",
                    "🌐",
                )
                serebii_success = True
        else:
            logger.step("Step 1: Running Serebii scraper...", "🌐")
            serebii_success = run_serebii_scraper(
                overwrite=args.overwrite,
                dry_run=args.dry_run,
                pokemon_filter=args.pokemon,
                cleanup=True,  # Always enable cleanup as Serebii is our single source of truth
            )
        if not serebii_success:
            logger.failure("\nSerebii scraping failed - this is critical for the dataset")
            logger.substep("💡 Serebii.net may be down or blocking requests", 2)
            logger.substep("🔧 Try again later or use --force flag in individual scripts", 2)
            sys.exit(1)
    else:
        logger.substep("⏭️  Skipping Serebii scraping (--validate-only mode)")
        logger.substep(" Only processing existing directories with sprites, descriptions, etc.")
    pokemon_directories = get_existing_pokemon_directories()
    if not pokemon_directories:
        logger.failure("\nNo Pokemon directories found - run Serebii scraper first")
        sys.exit(1)
    if args.pokemon:
        pokemon_dirs = cli.filter_pokemon_directories(args.pokemon, cli.pokemon_data_root())
        if not pokemon_dirs:
            logger.failure(f"\nPokemon '{args.pokemon}' not found")
            logger.substep(
                "💡 Try using the exact Pokemon name like 'Flabébé' or Pokedex number like '669'", 2
            )
            logger.substep(
                f"Available examples: {', '.join(sorted(pokemon_directories)[:5])}...", 2
            )
            sys.exit(1)
        resolved_directory = pokemon_dirs[0]
        resolved_name = resolved_directory.name
        logger.success(f"\nResolved '{args.pokemon}' to: {resolved_name}")
        matching_dirs = [d for d in pokemon_directories if d == resolved_name]
        if not matching_dirs:
            logger.failure(f"\nResolved Pokemon '{resolved_name}' not found in current Pokemon set")
            sys.exit(1)
        pokemon_directories = set(matching_dirs)
        logger.step(f"SINGLE POKEMON MODE: Processing {matching_dirs[0]}", "🎯")
        logger.substep("📋 Expected steps: 6-8 (depending on skip flags)")
    else:
        logger.step(f"\nFULL MODE: Processing all {len(pokemon_directories)} Pokemon", "🌍")
        logger.substep("📋 Expected steps: 6-8 (depending on skip flags)")
    pokemon_filter = (
        sorted(pokemon_directories)[0] if args.pokemon and pokemon_directories else None
    )
    # Step 2: Logo Generation
    step_start = time.time()
    logo_results = asyncio.run(
        run_logo_generation_step(
            pokemon_directories,
            dry_run=args.dry_run,
            pokemon_filter=pokemon_filter,
            skip_logos=skip_flags["logos"],
        )
    )
    step_time = time.time() - step_start
    logger.substep(f"⏱️  Logo step completed in {step_time:.1f}s")
    # Step 3: Sprite Download
    step_start = time.time()
    if smart_mode and completeness_analysis:
        missing_sprites = completeness_analysis.get("missing_sprites", set())
        if args.pokemon:
            target_pokemon = sorted(pokemon_directories)[0] if pokemon_directories else None
            sprite_success = run_sprite_download(
                dry_run=args.dry_run, pokemon_filter=target_pokemon
            )
        elif missing_sprites:
            logger.step(f"Step 3: Smart sprite download for {len(missing_sprites)} Pokemon...", "🖼️")
            sprite_success = run_sprite_download(dry_run=args.dry_run)
        else:
            logger.step("Step 3: Skipping sprite download - all Pokemon have sprites", "🖼️")
            sprite_success = True
    else:
        if args.pokemon:
            target_pokemon = sorted(pokemon_directories)[0] if pokemon_directories else None
            sprite_success = run_sprite_download(
                dry_run=args.dry_run, pokemon_filter=target_pokemon
            )
        else:
            sprite_success = run_sprite_download(dry_run=args.dry_run)
    step_time = time.time() - step_start
    logger.substep(f"⏱️  Sprite download step completed in {step_time:.1f}s")
    if not sprite_success:
        logger.warning("\nSprite download failed - continuing anyway")
        logger.substep("💡 This may be due to pokemondb.net being inaccessible", 2)
    if skip_flags["descriptions"]:
        logger.step("\nStep 4: Skipping descriptions (--skip-descriptions)", "⏭️")
        description_success = True
    elif smart_mode and completeness_analysis:
        missing_descriptions = completeness_analysis.get(
            "missing_descriptions", set()
        ) | completeness_analysis.get("incomplete_metadata", set())
        if args.pokemon:
            target_pokemon = sorted(pokemon_directories)[0] if pokemon_directories else None
            description_success = run_description_scraper(
                dry_run=args.dry_run, pokemon_filter=target_pokemon
            )
        elif missing_descriptions:
            logger.step(
                f"Step 4: Smart description scraping for {len(missing_descriptions)} Pokemon...",
                "📖",
            )
            description_success = run_description_scraper(dry_run=args.dry_run)
        else:
            logger.step("Step 4: Skipping descriptions - all Pokemon have descriptions", "📖")
            description_success = True
    else:
        if args.pokemon:
            target_pokemon = sorted(pokemon_directories)[0] if pokemon_directories else None
            description_success = run_description_scraper(
                dry_run=args.dry_run, pokemon_filter=target_pokemon
            )
        else:
            description_success = run_description_scraper(dry_run=args.dry_run)
    if not description_success:
        logger.warning("\nDescription scraping failed - continuing anyway")
        logger.substep("💡 This may be due to pokelore.com being inaccessible", 2)
    if skip_flags["pokedex_entries"]:
        logger.step("\nStep 5: Skipping Pokédx entries (--skip-pokedex-entries)", "⏭️")
        pokedex_entries_success = True
    elif smart_mode and completeness_analysis:
        missing_pokedex_entries = completeness_analysis.get("missing_pokedex_entries", set())
        if args.pokemon:
            target_pokemon = sorted(pokemon_directories)[0] if pokemon_directories else None
            pokedex_entries_success = run_pokedex_entries_scraper(
                dry_run=args.dry_run, pokemon_filter=target_pokemon
            )
        elif missing_pokedex_entries:
            logger.step(
                f"Step 5: Smart Pokédx entries scraping for {len(missing_pokedex_entries)} Pokemon...",
                "📚",
            )
            pokedex_entries_success = run_pokedex_entries_scraper(dry_run=args.dry_run)
        else:
            logger.step("Step 5: Skipping Pokédx entries - all Pokemon have entries", "📚")
            pokedex_entries_success = True
    else:
        if args.pokemon:
            target_pokemon = sorted(pokemon_directories)[0] if pokemon_directories else None
            pokedex_entries_success = run_pokedex_entries_scraper(
                dry_run=args.dry_run, pokemon_filter=target_pokemon
            )
        else:
            pokedex_entries_success = run_pokedex_entries_scraper(dry_run=args.dry_run)
    if not pokedex_entries_success:
        logger.warning("\nPokédx entries scraping failed - continuing anyway")
    if skip_flags["evolution_chains"]:
        logger.step("\nStep 6: Skipping evolution chains (--skip-evolution-chains)", "⏭️")
        evolution_chains_success = True
    elif args.pokemon:
        target_pokemon = sorted(pokemon_directories)[0] if pokemon_directories else None
        evolution_chains_success = run_evolution_chains_scraper(
            dry_run=args.dry_run, pokemon_filter=target_pokemon
        )
    else:
        evolution_chains_success = run_evolution_chains_scraper(dry_run=args.dry_run)
    if not evolution_chains_success:
        logger.warning("\nEvolution chains scraping failed - continuing anyway")
    if skip_flags["pronunciations"]:
        logger.step("\nStep 7: Skipping pronunciations (--skip-pronunciations)", "⏭️")
        pronunciations_success = True
    elif args.pokemon:
        target_pokemon = sorted(pokemon_directories)[0] if pokemon_directories else None
        pronunciations_success = run_pronunciations_scraper(
            dry_run=args.dry_run, pokemon_filter=target_pokemon
        )
    else:
        pronunciations_success = run_pronunciations_scraper(dry_run=args.dry_run)
        if not pronunciations_success:
            logger.warning("\nPronunciations scraping failed - continuing anyway")
    if args.pokemon:
        target_pokemon = sorted(pokemon_directories)[0] if pokemon_directories else None
        normalize_success = run_normalize_metadata(
            dry_run=args.dry_run, pokemon_filter=target_pokemon
        )
    else:
        normalize_success = run_normalize_metadata(dry_run=args.dry_run)
    if not normalize_success:
        logger.warning("\nMetadata normalization failed - continuing anyway")
    if not args.skip_count_check:
        count_results = check_pokemon_count_match()
    else:
        logger.step("\nSkipping count verification (--skip-count-check)", "⏭️")
        count_results = None
    if smart_mode and not args.validate_only:
        logger.step("\nStep 10: Final comprehensive verification...", "🔍")
        if not canonical_data:
            logger.substep("📊 Getting canonical data for verification...")
            canonical_data = get_canonical_pokemon_data()
        logger.substep("🔍 Verifying data integrity and completeness...")
        final_dirs = get_existing_pokemon_directories()
        verification_results = {
            "total_directories": len(final_dirs),
            "valid_pokemon": 0,
            "missing_files": [],
            "corrupted_metadata": [],
            "file_issues": [],
            "canonical_mismatches": [],
        }
        for pokemon_dir in final_dirs:
            if isinstance(pokemon_dir, str):
                pokemon_path = cli.pokemon_data_root() / pokemon_dir
                pokemon_name = pokemon_dir
            else:
                pokemon_path = pokemon_dir
                pokemon_name = pokemon_dir.name
            canonical_entry = canonical_data.get(pokemon_name)
            if not canonical_entry:
                verification_results["canonical_mismatches"].append(
                    f"{pokemon_name} (not in canonical data)"
                )
                continue
            verification_results["valid_pokemon"] += 1
            required_files = ["main.png", "metadata.json"]
            optional_files = ["sprite.png", "name.png"]
            for req_file in required_files:
                if not (pokemon_path / req_file).exists():
                    verification_results["missing_files"].append(f"{pokemon_name}/{req_file}")
            for opt_file in optional_files:
                if not (pokemon_path / opt_file).exists():
                    verification_results["file_issues"].append(
                        f"{pokemon_name}/{opt_file} (optional)"
                    )
            metadata_file = pokemon_path / "metadata.json"
            if metadata_file.exists():
                try:
                    with open(metadata_file) as f:
                        metadata = json.load(f)
                    if metadata.get("dex_number") != canonical_entry.get("dex"):
                        verification_results["corrupted_metadata"].append(
                            f"{pokemon_name}: dex_number mismatch ({metadata.get('dex_number')} vs {canonical_entry.get('dex')})"
                        )
                    if metadata.get("display_name") != canonical_entry.get("name"):
                        verification_results["corrupted_metadata"].append(
                            f"{pokemon_name}: display_name mismatch ({metadata.get('display_name')} vs {canonical_entry.get('name')})"
                        )
                    required_metadata = ["dex_number", "display_name", "types"]
                    for field in required_metadata:
                        if field not in metadata:
                            verification_results["corrupted_metadata"].append(
                                f"{pokemon_name}: missing {field} in metadata"
                            )
                except (json.JSONDecodeError, Exception) as e:
                    verification_results["corrupted_metadata"].append(
                        f"{pokemon_name}: invalid JSON ({e})"
                    )
        logger.substep("📊 Verification Results:")
        logger.substep(f"Total directories: {verification_results['total_directories']}", 2)
        logger.substep(f"Valid Pokemon: {verification_results['valid_pokemon']}", 2)
        logger.substep("  Expected from Serebii: 1025")
        if verification_results["canonical_mismatches"]:
            logger.warning(
                f"{len(verification_results['canonical_mismatches'])} directories not in canonical data:"
            )
            for mismatch in verification_results["canonical_mismatches"][:5]:
                logger.substep(f"• {mismatch}", 3)
            if len(verification_results["canonical_mismatches"]) > 5:
                logger.substep(
                    f"• ... and {len(verification_results['canonical_mismatches']) - 5} more", 3
                )
        if verification_results["missing_files"]:
            logger.failure(f" {len(verification_results['missing_files'])} missing required files:")
            for missing in verification_results["missing_files"][:5]:
                logger.substep(f"• {missing}", 3)
            if len(verification_results["missing_files"]) > 5:
                logger.substep(
                    f"• ... and {len(verification_results['missing_files']) - 5} more", 3
                )
        if verification_results["corrupted_metadata"]:
            logger.warning(f"{len(verification_results['corrupted_metadata'])} metadata issues:")
            for corrupt in verification_results["corrupted_metadata"][:5]:
                logger.substep(f"• {corrupt}", 3)
            if len(verification_results["corrupted_metadata"]) > 5:
                logger.substep(
                    f"• ... and {len(verification_results['corrupted_metadata']) - 5} more", 3
                )
        if verification_results["file_issues"]:
            optional_count = len(verification_results["file_issues"])
            logger.substep(
                f"ℹ️  {optional_count} optional files missing (name.png, sprite.png, etc.)"
            )
        total_issues = (
            len(verification_results["missing_files"])
            + len(verification_results["corrupted_metadata"])
            + len(verification_results["canonical_mismatches"])
        )
        if total_issues == 0:
            logger.success(" Dataset verification passed - all Pokemon data is valid and complete!")
        else:
            logger.warning(f"Dataset has {total_issues} issues that may need attention")
    elif smart_mode:
        logger.success("\nSmart mode completed - dataset should be complete and clean")
    logger.substep("\n" + "=" * 50)
    logger.step("BUILD SUMMARY", "🎯")
    logger.substep("=" * 50)
    logger.substep("📊 Build Results:")
    logger.substep(f"• Total Pokemon processed: {len(pokemon_directories)}", 2)
    logger.substep(
        f"• Logo generation: {'Success' if logo_results.get('success') else 'Failed/Skipped'}", 2
    )
    logger.substep(f"• Sprite download: {'Success' if sprite_success else 'Failed'}", 2)
    logger.substep(
        f"• Description scraping: {'Success' if description_success else 'Failed/Skipped'}", 2
    )
    logger.substep(
        f"• Pokédex entries: {'Success' if pokedex_entries_success else 'Failed/Skipped'}", 2
    )
    logger.substep(
        f"• Evolution chains: {'Success' if evolution_chains_success else 'Failed/Skipped'}", 2
    )
    logger.substep(
        f"• Pronunciations: {'Success' if pronunciations_success else 'Failed/Skipped'}", 2
    )
    logger.substep(f"• Metadata normalization: {'Success' if normalize_success else 'Failed'}", 2)
    if count_results:
        logger.substep("\n📈 Count Verification:")
        logger.substep(f"• Local Pokemon count: {count_results['local_count']}", 2)
        logger.substep(f"• Max Pokedex number: {count_results['max_pokedex_number']}", 2)
        if count_results.get("issues"):
            logger.warning(" Issues found:")
            for issue in count_results["issues"]:
                logger.substep(f"- {issue}", 3)
            if count_results.get("missing_pokemon"):
                logger.substep("🔍 Specific missing Pokemon:", 2)
                for num, name in count_results["missing_pokemon"]:
                    logger.substep(f"- #{num}: {name}", 3)
        if count_results["appears_complete"] is True:
            logger.success(" Dataset appears complete")
        elif count_results["appears_complete"] is False:
            logger.warning(" Dataset has issues - see details above")
        else:
            logger.substep("❓ Could not verify completeness", 2)
    count_issues_critical = (
        count_results is not None
        and count_results.get("appears_complete") is False
        and count_results.get("missing_pokemon")
    )
    logo_success = logo_results.get("success", False)
    success_conditions = [
        sprite_success,
        normalize_success,
        not count_issues_critical,
    ]
    if not skip_flags["descriptions"]:
        success_conditions.append(description_success)
    if not skip_flags["pokedex_entries"]:
        success_conditions.append(pokedex_entries_success)
    if not skip_flags["evolution_chains"]:
        success_conditions.append(evolution_chains_success)
    if not skip_flags["pronunciations"]:
        success_conditions.append(pronunciations_success)
    if not skip_flags["logos"]:
        success_conditions.append(logo_success)
    total_time = time.time() - start_time
    hours, remainder = divmod(total_time, 3600)
    minutes, seconds = divmod(remainder, 60)
    time_str = ""
    if hours > 0:
        time_str += f"{int(hours)}h "
    if minutes > 0:
        time_str += f"{int(minutes)}m "
    time_str += f"{seconds:.1f}s"
    if all(success_conditions):
        logger.success("\nDataset build completed successfully!")
        if args.overwrite:
            logger.substep("🔄 Overwrite mode: Re-downloaded all data")
        else:
            logger.substep(
                "🧠 Smart mode: Only updated missing/incorrect data, preserved good existing data"
            )
            logger.substep(
                "Automatically removed corrupted directories and gracefully handled site issues", 2
            )
        logger.substep(f"📁 Pokemon data is ready in: {cli.pokemon_data_root()}")
        logger.substep(f"⏰ Total time: {time_str}")
    else:
        logger.warning("\nDataset build completed with issues - review the summary above")
        logger.substep(f"⏰ Total time: {time_str}")
        if not sprite_success:
            logger.substep("• Sprite download failed", 2)
        if not skip_flags["descriptions"] and not description_success:
            logger.substep("• Description scraping failed", 2)
        if not skip_flags["pokedex_entries"] and not pokedex_entries_success:
            logger.substep("• Pokédex entries scraping failed", 2)
        if not skip_flags["evolution_chains"] and not evolution_chains_success:
            logger.substep("• Evolution chains scraping failed", 2)
        if not normalize_success:
            logger.substep("• Metadata normalization failed", 2)
        if not skip_flags["pronunciations"] and not pronunciations_success:
            pass
        if not skip_flags["logos"] and not logo_success:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
