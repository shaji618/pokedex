from __future__ import annotations

import argparse
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import cli
import requests
from bs4 import BeautifulSoup
from script_logger import get_script_logger


try:
    from validation_utils import (
        add_validation_args,
        compare_audio_files,
        get_audio_properties,
        should_proceed_after_validation_failure,
        validate_audio_file,
    )
except ImportError:
    from scripts.validation_utils import (
        add_validation_args,
        compare_audio_files,
        get_audio_properties,
        should_proceed_after_validation_failure,
        validate_audio_file,
    )
MEDIAFIRE_URL = "https://www.mediafire.com/file/bwtoaxbvt2fnage/RealCries.zip/file"
AUDIO_EXTENSIONS = {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aiff", ".au"}
POKEDEX_PATTERN = re.compile(r"^(\d{1,4})", re.IGNORECASE)


class MediaFireDownloader:
    def __init__(self) -> None:
        self.logger = get_script_logger()
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "keep-alive",
            }
        )
        return session

    def get_direct_download_url(self, mediafire_url: str) -> str | None:
        try:
            self.logger.info(f"🔗 Fetching MediaFire page: {mediafire_url}")
            response = self.session.get(mediafire_url, timeout=30)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")
            download_link = soup.find("a", {"id": "downloadButton"})
            if download_link and download_link.get("href"):
                return download_link["href"]
            scripts = soup.find_all("script")
            for script in scripts:
                if script.string and "downloadUrl" in script.string:
                    import re

                    match = re.search(
                        r'downloadUrl["\']?\s*[:=]\s*["\']([^"\'\n]+)["\']', script.string
                    )
                    if match:
                        return match.group(1)
            self.logger.error("Could not find download link in MediaFire page")
            return None
        except Exception as e:
            self.logger.error(f"Error fetching MediaFire page: {e}")
            return None

    def download_file(self, url: str, dest_path: Path) -> bool:
        try:
            self.logger.info(f"⬇️  Downloading: {url}")
            with self.session.get(url, stream=True, timeout=60) as response:
                response.raise_for_status()
                total_size = int(response.headers.get("content-length", 0))
                if total_size > 0:
                    self.logger.info(f"📦 File size: {total_size / 1024 / 1024:.1f} MB")
                with open(dest_path, "wb") as f:
                    downloaded = 0
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                progress = (downloaded / total_size) * 100
                                if downloaded % (1024 * 1024) == 0:
                                    self.logger.info(f"📥 Progress: {progress:.1f}%")
            self.logger.info(f"✅ Downloaded: {dest_path}")
            return True
        except Exception as e:
            self.logger.error(f"Download failed: {e}")
            return False

    def download_and_extract_realcries(self, target_dir: Path) -> bool:
        if not target_dir.exists():
            target_dir.mkdir(parents=True, exist_ok=True)
        direct_url = self.get_direct_download_url(MEDIAFIRE_URL)
        if not direct_url:
            return False
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temp_file:
            temp_path = Path(temp_file.name)
        try:
            if not self.download_file(direct_url, temp_path):
                return False
            self.logger.info(f"📂 Extracting to: {target_dir}")
            with zipfile.ZipFile(temp_path, "r") as zip_ref:
                zip_ref.extractall(target_dir)
            self.logger.info("✅ RealCries extracted successfully")
            return True
        except Exception as e:
            self.logger.error(f"Extraction failed: {e}")
            return False
        finally:
            if temp_path.exists():
                temp_path.unlink()


