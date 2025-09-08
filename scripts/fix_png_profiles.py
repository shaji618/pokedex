import argparse
import logging
import shutil
from pathlib import Path
from typing import Any


try:
    from PIL import Image
except ImportError:
    import logging
    import sys

    logging.basicConfig(level=logging.ERROR, format="%(message)s")
    logging.error("❌ PIL/Pillow is required. Install with: pip install Pillow")
    sys.exit(1)
try:
    from scripts.script_logger import error, get_script_logger, step, substep, success, warning
except ImportError:
    try:
        import sys
        from pathlib import Path

        sys.path.append(str(Path(__file__).parent))
        from script_logger import error, get_script_logger, step, substep, success, warning
    except ImportError:
        import logging

        logging.basicConfig(level=logging.INFO, format="%(message)s")

        def get_script_logger() -> logging.Logger:
            return logging.getLogger(__name__)

        def step(msg: str, **kwargs: Any) -> None:
            logging.info(f"🔧 {msg}")

        def substep(msg: str, **kwargs: Any) -> None:
            logging.info(f"  {msg}")

        def success(msg: str, **kwargs: Any) -> None:
            logging.info(f"✅ {msg}")

        def warning(msg: str, **kwargs: Any) -> None:
            logging.warning(f"⚠️ {msg}")

        def error(msg: str, **kwargs: Any) -> None:
            logging.error(f"❌ {msg}")


def find_png_files(root_directory: Path, pokemon_only: bool = False) -> list[Path]:
    png_files = []
    if pokemon_only:
        pokemon_data = root_directory / "pokemon_data"
        if pokemon_data.exists():
            png_files.extend(pokemon_data.rglob("*.png"))
    else:
        skip_dirs = {".git", ".venv", "__pycache__", "node_modules", ".pytest_cache"}
        for path in root_directory.rglob("*.png"):
            if any(part in skip_dirs for part in path.parts):
                continue
            png_files.append(path)
    return sorted(png_files)


def has_problematic_icc_profile(png_path: Path) -> bool:
    try:
        with Image.open(png_path) as img:
            return "icc_profile" in img.info
    except Exception as e:
        warning(f"Could not check {png_path.name}: {e}")
        return False


def fix_png_profile(png_path: Path, create_backup: bool = False) -> bool:
    try:
        if create_backup:
            backup_path = png_path.with_suffix(png_path.suffix + ".bak")
            if not backup_path.exists():
                shutil.copy2(png_path, backup_path)
                substep(f"Created backup: {backup_path.name}")
        with Image.open(png_path) as img:
            mode = img.mode
            size = img.size
            data = img.tobytes()
            clean_image = Image.frombytes(mode, size, data)
            clean_image.save(png_path, "PNG", optimize=True)
        return True
    except Exception as e:
        error(f"Failed to fix {png_path.name}: {e}")
        return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fix PNG files with problematic ICC color profiles",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
        """,
    )
    parser.add_argument(
        "--fix", action="store_true", help="Actually fix files (default is dry-run)"
    )
    parser.add_argument("--backup", action="store_true", help="Create .bak files before fixing")
    parser.add_argument(
        "--pokemon-only", action="store_true", help="Only process files in pokemon_data/ directory"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Show detailed progress for each file"
    )
    args = parser.parse_args()
    script_directory = Path(__file__).parent
    project_root = script_directory.parent
    step("🔍 Scanning for PNG files with problematic ICC profiles...")
    png_files = find_png_files(project_root, args.pokemon_only)
    substep(f"Found {len(png_files)} PNG files to check")
    if args.pokemon_only:
        substep("Scope: pokemon_data/ directory only")
    else:
        substep("Scope: entire project")
    problematic_files = []
    for png_file in png_files:
        if has_problematic_icc_profile(png_file):
            problematic_files.append(png_file)
            if args.verbose:
                substep(f"📋 {png_file.relative_to(project_root)} has ICC profile")
    if not problematic_files:
        success("🎉 No PNG files with problematic ICC profiles found!")
        return
    step(f"📊 Found {len(problematic_files)} PNG files with ICC profiles")
    if not args.fix:
        step("🔍 DRY RUN - Use --fix to actually modify files")
        for png_file in problematic_files[:10]:
            substep(f"Would fix: {png_file.relative_to(project_root)}")
        if len(problematic_files) > 10:
            substep(f"... and {len(problematic_files) - 10} more files")
        return
    step(f"🔧 Fixing {len(problematic_files)} PNG files...")
    if args.backup:
        substep("Creating backup files (.bak)")
    fixed_count = 0
    failed_count = 0
    for png_file in problematic_files:
        if args.verbose:
            substep(f"Fixing: {png_file.relative_to(project_root)}")
        if fix_png_profile(png_file, args.backup):
            fixed_count += 1
        else:
            failed_count += 1
    if fixed_count > 0:
        success(f"✅ Fixed {fixed_count} PNG files")
    if failed_count > 0:
        warning(f"⚠️ Failed to fix {failed_count} PNG files")
    step("🎉 PNG profile cleanup complete!")
    step("💡 The libpng warnings should now be gone when running the apps")


if __name__ == "__main__":
    main()
