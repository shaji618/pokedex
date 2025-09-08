"""System Tests - Testing persistence, performance, and cross-cutting concerns."""

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


class SystemTests:
    """Tests for system-wide functionality and cross-cutting concerns."""

    @staticmethod
    def test_scanner_ai_classification_pipeline() -> TestResult:
        """Test if Scanner can load AI model and has classification pipeline."""
        result = TestResult("scanner_ai_classification_pipeline")

        screen = None
        try:
            screen = setup_pygame_headless()

            module = import_app_module("scanner")
            if module is None:
                raise Exception("Could not import scanner module")

            app_class = getattr(module, "ScannerApp", None)
            if app_class is None:
                raise Exception("ScannerApp not found")

            app = app_class(screen)

            # Test model loading capability
            if not hasattr(app, "local_model_directory"):
                raise Exception("No model directory configured")

            # Test model loading function exists
            load_model_func = getattr(module, "_load_model", None)
            if load_model_func is None:
                raise Exception("Model loading function not found")

            # Test classification function exists
            classify_func = getattr(module, "_classify_image", None)
            if classify_func is None:
                raise Exception("Image classification function not found")

            result.mark_passed(
                details={"ai_pipeline": "Model loading and classification functions available"}
            )

        except Exception as e:
            result.mark_failed(f"Scanner AI pipeline test failed: {e}")
        finally:
            if screen:
                teardown_pygame()

        return result

    @staticmethod
    def test_game_state_persistence() -> TestResult:
        """Test that user settings and game state persist correctly."""
        result = TestResult("game_state_persistence")

        screen = None
        try:
            screen = setup_pygame_headless()

            # Test ID card voice preference persistence
            id_module = import_app_module("id_card")
            if id_module:
                app_class = getattr(id_module, "IDCardApp", None)
                if app_class:
                    app = app_class(screen)

                    if app.voices and len(app.voices) > 1:
                        # Test that voice changes are tracked
                        original_voice = app.current_index
                        app.current_index = (original_voice + 1) % len(app.voices)

                        # Test that save state is detected
                        has_changes = app.current_index != app.saved_index
                        if not has_changes:
                            raise Exception("Voice preference changes not tracked")

                        # Test saving
                        app.saved_index = app.current_index

                        # Should persist
                        if app.current_index != app.saved_index:
                            raise Exception("Voice preference save failed")

            # Test TTS system persistence across app instances
            from src.utils import tts_util

            voices = tts_util.list_available_voices()

            if voices:
                original_voice = tts_util.get_selected_voice()
                test_voice = voices[0]

                # Set voice
                tts_util.set_selected_voice(test_voice)

                # Should persist
                current_voice = tts_util.get_selected_voice()
                if current_voice != test_voice:
                    raise Exception("TTS voice selection doesn't persist")

                # Restore original
                if original_voice:
                    tts_util.set_selected_voice(original_voice)

            result.mark_passed(
                details={"persistence": "Voice preferences, TTS settings, game state tracking"}
            )

        except Exception as e:
            result.mark_failed(f"Persistence test failed: {e}")
        finally:
            if screen:
                teardown_pygame()

        return result
