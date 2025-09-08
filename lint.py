from __future__ import annotations

import argparse
import importlib.util
import logging
import shutil
import subprocess
import sys
import types
from pathlib import Path
from typing import Any


logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def project_root() -> Path:
    return Path(__file__).resolve().parent


def run_ruff_check() -> tuple[bool, str]:
    logger.info("🔍 Running ruff linter...")
    ruff_path = shutil.which("ruff")
    if not ruff_path:
        return False, "❌ ruff executable not found in PATH"
    try:
        result = subprocess.run(
            [ruff_path, "check", "."],
            cwd=project_root(),
            capture_output=True,
            text=True,
            timeout=60,
        )
        success = result.returncode == 0
        output = result.stdout + result.stderr
        if success:
            logger.info("  ✅ Ruff linting passed")
        else:
            logger.error("  ❌ Ruff linting found issues:")
            logger.error(f"    {output}")
        return success, output
    except subprocess.TimeoutExpired:
        logger.error("  ⏰ Ruff linting timed out")
        return False, "Timeout"
    except FileNotFoundError:
        logger.error("  ❌ Ruff not found. Install with: pip install ruff")
        return False, "Ruff not installed"
    except Exception as e:
        logger.error(f"  ❌ Error running ruff: {e}")
        return False, str(e)


def run_ruff_format_check() -> tuple[bool, str]:
    logger.info("📝 Checking code formatting...")
    ruff_path = shutil.which("ruff")
    if not ruff_path:
        return False, "❌ ruff executable not found in PATH"
    try:
        result = subprocess.run(
            [ruff_path, "format", "--check", "."],
            cwd=project_root(),
            capture_output=True,
            text=True,
            timeout=30,
        )
        success = result.returncode == 0
        output = result.stdout + result.stderr
        if success:
            logger.info("  ✅ Code formatting is consistent")
        else:
            logger.error("  ❌ Code formatting issues found:")
            logger.info("    Run 'ruff format .' to fix formatting")
        return success, output
    except Exception as e:
        logger.error(f"  ❌ Error checking format: {e}")
        return False, str(e)