class PokemonCryImporter:
    def __init__(
        self,
        realcries_dir: Path,
        pokemon_data_dir: Path,
        *,
        dry_run: bool = False,
        auto_download: bool = True,
    ) -> None:
        self.realcries_dir = realcries_dir
        self.pokemon_data_dir = pokemon_data_dir
        self.dry_run = dry_run
        self.auto_download = auto_download
        self.logger = get_script_logger()
        self.pokemon_metadata = self._load_pokemon_metadata()

    def _load_pokemon_metadata(self) -> dict[str, dict[str, Any]]:
        metadata = {}
        for pokemon_dir in self.pokemon_data_dir.iterdir():
            if not pokemon_dir.is_dir() or pokemon_dir.name.startswith("."):
                continue
            metadata_path = pokemon_dir / "metadata.json"
            if metadata_path.exists():
                try:
                    with open(metadata_path, encoding="utf-8") as f:
                        data = json.load(f)
                    metadata[pokemon_dir.name] = data
                except (json.JSONDecodeError, OSError):
                    self.logger.warning(f"Cannot read metadata for {pokemon_dir.name}")
        return metadata

    def ensure_realcries_directory(self) -> bool:
        if self.realcries_dir.exists():
            self.logger.info(f"📁 RealCries directory found: {self.realcries_dir}")
            return True
        if not self.auto_download:
            self.logger.error(
                f"RealCries directory not found and auto-download disabled: {self.realcries_dir}"
            )
            return False
        self.logger.info("📦 RealCries directory not found, downloading...")
        if self.dry_run:
            self.logger.info(f"[DRY RUN] Would download RealCries to: {self.realcries_dir.parent}")
            return True
        downloader = MediaFireDownloader()
        return downloader.download_and_extract_realcries(self.realcries_dir.parent)

    def scan_realcries_directory(self) -> dict[int, list[tuple[Path, dict[str, Any]]]]:
        audio_files = {}
        if not self.ensure_realcries_directory():
            return {}
        cries_dir = self.realcries_dir / "cries"
        if not cries_dir.exists():
            for item in self.realcries_dir.iterdir():
                if item.is_dir() and "cries" in item.name.lower():
                    cries_dir = item
                    break
            else:
                realcries_subdir = self.realcries_dir / "RealCries"
                if realcries_subdir.exists():
                    cries_dir = realcries_subdir / "cries"
        if not cries_dir.exists():
            self.logger.error(f"Cries directory not found in: {self.realcries_dir}")
            return {}
        self.logger.info(f"📁 Scanning cries directory: {cries_dir}")
        for file_path in cries_dir.iterdir():
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in AUDIO_EXTENSIONS:
                continue
            match = POKEDEX_PATTERN.match(file_path.name)
            if not match:
                self.logger.debug(f"Skipping file without Pokedex number: {file_path.name}")
                continue
            pokedex_num = int(match.group(1))
            properties = get_audio_properties(file_path)
            if not properties:
                self.logger.warning(f"Cannot read audio properties: {file_path.name}")
                continue
            properties["filename"] = file_path.name
            properties["file_path"] = file_path
            if pokedex_num not in audio_files:
                audio_files[pokedex_num] = []
            audio_files[pokedex_num].append((file_path, properties))
        self.logger.info(
            f"🎵 Found {sum(len(files) for files in audio_files.values())} audio files for {len(audio_files)} Pokemon"
        )
        return audio_files

    def find_pokemon_by_number(self, pokedex_num: int) -> str | None:
        for dir_name, metadata in self.pokemon_metadata.items():
            if metadata.get("pokedex_number") == pokedex_num:
                return dir_name
        return None

    def choose_audio_file(
        self, pokedex_num: int, files: list[tuple[Path, dict[str, Any]]]
    ) -> tuple[Path, dict[str, Any]] | None:
        if len(files) == 1:
            return files[0]
        pokemon_dir = self.find_pokemon_by_number(pokedex_num)
        if pokemon_dir and pokemon_dir in self.pokemon_metadata:
            self.pokemon_metadata[pokemon_dir].get("name", pokemon_dir)
        for _i, (_file_path, props) in enumerate(files, 1):
            props.get("duration", 0)
            props.get("file_size", 0)
            props.get("sample_rate", 0)
            props.get("format", "")
            if props.get("spectral_centroid_mean"):
                props["spectral_centroid_mean"]
                props.get("rms_mean", 0)
        while True:
            try:
                choice = input(f"Choose file (1-{len(files)}) or 's' to skip: ").strip().lower()
                if choice == "s":
                    return None
                choice_num = int(choice)
                if 1 <= choice_num <= len(files):
                    chosen_file, chosen_props = files[choice_num - 1]
                    return chosen_file, chosen_props
                else:
                    pass
            except ValueError:
                pass
            except KeyboardInterrupt:
                return None

    def validate_before_import(self, source_path: Path, dest_path: Path) -> bool:
        validation_result = validate_audio_file(source_path)
        if not validation_result["valid"]:
            self.logger.warning(f"Source file validation failed: {source_path.name}")
            for error in validation_result["errors"]:
                self.logger.warning(f"  - {error}")
            return False
        if dest_path.exists():
            self.logger.info("🔄 Destination already exists, comparing files...")
            is_similar, message = compare_audio_files(dest_path, source_path)
            if is_similar:
                self.logger.info(f"✅ Files are similar: {message}")
                return True
            else:
                self.logger.warning(f"⚠️  Files differ: {message}")
                while True:
                    choice = input("Replace existing file? (y/n/c to cancel): ").strip().lower()
                    if choice == "y":
                        return True
                    elif choice == "n":
                        self.logger.info("Keeping existing file")
                        return False
                    elif choice == "c":
                        self.logger.info("Cancelling import")
                        return False
                    else:
                        pass
        return True

    def import_audio_file(
        self, source_path: Path, pokemon_dir: str, filename: str = "anime_cry.wav"
    ) -> bool:
        dest_dir = self.pokemon_data_dir / pokemon_dir
        if not dest_dir.exists():
            self.logger.error(f"Pokemon directory not found: {dest_dir}")
            return False
        dest_path = dest_dir / filename
        if not self.validate_before_import(source_path, dest_path):
            return False
        try:
            if self.dry_run:
                self.logger.info(f"[DRY RUN] Would copy: {source_path.name} → {dest_path}")
                return True
            else:
                shutil.copy2(source_path, dest_path)
                self.logger.info(f"✅ Imported: {source_path.name} → {pokemon_dir}/{filename}")
                validation_result = validate_audio_file(dest_path)
                if not validation_result["valid"]:
                    self.logger.error("Copied file failed validation!")
                    return False
                return True
        except Exception as e:
            self.logger.error(f"Failed to copy {source_path.name}: {e}")
            return False

    def process_all_files(
        self, _overwrite: bool = False, interactive: bool = True, pokemon_filter: str | None = None
    ) -> dict[str, Any]:
        audio_files = self.scan_realcries_directory()
        if pokemon_filter:
            filtered_files = self._filter_audio_files_by_pokemon(audio_files, pokemon_filter)
            if not filtered_files:
                self.logger.error(f"No audio files found for Pokemon: {pokemon_filter}")
                return {"processed": 0, "imported": 0, "skipped": 0, "errors": 0}
            audio_files = filtered_files
        if not audio_files:
            self.logger.error("No audio files found in RealCries directory")
            return {"processed": 0, "imported": 0, "skipped": 0, "errors": 0}
        stats = {"processed": 0, "imported": 0, "skipped": 0, "errors": 0}
        for pokedex_num in sorted(audio_files.keys()):
            files = audio_files[pokedex_num]
            pokemon_dir = self.find_pokemon_by_number(pokedex_num)
            if not pokemon_dir:
                self.logger.warning(f"#{pokedex_num:03d}: No Pokemon directory found")
                stats["errors"] += 1
                continue
            pokemon_name = self.pokemon_metadata.get(pokemon_dir, {}).get("name", pokemon_dir)
            stats["processed"] += 1
            if interactive and len(files) > 1:
                chosen = self.choose_audio_file(pokedex_num, files)
                if not chosen:
                    stats["skipped"] += 1
                    continue
                source_path, properties = chosen
            else:
                source_path, properties = max(files, key=lambda f: f[1].get("file_size", 0))
                if len(files) > 1:
                    self.logger.info(
                        f"#{pokedex_num:03d} {pokemon_name}: Auto-selected {source_path.name} (largest file)"
                    )
            success = self.import_audio_file(source_path, pokemon_dir)
            if success:
                stats["imported"] += 1
                self.logger.info(f"✅ #{pokedex_num:03d} {pokemon_name}: {source_path.name}")
            else:
                stats["errors"] += 1
                self.logger.error(
                    f"❌ #{pokedex_num:03d} {pokemon_name}: Failed to import {source_path.name}"
                )
        return stats

    def _filter_audio_files_by_pokemon(
        self, audio_files: dict[int, list[tuple[Path, dict[str, Any]]]], pokemon_filter: str
    ) -> dict[int, list[tuple[Path, dict[str, Any]]]]:
        try:
            target_pokedex_num = int(pokemon_filter)
            if target_pokedex_num in audio_files:
                return {target_pokedex_num: audio_files[target_pokedex_num]}
            else:
                return {}
        except ValueError:
            pass
        target_name = pokemon_filter.lower().strip()
        for pokedex_num, files in audio_files.items():
            pokemon_dir = self.find_pokemon_by_number(pokedex_num)
            if not pokemon_dir:
                continue
            if target_name == pokemon_dir.lower():
                return {pokedex_num: files}
            metadata = self.pokemon_metadata.get(pokemon_dir, {})
            pokemon_name = metadata.get("name", "").lower()
            if target_name == pokemon_name:
                return {pokedex_num: files}
        return {}


