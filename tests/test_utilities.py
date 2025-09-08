from __future__ import annotations

import contextlib
import importlib.util
import os
import sys
import time
import types
from collections.abc import Generator
from pathlib import Path
from typing import Any, Never

import pygame

from tests.test_configuration import TEST_SCREEN_SIZE, TEST_TIMEOUT_SECONDS


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def setup_pygame_headless() -> pygame.Surface:
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    pygame.init()
    pygame.display.init()
    return pygame.display.set_mode(TEST_SCREEN_SIZE)


def teardown_pygame() -> None:
    with contextlib.suppress(Exception):
        pygame.quit()


def setup_project_paths() -> None:
    root_path = str(project_root())
    src_path = str(project_root() / "src")

    if root_path not in sys.path:
        sys.path.insert(0, root_path)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


def import_app_module(app_name: str) -> types.ModuleType | None:
    setup_project_paths()
    app_path = project_root() / "src" / "apps" / app_name / "app.py"

    if not app_path.exists():
        return None

    module_name = f"apps.{app_name}.app"
    spec = importlib.util.spec_from_file_location(module_name, app_path)

    if spec is None or spec.loader is None:
        return None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def import_utils_module(module_name: str) -> types.ModuleType | None:
    setup_project_paths()
    utils_path = project_root() / "src" / "utils" / f"{module_name}.py"

    if not utils_path.exists():
        return None

    spec = importlib.util.spec_from_file_location(f"utils.{module_name}", utils_path)

    if spec is None or spec.loader is None:
        return None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def get_apps_directory() -> Path:
    return project_root() / "src" / "apps"


def get_pokemon_data_directory() -> Path:
    return project_root() / "pokemon_data"


def get_utils_directory() -> Path:
    return project_root() / "src" / "utils"


def find_app_directories() -> list[str]:
    apps_dir = get_apps_directory()
    if not apps_dir.exists():
        return []

    return [d.name for d in apps_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]


def find_pokemon_data_directories() -> list[str]:
    data_dir = get_pokemon_data_directory()
    if not data_dir.exists():
        return []

    return [d.name for d in data_dir.iterdir() if d.is_dir() and not d.name.startswith(".")]


def find_utils_modules() -> list[str]:
    utils_dir = get_utils_directory()
    if not utils_dir.exists():
        return []

    return [
        f.stem
        for f in utils_dir.iterdir()
        if f.is_file() and f.suffix == ".py" and not f.name.startswith("_")
    ]


def time_function_execution(func: callable, *args: Any, **kwargs: Any) -> tuple[Any, float]:
    start_time = time.time()
    try:
        result = func(*args, **kwargs)
        execution_time = time.time() - start_time
        return result, execution_time
    except Exception as e:
        execution_time = time.time() - start_time
        raise e


# Generator import moved to top


@contextlib.contextmanager
def timeout_context(seconds: float = TEST_TIMEOUT_SECONDS) -> Generator[None, None, None]:
    import signal

    def timeout_handler(signum: int, frame: object) -> Never:
        raise TimeoutError(f"Operation timed out after {seconds} seconds")

    if hasattr(signal, "SIGALRM"):
        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(int(seconds))
        try:
            yield
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
    else:
        yield


def safe_import_with_timeout(
    module_path: str, timeout_seconds: float = 5.0
) -> tuple[types.ModuleType | None, str | None]:
    try:
        with timeout_context(timeout_seconds):
            if module_path.startswith("apps."):
                app_name = module_path.split(".")[1]
                module = import_app_module(app_name)
            elif module_path.startswith("utils."):
                utils_name = module_path.split(".")[1]
                module = import_utils_module(utils_name)
            else:
                spec = importlib.util.spec_from_file_location("test_module", module_path)
                if spec is None or spec.loader is None:
                    return None, "Could not create module spec"
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
            return module, None
    except TimeoutError:
        return None, f"Import timed out after {timeout_seconds} seconds"
    except Exception as e:
        return None, f"Import failed: {e}"


def check_file_exists_and_readable(file_path: Path) -> tuple[bool, str | None]:
    if not file_path.exists():
        return False, f"File does not exist: {file_path}"

    if not file_path.is_file():
        return False, f"Path is not a file: {file_path}"

    try:
        # Try reading as binary first (works for all file types)
        with open(file_path, "rb") as f:
            f.read(1)
        return True, None
    except Exception as e:
        return False, f"File not readable: {e}"


def check_directory_exists_and_accessible(dir_path: Path) -> tuple[bool, str | None]:
    if not dir_path.exists():
        return False, f"Directory does not exist: {dir_path}"

    if not dir_path.is_dir():
        return False, f"Path is not a directory: {dir_path}"

    try:
        list(dir_path.iterdir())
        return True, None
    except Exception as e:
        return False, f"Directory not accessible: {e}"


class TestResult:
    def __init__(self, test_name: str) -> None:
        self.test_name = test_name
        self.passed = False
        self.error_message: str | None = None
        self.execution_time: float = 0.0
        self.details: dict[str, Any] = {}

    def mark_passed(
        self, execution_time: float = 0.0, details: dict[str, Any] | None = None
    ) -> None:
        self.passed = True
        self.execution_time = execution_time
        if details:
            self.details = details

    def mark_failed(
        self, error_message: str, execution_time: float = 0.0, details: dict[str, Any] | None = None
    ) -> None:
        self.passed = False
        self.error_message = error_message
        self.execution_time = execution_time
        if details:
            self.details = details


class TestSuite:
    def __init__(self, suite_name: str) -> None:
        self.suite_name = suite_name
        self.results: list[TestResult] = []

    def add_result(self, result: TestResult) -> None:
        self.results.append(result)

    def get_passed_count(self) -> int:
        return sum(1 for r in self.results if r.passed)

    def get_failed_count(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    def get_total_count(self) -> int:
        return len(self.results)

    def is_all_passed(self) -> bool:
        return self.get_failed_count() == 0

    def get_total_execution_time(self) -> float:
        return sum(r.execution_time for r in self.results)
