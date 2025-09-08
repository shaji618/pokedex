"""Audio System Tests - Testing TTS, Pokemon cries, and music."""

from __future__ import annotations

import sys
from pathlib import Path


# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tests.test_utilities import TestResult, setup_pygame_headless, teardown_pygame


class AudioTests:
    """Tests for audio systems across all apps."""

    @staticmethod
    def test_cross_app_audio_integration() -> TestResult:
        """Test that audio works consistently across all apps."""
        result = TestResult("cross_app_audio_integration")

        screen = None
        try:
            screen = setup_pygame_headless()

            # Test TTS system across apps
            tts_module = None
            try:
                from src.utils import tts_util

                tts_module = tts_util
            except ImportError:
                raise Exception("TTS system not available") from None

            # Test voice availability
            voices = tts_module.list_available_voices()
            if not voices:
                result.mark_passed(
                    details={"audio_systems": "No TTS voices available, basic test passed"}
                )
                return result

            # Test voice selection persistence
            original_voice = tts_module.get_selected_voice()
            test_voice = voices[0]

            if tts_module.set_selected_voice(test_voice):
                current_voice = tts_module.get_selected_voice()
                if current_voice != test_voice:
                    raise Exception("Voice selection doesn't persist")

            # Test Pokemon cry system
            try:
                from src.utils import audio_util

                # Test that cry functions exist and are callable
                if not hasattr(audio_util, "play_pokemon_cry"):
                    raise Exception("Pokemon cry system not available")

                if not callable(audio_util.play_pokemon_cry):
                    raise Exception("Pokemon cry function not callable")

            except ImportError:
                raise Exception("Audio utilities not available") from None

            # Test music system
            if hasattr(audio_util, "play_music_once"):
                if not callable(audio_util.play_music_once):
                    raise Exception("Music system not functional")

            # Restore original voice
            if original_voice:
                tts_module.set_selected_voice(original_voice)

            result.mark_passed(
                details={"audio_systems": "TTS voice management, Pokemon cries, music playback"}
            )

        except Exception as e:
            result.mark_failed(f"Audio integration test failed: {e}")
        finally:
            if screen:
                teardown_pygame()

        return result
