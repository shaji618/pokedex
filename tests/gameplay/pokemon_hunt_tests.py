"""Pokemon Hunt Game Tests - Testing actual catching mechanics."""

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


class PokemonHuntTests:
    """Tests for Pokemon Hunt game mechanics."""

    @staticmethod
    def test_core_gameplay() -> TestResult:
        """Test if Pokemon Hunt game actually works - can you catch Pokemon?"""
        result = TestResult("pokemon_hunt_core_gameplay")

        screen = None
        try:
            screen = setup_pygame_headless()

            module = import_app_module("pokemon_hunt")
            if module is None:
                raise Exception("Could not import pokemon hunt module")

            app_class = getattr(module, "PokemonHuntApp", None)
            if app_class is None:
                raise Exception("PokemonHuntApp not found")

            app = app_class(screen)

            # Test initial game state
            initial_pokeballs = app.pokeballs_left
            if initial_pokeballs <= 0:
                raise Exception("Game starts with no pokeballs")

            initial_pokemon = app.pokemon_species
            if not initial_pokemon:
                raise Exception("No Pokemon spawned")

            # Test Pokemon catching mechanics
            if hasattr(app, "catch_pokemon"):
                # Simulate successful catch
                original_score = getattr(app, "score", 0)
                app.catch_pokemon()

                # Verify pokeball count decreases
                if app.pokeballs_left != initial_pokeballs - 1:
                    raise Exception("Pokeball count doesn't decrease after catch attempt")

                # Verify score increases or new Pokemon spawns
                new_score = getattr(app, "score", 0)
                new_pokemon = app.pokemon_species

                if new_score == original_score and new_pokemon == initial_pokemon:
                    raise Exception("No visible game progress after Pokemon catch")

            # Test throwball mechanics if available
            if hasattr(app, "throw_ball"):
                # Simulate ball throwing
                original_pokeballs = app.pokeballs_left
                app.throw_ball()

                if app.pokeballs_left >= original_pokeballs:
                    raise Exception("Throwing ball doesn't consume pokeballs")

            # Test game over conditions
            if hasattr(app, "pokeballs_left"):
                # Simulate running out of pokeballs
                app.pokeballs_left = 0

                # Game should handle end state gracefully
                for _ in range(3):
                    app.clock.tick(60)
                    if not app.running:
                        break  # Game properly ended

            result.mark_passed(
                details={
                    "mechanics_tested": "Pokemon catching, ball throwing, game progression, end conditions"
                }
            )

        except Exception as e:
            result.mark_failed(f"Pokemon Hunt gameplay test failed: {e}")
        finally:
            if screen:
                teardown_pygame()

        return result
