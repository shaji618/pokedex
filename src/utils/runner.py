import importlib
from typing import Any

import pygame


def run_app(screen: pygame.Surface, app_module_name: str) -> bool:
    try:
        module = importlib.import_module(app_module_name)

        function = getattr(module, "run_on_existing_display", None)
        if callable(function):
            function(screen)
            return True

        run_function = getattr(module, "run", None)
        if callable(run_function):
            run_function()
            return True

        return False
    except Exception:
        return False


def get_app_metadata(app_module_name: str) -> dict[str, Any] | None:
    try:
        module = importlib.import_module(app_module_name)
        return getattr(module, "APP_DATA", None)
    except Exception:
        return None
