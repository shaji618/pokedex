from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import cli
from script_logger import get_script_logger
from validation_utils import add_validation_args


@dataclass
class FileStatus:
    exists: bool = False
    path: Path | None = None
    size: int = 0
    issues: list[str] = field(default_factory=list)


@dataclass
class PokemonVerification:
    directory: Path
    canonical_name: str = ""
    canonical_dex: int = 0
    canonical_types: list[str] = field(default_factory=list)
    main_png: FileStatus = field(default_factory=FileStatus)
    sprite_png: FileStatus = field(default_factory=FileStatus)
    name_png: FileStatus = field(default_factory=FileStatus)
    anime_cry: FileStatus = field(default_factory=FileStatus)
    metadata_json: FileStatus = field(default_factory=FileStatus)
    metadata_content: dict = field(default_factory=dict)
    metadata_issues: list[str] = field(default_factory=list)
    directory_name_correct: bool = True
    directory_name_issues: list[str] = field(default_factory=list)
    is_valid_pokemon: bool = True
    overall_issues: list[str] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        return bool(
            self.main_png.issues
            or self.sprite_png.issues
            or self.name_png.issues
            or self.anime_cry.issues
            or self.metadata_json.issues
            or self.metadata_issues
            or self.directory_name_issues
            or self.overall_issues
            or not self.is_valid_pokemon
        )

    @property
    def critical_issues(self) -> list[str]:
        critical = []
        if not self.is_valid_pokemon:
            critical.extend(self.overall_issues)
        if not self.main_png.exists:
            critical.append("Missing main.png")
        if not self.metadata_json.exists:
            critical.append("Missing metadata.json")
        if self.metadata_issues:
            critical.extend(self.metadata_issues)
        return critical


def check_file_status(directory: Path, filename_pattern: str, required: bool = True) -> FileStatus:
    status = FileStatus()
    if "*" in filename_pattern:
        matching_files = list(directory.glob(filename_pattern))
        if not matching_files:
            status.exists = False
            if required:
                status.issues.append(f"No {filename_pattern} file found")
        elif len(matching_files) == 1:
            file_path = matching_files[0]
            status.exists = True
            status.path = file_path
            status.size = file_path.stat().st_size
            if status.size == 0:
                status.issues.append(f"{file_path.name} is empty")
        else:
            status.exists = True
            status.path = matching_files[0]
            status.size = sum(f.stat().st_size for f in matching_files)
            status.issues.append(
                f"Multiple {filename_pattern} files found: {[f.name for f in matching_files]}"
            )
    else:
        file_path = directory / filename_pattern
        status.exists = file_path.exists()
        if status.exists:
            status.path = file_path
            status.size = file_path.stat().st_size
            if status.size == 0:
                status.issues.append(f"{filename_pattern} is empty")
        elif required:
            status.issues.append(f"Missing {filename_pattern}")
    return status


def suggest_correct_name(corrupted_name: str, canonical_data: dict[str, dict]) -> str | None:
    corrupted_name.lower()
    if corrupted_name.endswith("_male") or corrupted_name.endswith("_female"):
        base_name = corrupted_name.rsplit("_", 1)[0]
        for canonical_name in canonical_data:
            canonical_lower = canonical_name.lower()
            if canonical_lower.startswith(base_name.lower()):
                return canonical_name
            if len(base_name) >= 4:
                base_chars = set(base_name.lower())
                canonical_chars = set(canonical_lower)
                overlap = len(base_chars & canonical_chars)
                if (
                    overlap >= len(base_chars) - 1
                    and abs(len(canonical_name) - len(base_name)) <= 2
                ):
                    return canonical_name
    return None


def rename_corrupted_directory(old_path: Path, new_name: str, dry_run: bool = True) -> bool:
    pokemon_root = old_path.parent
    new_path = pokemon_root / new_name
    if new_path.exists():
        return False
    if dry_run:
        return True
    try:
        old_path.rename(new_path)
        return True
    except OSError:
        return False


