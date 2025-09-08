"""Pokedex App Tests - Testing search and navigation workflows."""

from __future__ import annotations

import sys
from pathlib import Path


# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.test_utilities import (
    TestResult,
    import_app_module,
    setup_pygame_headless,
    teardown_pygame,
)


class PokedexTests:
    """Tests for Pokedex search and navigation functionality."""

    @staticmethod
    def test_search_workflow() -> TestResult:
        """Test if Pokedex search actually works for finding Pokemon."""
        result = TestResult("pokedex_pokemon_search_workflow")

        screen = None
        try:
            screen = setup_pygame_headless()

            module = import_app_module("pokedex")
            if module is None:
                raise Exception("Could not import pokedex module")

            app_class = getattr(module, "PokedexApp", None)
            if app_class is None:
                raise Exception("PokedexApp not found")

            app = app_class(screen)

            if not hasattr(app, "all_names") or not app.all_names:
                raise Exception("Pokemon names not loaded")

            original_count = len(app.all_names)

            # Test multi-character search (more realistic)
            app.add_to_search("p")
            app.add_to_search("i")  # "pi" - should find Pikachu, etc.

            filtered_results = app.get_visible_names(100)

            if len(filtered_results) >= original_count:
                raise Exception("Multi-character search filtering doesn't work")

            # Verify specific Pokemon in results
            pi_pokemon = [name for name in filtered_results if name.lower().startswith("pi")]
            if not pi_pokemon:
                raise Exception("Search should find Pokemon starting with 'pi' (like Pikachu)")

            # Test search refinement
            app.add_to_search("k")  # "pik" - should narrow down further

            more_filtered = app.get_visible_names(100)
            if len(more_filtered) >= len(filtered_results):
                raise Exception("Search refinement doesn't narrow results")

            # Test backspace/deletion
            if hasattr(app, "remove_from_search"):
                app.remove_from_search()  # Remove 'k', back to "pi"
                backspace_results = app.get_visible_names(100)

                if len(backspace_results) <= len(more_filtered):
                    raise Exception("Backspace doesn't expand search results")

            # Test clear search
            app.clear_search()
            if app.prefix != "":
                raise Exception("Search clear doesn't reset prefix")

            # Test navigation (if available)
            if hasattr(app, "scroll_offset"):
                original_offset = app.scroll_offset

                # Test scrolling
                if hasattr(app, "scroll_down"):
                    app.scroll_down()
                    if app.scroll_offset == original_offset:
                        raise Exception("Scroll down doesn't change offset")

                if hasattr(app, "scroll_up"):
                    app.scroll_up()
                    # Should move back towards original position

            result.mark_passed(
                details={
                    "workflow_tested": "Multi-char search, refinement, backspace, navigation, clear"
                }
            )

        except Exception as e:
            result.mark_failed(f"Pokedex search test failed: {e}")
        finally:
            if screen:
                teardown_pygame()

        return result
