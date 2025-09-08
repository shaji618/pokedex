from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parent


def run_command(command: list[str], description: str, show_output: bool = True) -> bool:
    try:
        if show_output:
            result = subprocess.run(command, cwd=project_root(), check=True)  # noqa: S603
        else:
            result = subprocess.run(  # noqa: S603
                command, cwd=project_root(), check=True, capture_output=True, text=True
            )
            if result.stdout.strip():
                pass
        return True
    except subprocess.CalledProcessError as e:
        if hasattr(e, "stderr") and e.stderr:
            pass
        return False
    except FileNotFoundError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Run pre-commit hooks manually for testing")
    parser.add_argument(
        "--hook",
        choices=["linter", "apps", "sanity", "ruff", "all"],
        default="all",
        help="Which specific hook to run (default: all)",
    )
    parser.add_argument(
        "--files",
        action="store_true",
        help="Run hooks only on staged files (default: run on all files)",
    )
    parser.add_argument("--verbose", action="store_true", help="Show detailed output from commands")

    args = parser.parse_args()

    if args.hook == "all":
        hooks_to_run = [
            (
                ["pre-commit", "run", "--all-files"] if not args.files else ["pre-commit", "run"],
                "Running all pre-commit hooks",
            ),
        ]
    elif args.hook == "linter":
        hooks_to_run = [
            (["python", "lint.py", "--lint-only"], "Running Pokemon linter"),
        ]
    elif args.hook == "apps":
        hooks_to_run = [
            (["python", "lint.py", "--apps-only"], "Running Pokemon app validation"),
        ]
    elif args.hook == "sanity":
        hooks_to_run = [
            (["python", "lint.py", "--sanity"], "Running Pokemon sanity tests"),
        ]
    elif args.hook == "ruff":
        hooks_to_run = [
            (["ruff", "check", "."], "Running ruff linter"),
            (["ruff", "format", "--check", "."], "Checking ruff formatting"),
        ]

    success_count = 0
    for command, description in hooks_to_run:
        if run_command(command, description, show_output=args.verbose):
            success_count += 1

    if success_count == len(hooks_to_run):
        return 0
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main())