def delete_corrupted_directory(directory_path: Path, dry_run: bool = True) -> bool:
    if dry_run:
        return True
    try:
        import shutil

        shutil.rmtree(directory_path)
        return True
    except OSError:
        return False


def validate_metadata_content(
    metadata: dict, canonical_dex: int, canonical_name: str, canonical_types: list[str]
) -> list[str]:
    issues = []
    if "pokedex_number" not in metadata:
        issues.append("Missing pokedex_number")
    elif metadata["pokedex_number"] != canonical_dex:
        issues.append(
            f"Incorrect pokedex_number: {metadata['pokedex_number']} (expected {canonical_dex})"
        )
    if "name" not in metadata:
        issues.append("Missing name")
    elif metadata["name"] != canonical_name:
        issues.append(f"Incorrect name: '{metadata['name']}' (expected '{canonical_name}')")
    if "types" not in metadata:
        issues.append("Missing types")
    elif metadata["types"] != canonical_types:
        issues.append(f"Incorrect types: {metadata['types']} (expected {canonical_types})")
    return issues


async def get_canonical_pokemon_data() -> dict[str, dict]:
    try:
        result = subprocess.run(
            [sys.executable, "scripts/scrape_serebii_data.py", "--dry-run", "--validation-only"],
            capture_output=True,
            text=True,
            cwd=cli.project_root(),
        )
        if result.returncode != 0:
            pass
        import requests
        from scrape_serebii_data import fetch_index, normalize_name, parse_species

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
    except Exception:
        return {}


def verify_single_pokemon(directory: Path, canonical_data: dict[str, dict]) -> PokemonVerification:
    verification = PokemonVerification(directory=directory)
    directory_name = directory.name
    if directory_name in canonical_data:
        canonical_info = canonical_data[directory_name]
        verification.canonical_name = canonical_info["name"]
        verification.canonical_dex = canonical_info["dex"]
        verification.canonical_types = canonical_info["types"]
        verification.is_valid_pokemon = True
    else:
        verification.is_valid_pokemon = False
        verification.overall_issues.append(
            f"Directory '{directory_name}' not found in Serebii canonical data"
        )
        suggested_name = suggest_correct_name(directory_name, canonical_data)
        if suggested_name:
            verification.overall_issues.append(
                f"Suggested correction: {directory_name} -> {suggested_name}"
            )
        else:
            similar_names = []
            dir_lower = directory_name.lower()
            for canonical_name in canonical_data:
                if canonical_name.lower().startswith(dir_lower[:4]) or dir_lower.startswith(
                    canonical_name.lower()[:4]
                ):
                    similar_names.append(canonical_name)
            if similar_names:
                verification.overall_issues.append(f"Possible matches: {similar_names[:3]}")
    verification.main_png = check_file_status(directory, "main.png", required=True)
    verification.sprite_png = check_file_status(directory, "sprite.png", required=False)
    verification.name_png = check_file_status(directory, "name.png", required=False)
    verification.anime_cry = check_file_status(directory, "anime_cry.*", required=False)
    verification.metadata_json = check_file_status(directory, "metadata.json", required=True)
    if verification.metadata_json.exists:
        try:
            with open(verification.metadata_json.path, encoding="utf-8") as f:
                verification.metadata_content = json.load(f)
            if verification.is_valid_pokemon:
                verification.metadata_issues = validate_metadata_content(
                    verification.metadata_content,
                    verification.canonical_dex,
                    verification.canonical_name,
                    verification.canonical_types,
                )
        except (json.JSONDecodeError, OSError) as e:
            verification.metadata_issues.append(f"Cannot read metadata.json: {e}")
    return verification