def validate_before_import(realcries_dir: Path, auto_download: bool = True) -> bool:
    logger = get_script_logger()
    logger.info("🧪 Pre-flight validation for Pokemon cries import...")
    if auto_download and not realcries_dir.exists():
        logger.info("🌐 Testing MediaFire URL accessibility...")
        try:
            downloader = MediaFireDownloader()
            direct_url = downloader.get_direct_download_url(MEDIAFIRE_URL)
            if direct_url:
                logger.info("✅ MediaFire URL is accessible and download link extracted")
            else:
                logger.error("❌ Cannot extract download link from MediaFire")
                return False
        except Exception as e:
            logger.error(f"❌ Failed to test MediaFire URL: {e}")
            return False
    if not realcries_dir.exists():
        if auto_download:
            logger.info(f"📦 RealCries directory not found, will download: {realcries_dir}")
            return True
        else:
            logger.error(f"❌ RealCries directory not found: {realcries_dir}")
            return False
    if not realcries_dir.is_dir():
        logger.error(f"❌ RealCries path is not a directory: {realcries_dir}")
        return False
    cries_dir = realcries_dir / "cries"
    if not cries_dir.exists():
        found_cries = False
        for item in realcries_dir.iterdir():
            if item.is_dir() and "cries" in item.name.lower():
                cries_dir = item
                found_cries = True
                break
        if not found_cries:
            realcries_subdir = realcries_dir / "RealCries"
            if realcries_subdir.exists():
                cries_dir = realcries_subdir / "cries"
                found_cries = cries_dir.exists()
        if not found_cries:
            logger.error(f"❌ No cries directory found in: {realcries_dir}")
            return False
    audio_files = []
    for file_path in cries_dir.iterdir():
        if file_path.is_file() and file_path.suffix.lower() in AUDIO_EXTENSIONS:
            audio_files.append(file_path)
    if not audio_files:
        logger.error("❌ No audio files found in RealCries directory")
        return False
    logger.info(f"✅ Found {len(audio_files)} audio files in RealCries directory")
    test_files = audio_files[:3]
    valid_count = 0
    for test_file in test_files:
        properties = get_audio_properties(test_file)
        if properties:
            duration = properties.get("duration", 0)
            if 0.1 <= duration <= 10.0:
                valid_count += 1
                logger.info(f"  ✅ {test_file.name}: {duration:.2f}s")
            else:
                logger.warning(f"  ⚠️  {test_file.name}: Unusual duration {duration:.2f}s")
        else:
            logger.warning(f"  ❌ {test_file.name}: Cannot read audio properties")
    if valid_count == 0:
        logger.error("❌ No valid audio files found")
        return False
    logger.info(f"✅ {valid_count}/{len(test_files)} sample files passed validation")
    logger.info("✅ Pre-flight validation passed")
    return True