def import_module_from_path(path: str) -> types.ModuleType | None:
    path_obj = Path(path)

    if "src/apps" in str(path_obj):
        parts = path_obj.parts
        src_idx = parts.index("src")
        module_parts = parts[src_idx:-1]
        module_name = ".".join((*module_parts, "app"))

        try:
            return importlib.import_module(module_name)
        except ImportError:
            pass

    spec = importlib.util.spec_from_file_location("app_module", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_app_structure(app_directory: Path) -> dict[str, Any]:
    results = {"name": app_directory.name, "valid": True, "errors": [], "warnings": []}
    app_py = app_directory / "app.py"
    if not app_py.exists():
        results["errors"].append("Missing app.py file")
        results["valid"] = False
        return results
    icon_extensions = [".png", ".jpg", ".jpeg", ".bmp", ".gif"]
    icon_found = any((app_directory / f"menu_icon{ext}").exists() for ext in icon_extensions)
    if not icon_found:
        results["errors"].append(f"Missing menu_icon file with extensions: {icon_extensions}")
        results["valid"] = False
    try:
        module = import_module_from_path(str(app_py))
        app_data = getattr(module, "APP_DATA", None)
        if app_data is None:
            results["errors"].append("Missing APP_DATA constant")
            results["valid"] = False
        elif not isinstance(app_data, dict):
            results["errors"].append("APP_DATA must be a dictionary")
            results["valid"] = False
        else:
            if not app_data.get("name"):
                results["errors"].append("APP_DATA must have a 'name' key with non-empty value")
                results["valid"] = False
            recommended_fields = ["name", "menu_icon_bg_color"]
            missing_recommended = [field for field in recommended_fields if field not in app_data]
            if missing_recommended:
                results["warnings"].append(
                    f"Missing recommended APP_DATA fields: {missing_recommended}"
                )
    except Exception as e:
        results["errors"].append(f"Error importing app.py: {e}")
        results["valid"] = False
    try:
        with open(app_py, encoding="utf-8") as f:
            code = f.read()
        compile(code, str(app_py), "exec")
    except SyntaxError as e:
        results["errors"].append(f"Python syntax error: {e}")
        results["valid"] = False
    except Exception as e:
        results["warnings"].append(f"Could not validate syntax: {e}")
    return results


def validate_all_apps() -> tuple[bool, dict[str, Any]]:
    logger.info("🎮 Validating Pokemon app structure...")
    apps_directory = project_root() / "src" / "apps"
    if not apps_directory.exists():
        logger.error("  ❌ src/apps/ directory not found")
        return False, {}
    results = {"total_apps": 0, "valid_apps": 0, "invalid_apps": 0, "app_details": {}}
    app_dirs = [d for d in apps_directory.iterdir() if d.is_dir() and not d.name.startswith(".")]
    results["total_apps"] = len(app_dirs)
    for app_directory in sorted(app_dirs):
        app_result = validate_app_structure(app_directory)
        results["app_details"][app_directory.name] = app_result
        if app_result["valid"]:
            results["valid_apps"] += 1
            logger.info(f"  ✅ {app_directory.name}: Valid")
        else:
            results["invalid_apps"] += 1
            logger.error(f"  ❌ {app_directory.name}: Invalid")
            for error in app_result["errors"]:
                logger.error(f"      • {error}")
        for warning in app_result["warnings"]:
            logger.warning(f"  ⚠️  {app_directory.name}: {warning}")
    success = results["invalid_apps"] == 0
    logger.info("\n📊 App validation summary:")
    logger.info(f"  Total apps: {results['total_apps']}")
    logger.info(f"  Valid: {results['valid_apps']}")
    logger.info(f"  Invalid: {results['invalid_apps']}")
    return success, results


def validate_project_structure() -> tuple[bool, list[str]]:
    logger.info("📁 Validating project structure...")
    issues = []
    required_dirs = ["src", "scripts", "pokemon_data"]
    required_files = ["requirements.txt", "launcher.py"]
    project_path = project_root()
    for directory_name in required_dirs:
        directory_path = project_path / directory_name
        if not directory_path.exists():
            issues.append(f"Missing required directory: {directory_name}")
        elif not directory_path.is_dir():
            issues.append(f"Expected directory but found file: {directory_name}")
    for file_name in required_files:
        file_path = project_path / file_name
        if not file_path.exists():
            issues.append(f"Missing required file: {file_name}")
        elif not file_path.is_file():
            issues.append(f"Expected file but found directory: {file_name}")
    ruff_configuration = project_path / "ruff.toml"
    if ruff_configuration.exists():
        try:
            import tomllib

            with open(ruff_configuration, mode="rb") as f:
                tomllib.load(f)
        except Exception as e:
            issues.append(f"Invalid ruff.toml: {e}")
    success = len(issues) == 0
    if success:
        logger.info("  ✅ Project structure is valid")
    else:
        logger.error("  ❌ Project structure issues found:")
        for issue in issues:
            logger.error(f"      • {issue}")
    return success, issues


def validate_scraping_scripts_have_validation() -> tuple[bool, list[str]]:
    issues = []
    scripts_directory = project_root() / "scripts"

    # Find all Python scripts, excluding utility modules
    excluded_scripts = [
        "script_logger.py",
        "validation_utils.py",
        "cli.py",
        "browser_utils.py",
        "fix_png_profiles.py",  # Utility script, not a scraper
        "normalize_metadata.py",  # Text normalization utility, not a scraper
        "build_pokemon_data.py",  # Orchestrator script, not a scraper
        "verify_pokemon_data.py",  # Verification/analysis tool, not a scraper
        "__init__.py",
    ]

    scraping_scripts = []
    for script_path in scripts_directory.glob("*.py"):
        script_name = script_path.name
        if script_name not in excluded_scripts:
            scraping_scripts.append(script_name)
    for script_name in scraping_scripts:
        script_path = scripts_directory / script_name
        if not script_path.exists():
            issues.append(f"❌ Missing scraping script: {script_name}")
            continue
        try:
            with open(script_path, encoding="utf-8") as f:
                content = f.read()
            if "def validate_before_scraping(" not in content:
                issues.append(f"❌ {script_name}: Missing validate_before_scraping() function")
            if "validation_only" not in content and "validation-only" not in content:
                issues.append(f"❌ {script_name}: Missing --validation-only argument support")
            if "add_validation_args" not in content:
                issues.append(f"❌ {script_name}: Missing add_validation_args import")
            if "exit(1)" not in content:
                issues.append(f"⚠️  {script_name}: Consider adding exit(1) on validation failure")
        except Exception as e:
            issues.append(f"❌ {script_name}: Error reading file - {e}")
    success = len(issues) == 0
    if success:
        logger.info("✅ All scraping scripts have proper validation functions")
    else:
        logger.error(f"❌ Found {len(issues)} validation issues in scraping scripts:")
        for issue in issues:
            logger.error(f"  {issue}")
    return success, issues


def run_sanity_tests() -> tuple[bool, str]:
    logger.info("🧪 Running comprehensive sanity tests...")
    try:
        from tests.runner import run_user_focused_tests

        success, suites = run_user_focused_tests(show_details=False)

        total_passed = sum(suite.get_passed_count() for suite in suites)
        total_failed = sum(suite.get_failed_count() for suite in suites)
        total_tests = sum(suite.get_total_count() for suite in suites)

        if success:
            logger.info(f"  ✅ All {total_tests} sanity tests passed")
        else:
            logger.error(f"  ❌ {total_failed} of {total_tests} sanity tests failed")

        return success, f"Passed: {total_passed}/{total_tests}"
    except ImportError:
        logger.error("  ❌ Sanity test framework not found. Check tests/ directory.")
        return False, "Sanity tests not available"
    except Exception as e:
        logger.error(f"  ❌ Error running sanity tests: {e}")
        return False, str(e)


def main() -> int:
    parser = argparse.ArgumentParser(description="Lint and validate Pokemon project")
    parser.add_argument(
        "--apps-only", action="store_true", help="Only validate app structure (skip linting)"
    )
    parser.add_argument(
        "--lint-only", action="store_true", help="Only run ruff linting (skip app validation)"
    )
    parser.add_argument(
        "--sanity", action="store_true", help="Run comprehensive sanity tests for user experience"
    )
    parser.add_argument(
        "--fix", action="store_true", help="Automatically fix formatting issues with ruff"
    )
    args = parser.parse_args()
    logger.info("🚀 Pokemon Project Linting and Validation")
    logger.info("=" * 50)
    success_count = 0
    total_checks = 0

    if args.sanity:
        total_checks += 1
        sanity_success, _ = run_sanity_tests()
        if sanity_success:
            success_count += 1
    elif not args.apps_only and not args.lint_only:
        if not args.apps_only:
            total_checks += 2
            if args.fix:
                logger.info("🔧 Auto-fixing code formatting...")
                try:
                    subprocess.run(args=["ruff", "format", "."], cwd=project_root(), check=True)
                    logger.info("  ✅ Code formatting applied")
                except Exception as e:
                    logger.error(f"  ❌ Error auto-fixing: {e}")
            lint_success, _ = run_ruff_check()
            if lint_success:
                success_count += 1
            format_success, _ = run_ruff_format_check()
            if format_success:
                success_count += 1
        if not args.lint_only:
            total_checks += 3
            structure_success, _ = validate_project_structure()
            if structure_success:
                success_count += 1
            apps_success, _ = validate_all_apps()
            if apps_success:
                success_count += 1
            validation_success, _ = validate_scraping_scripts_have_validation()
            if validation_success:
                success_count += 1
    else:
        if not args.apps_only:
            total_checks += 2
            if args.fix:
                logger.info("🔧 Auto-fixing code formatting...")
                try:
                    subprocess.run(args=["ruff", "format", "."], cwd=project_root(), check=True)
                    logger.info("  ✅ Code formatting applied")
                except Exception as e:
                    logger.error(f"  ❌ Error auto-fixing: {e}")
            lint_success, _ = run_ruff_check()
            if lint_success:
                success_count += 1
            format_success, _ = run_ruff_format_check()
            if format_success:
                success_count += 1
        if not args.lint_only:
            total_checks += 3
            structure_success, _ = validate_project_structure()
            if structure_success:
                success_count += 1
            apps_success, _ = validate_all_apps()
            if apps_success:
                success_count += 1
            validation_success, _ = validate_scraping_scripts_have_validation()
            if validation_success:
                success_count += 1
    logger.info("\n" + "=" * 50)
    logger.info("🎯 FINAL SUMMARY")
    logger.info("=" * 50)
    logger.info(f"Passed: {success_count}/{total_checks} checks")
    if success_count == total_checks:
        if args.sanity:
            logger.info("🎉 All sanity tests passed! Your apps work as users expect.")
        else:
            logger.info("🎉 All checks passed! Project is in great shape.")
        return 0
    else:
        if args.sanity:
            logger.warning("⚠️  Some sanity tests failed. User experience may be impacted.")
        else:
            logger.warning("⚠️  Some checks failed. See details above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