def print_verification_summary(verifications: list[PokemonVerification]) -> None:
    len(verifications)
    sum(1 for v in verifications if v.is_valid_pokemon)
    sum(1 for v in verifications if v.has_issues)
    sum(1 for v in verifications if v.critical_issues)
    sum(1 for v in verifications if v.main_png.exists)
    sum(1 for v in verifications if v.sprite_png.exists)
    sum(1 for v in verifications if v.name_png.exists)
    sum(1 for v in verifications if v.anime_cry.exists)
    sum(1 for v in verifications if v.metadata_json.exists)
    invalid_directories = [v for v in verifications if not v.is_valid_pokemon]
    if invalid_directories:
        for v in invalid_directories[:10]:
            if v.overall_issues:
                for _issue in v.overall_issues[:2]:
                    pass
        if len(invalid_directories) > 10:
            pass
    critical_pokemon = [v for v in verifications if v.critical_issues and v.is_valid_pokemon]
    if critical_pokemon:
        for v in critical_pokemon[:5]:
            for _issue in v.critical_issues[:2]:
                pass
        if len(critical_pokemon) > 5:
            pass


def print_detailed_verification(verification: PokemonVerification) -> None:
    v = verification
    if v.is_valid_pokemon:
        pass
    else:
        for issue in v.overall_issues:
            pass
    files_to_check = [
        ("main.png", v.main_png, "🖼️"),
        ("sprite.png", v.sprite_png, "🎨"),
        ("name.png", v.name_png, "🏷️"),
        ("anime_cry.*", v.anime_cry, "🔊"),
        ("metadata.json", v.metadata_json, "📋"),
    ]
    for _filename, status, _icon in files_to_check:
        if status.exists:
            if status.issues:
                for issue in status.issues:
                    pass
        else:
            if status.issues:
                for issue in status.issues:
                    pass
    if v.metadata_content and v.is_valid_pokemon:
        if not v.metadata_issues:
            pass
        else:
            for issue in v.metadata_issues:
                pass
    if v.has_issues:
        if not v.is_valid_pokemon:
            suggested_name = None
            for issue in v.overall_issues:
                if "Suggested correction:" in issue:
                    suggested_name = issue.split(" -> ")[-1]
                    break
            if suggested_name:
                pass
            else:
                pass
        else:
            if not v.main_png.exists:
                pass
            if not v.sprite_png.exists:
                pass
            if not v.name_png.exists:
                pass
            if v.metadata_issues:
                pass