def validate_before_scraping(args: argparse.Namespace) -> bool:
    """Simple validation: check if MediaFire URL is active."""
    logger = get_script_logger()
    logger.info("🔍 Checking MediaFire URL accessibility...")
    try:
        downloader = MediaFireDownloader()
        direct_url = downloader.get_direct_download_url(MEDIAFIRE_URL)
        if direct_url:
            logger.info("✅ MediaFire URL is active and accessible")
            return True
        else:
            logger.error("❌ MediaFire URL is not accessible")
            return False
    except Exception as e:
        logger.error(f"❌ Failed to check MediaFire URL: {e}")
        return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import Pokemon cry audio files from RealCries directory",
        epilog="Source: https://www.mediafire.com/file/bwtoaxbvt2fnage/RealCries.zip/file",
    )
    parser.add_argument(
        "realcries_dir",
        nargs="?",
        type=Path,
        help="Path to RealCries directory (default: ./RealCries, will auto-download if missing)",
    )
    cli.add_dry_run(parser, help="Show what would be imported without making changes")
    cli.add_overwrite(parser, help="Overwrite existing audio files without asking")
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Non-interactive mode: auto-select files and don't prompt user",
    )
    parser.add_argument(
        "--pokemon",
        type=str,
        help="Import cry for specific Pokemon only (by name or Pokedex number)",
    )
    parser.add_argument(
        "--no-download",
        action="store_true",
        help="Disable auto-download of RealCries if directory doesn't exist",
    )
    add_validation_args(parser)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.realcries_dir is None:
        args.realcries_dir = Path.cwd() / "RealCries"
    pokemon_data_dir = cli.pokemon_data_root()
    logger = get_script_logger()
    if args.validation_only:
        success = validate_before_import(args.realcries_dir)
        if success:
            pass
        else:
            exit(1)
        return
    if not args.skip_validation:
        if not validate_before_import(args.realcries_dir, auto_download=not args.no_download):
            if not should_proceed_after_validation_failure(args.force):
                exit(1)
    importer = PokemonCryImporter(
        args.realcries_dir,
        pokemon_data_dir,
        dry_run=args.dry_run,
        auto_download=not args.no_download,
    )
    if args.dry_run:
        logger.info("🔍 DRY RUN MODE - No files will be modified")
    stats = importer.process_all_files(
        overwrite=args.overwrite, interactive=not args.batch, pokemon_filter=args.pokemon
    )
    if args.dry_run and stats["imported"] > 0:
        pass


if __name__ == "__main__":
    main()
