"""Who's That Pokemon Game Tests - Testing guessing game flow."""

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


class WhosThatPokemonTests:
    """Tests for Who's That Pokemon guessing game."""

    @staticmethod
    def test_game_flow() -> TestResult:
        """Test if Who's That Pokemon game flow works."""
        result = TestResult("whos_that_pokemon_game_flow")

        screen = None
        try:
            screen = setup_pygame_headless()

            module = import_app_module("whos_that_pokemon")
            if module is None:
                raise Exception("Could not import whos_that_pokemon module")

            app_class = getattr(module, "WhosThatPokemonApp", None)
            if app_class is None:
                raise Exception("WhosThatPokemonApp not found")

            app = app_class(screen)

            # Test initial state - silhouette phase
            if not hasattr(app, "species") or not app.species:
                raise Exception("No Pokemon species loaded")

            if not hasattr(app, "phase"):
                raise Exception("Game doesn't have phase system")

            if app.phase != 0:
                raise Exception("Game should start in silhouette phase (0)")

            # Test visual assets loaded
            if not hasattr(app, "creature_scaled"):
                raise Exception("Pokemon image not loaded")

            if not hasattr(app, "name_scaled"):
                raise Exception("Pokemon name image not prepared")

            # Test game progression through phases
            # Phase 0 -> 1: Should reveal Pokemon and play cry
            app._advance_game()
            if app.phase != 1:
                raise Exception("Game doesn't advance from silhouette to reveal phase")

            # Phase 1 -> 2: Should show name
            app._advance_game()
            if app.phase != 2:
                raise Exception("Game doesn't advance from reveal to name phase")

            # Phase 2 -> 0: Should load new Pokemon and restart
            app._advance_game()
            if app.phase != 0:
                raise Exception("Game doesn't restart cycle after name phase")

            # Verify new Pokemon loaded (might be same by chance, but species should be set)
            if not app.species:
                raise Exception("New Pokemon not loaded after cycle restart")

            # Test that multiple cycles work
            for cycle in range(3):
                for phase_step in range(3):
                    app._advance_game()
                    expected_phase = (phase_step + 1) % 3
                    if app.phase != expected_phase:
                        raise Exception(
                            f"Game phase progression broken at cycle {cycle}, step {phase_step}"
                        )

            result.mark_passed(
                details={
                    "game_flow": "Complete phase cycle: silhouette -> reveal -> name -> restart"
                }
            )

        except Exception as e:
            result.mark_failed(f"Who's That Pokemon game flow test failed: {e}")
        finally:
            if screen:
                teardown_pygame()

        return result