async def fix_pokemon_issues(verification: PokemonVerification, dry_run: bool = True) -> bool:
    if not verification.has_issues:
        return True
    if not verification.is_valid_pokemon:
        return False
    fixed_any = False
    canonical_name = verification.canonical_name
    if not verification.main_png.exists or verification.metadata_issues:
        cmd = [sys.executable, "scripts/scrape_serebii_data.py", "--pokemon", canonical_name]
        if not dry_run:
            cmd.append("--overwrite")
        if dry_run:
            pass
        else:
            result = subprocess.run(
                args=cmd, capture_output=True, text=True, cwd=cli.project_root()
            )
            if result.returncode == 0:
                fixed_any = True
            else:
                pass
    if not verification.sprite_png.exists:
        cmd = [sys.executable, "scripts/download_sprites.py", "--pokemon", canonical_name]
        if dry_run:
            pass
        else:
            result = subprocess.run(
                args=cmd, capture_output=True, text=True, cwd=cli.project_root()
            )
            if result.returncode == 0:
                fixed_any = True
            else:
                pass
    if not verification.name_png.exists:
        cmd = [
            sys.executable,
            "scripts/download_pokemon_logo_font_names.py",
            "--pokemon",
            canonical_name,
        ]
        if dry_run:
            pass
        else:
            result = subprocess.run(
                args=cmd, capture_output=True, text=True, cwd=cli.project_root()
            )
            if result.returncode == 0:
                fixed_any = True
            else:
                pass
    return fixed_any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify Pokemon data completeness and accuracy, optionally fix issues"
    )
    cli.add_pokemon(parser, help="Verify only a specific Pokemon by name/directory")
    cli.add_dry_run(parser, help="Show what would be fixed without making changes")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Automatically fix issues using existing scrapers (use with --dry-run to preview)",
    )
    parser.add_argument(
        "--detailed",
        action="store_true",
        help="Show detailed verification results for each Pokemon",
    )
    parser.add_argument(
        "--critical-only",
        action="store_true",
        help="Only show Pokemon with critical issues (missing main.png, metadata, etc.)",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Remove corrupted directories and add missing Pokemon using Serebii scraper",
    )
    parser.add_argument(
        "--directory",
        type=Path,
        help="Verify a specific directory path (can be outside pokemon_data/)",
    )
    parser.add_argument(
        "--delete-corrupted",
        action="store_true",
        help="Delete directories that don't match any known Pokemon",
    )
    parser.add_argument(
        "--rename-corrupted",
        action="store_true",
        help="Attempt to rename corrupted directories to their correct names",
    )
    add_validation_args(parser)
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    get_script_logger()
    if args.rename_corrupted and args.delete_corrupted:
        return
    if (args.rename_corrupted or args.delete_corrupted) and not args.dry_run:
        response = input("Continue? (y/N): ").strip().lower()
        if response != "y":
            return
    canonical_data = await get_canonical_pokemon_data()
    if not canonical_data:
        return
    if args.directory:
        if not args.directory.exists():
            return
        if not args.directory.is_dir():
            return
        pokemon_dirs = [args.directory]
    elif args.pokemon:
        pokemon_root = cli.pokemon_data_root()
        if not pokemon_root.exists():
            return
        pokemon_dirs = cli.filter_pokemon_directories(args.pokemon, pokemon_root)
        if not pokemon_dirs:
            return
    else:
        pokemon_root = cli.pokemon_data_root()
        if not pokemon_root.exists():
            return
        pokemon_dirs = [
            d for d in pokemon_root.iterdir() if d.is_dir() and not d.name.startswith(".")
        ]
        pokemon_dirs.sort()
    verifications = []
    total = len(pokemon_dirs)
    for _i, directory in enumerate(pokemon_dirs, 1):
        if total > 10:
            pass
        verification = verify_single_pokemon(directory, canonical_data)
        verifications.append(verification)
    if total > 10:
        pass
    if args.critical_only:
        verifications = [v for v in verifications if v.critical_issues]
    if args.pokemon or args.detailed:
        for verification in verifications:
            print_detailed_verification(verification)
    else:
        print_verification_summary(verifications)
    if args.fix and verifications:
        fixed_count = 0
        issues_to_fix = [v for v in verifications if v.has_issues and v.is_valid_pokemon]
        if args.critical_only:
            issues_to_fix = [v for v in issues_to_fix if v.critical_issues]
        for verification in issues_to_fix:
            if await fix_pokemon_issues(verification, dry_run=args.dry_run):
                fixed_count += 1
    if args.cleanup:
        cmd = [sys.executable, "scripts/scrape_serebii_data.py", "--cleanup"]
        if args.dry_run:
            cmd.append("--dry-run")
        result = subprocess.run(args=cmd, cwd=cli.project_root())
        if result.returncode == 0:
            pass
        else:
            pass
    corrupted_verifications = [v for v in verifications if not v.is_valid_pokemon]
    if args.rename_corrupted and corrupted_verifications:
        renamed_count = 0
        for verification in corrupted_verifications:
            suggested_name = None
            for issue in verification.overall_issues:
                if "Suggested correction:" in issue:
                    suggested_name = issue.split(" -> ")[-1]
                    break
            if suggested_name:
                if rename_corrupted_directory(
                    verification.directory, suggested_name, dry_run=args.dry_run
                ):
                    renamed_count += 1
            else:
                pass
    if args.delete_corrupted and corrupted_verifications:
        deleted_count = 0
        for verification in corrupted_verifications:
            if delete_corrupted_directory(verification.directory, dry_run=args.dry_run):
                deleted_count += 1


if __name__ == "__main__":
    asyncio.run(main())
