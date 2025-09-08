from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parent


def run_command(command: list[str], description: str) -> bool:
    try:
        result = subprocess.run(  # noqa: S603
            command, cwd=project_root(), check=True, capture_output=True, text=True
        )
        if result.stdout.strip():
            pass
        return True
    except subprocess.CalledProcessError:
        return False
    except FileNotFoundError:
        return False


def main() -> int:
    steps = [
        (
            ["python", "-m", "pip", "install", "-r", "requirements.txt"],
            "Installing Python dependencies",
        ),
        (["pre-commit", "install"], "Installing pre-commit git hooks"),
        (["pre-commit", "install", "--hook-type", "pre-push"], "Installing pre-push hooks"),
        (["python", "lint.py"], "Testing linter and validation setup"),
    ]

    success_count = 0
    for command, description in steps:
        if run_command(command, description):
            success_count += 1
        else:
            break

    if success_count == len(steps):
        return 0
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main())
