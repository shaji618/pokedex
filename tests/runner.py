#!/usr/bin/env python3
"""Pokemon Game Test Runner - User Experience Focused.

Tests what matters: Can users actually play the games?
No more import validation garbage.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


# Add parent directory to path so we can import src modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from tests.audio.audio_tests import AudioTests
from tests.gameplay.pokedex_tests import PokedexTests

# Import test classes from organized modules
from tests.gameplay.pokemon_hunt_tests import PokemonHuntTests
from tests.gameplay.whos_that_pokemon_tests import WhosThatPokemonTests
from tests.system.system_tests import SystemTests
from tests.test_utilities import TestSuite
from tests.ui.id_card_tests import IDCardTests


def print_test_suite_results(suite: TestSuite, show_details: bool = False) -> None:
    """Print results for a test suite."""
    passed_count = suite.get_passed_count()
    total_count = suite.get_total_count()

    if suite.is_all_passed():
        print(f"✅ {suite.suite_name}: {passed_count}/{total_count} passed")
    else:
        failed_count = suite.get_failed_count()
        print(f"❌ {suite.suite_name}: {passed_count}/{total_count} passed, {failed_count} failed")

    if show_details or not suite.is_all_passed():
        for result in suite.results:
            status = "✅" if result.passed else "❌"
            print(f"  {status} {result.test_name}")

            if not result.passed and result.error_message:
                print(f"    Error: {result.error_message}")
            elif show_details and result.passed and result.details:
                print(f"    Details: {result.details}")


def print_comprehensive_summary(suites: list[TestSuite]) -> None:
    """Print overall test summary."""
    total_passed = sum(suite.get_passed_count() for suite in suites)
    total_tests = sum(suite.get_total_count() for suite in suites)
    total_failed = total_tests - total_passed

    print("\n" + "=" * 60)
    print("🎮 POKEMON GAME TEST SUMMARY")
    print("=" * 60)

    if total_failed == 0:
        print(f"🎉 ALL TESTS PASSED! ({total_passed}/{total_tests})")
        print("✨ Your Pokemon games are ready for users! ✨")
    else:
        print(f"⚠️  {total_failed} user workflows failed out of {total_tests}")
        print("🔧 Fix these issues to ensure great user experience.")

        for suite in suites:
            if not suite.is_all_passed():
                failed_tests = [r for r in suite.results if not r.passed]
                for test in failed_tests:
                    print(f"  • {test.test_name}: {test.error_message}")


def run_user_focused_tests(show_details: bool = False) -> tuple[bool, list[TestSuite]]:
    """Run tests that actually matter to users."""
    print("🎮 Pokemon Game User Experience Testing")
    print("=" * 50)
    print("Testing what matters: Can users actually play your games?")

    suites = []

    # Gameplay Tests
    print("\n🎯 Running Gameplay Tests...")
    start_time = time.time()
    gameplay_suite = TestSuite("Gameplay Tests")
    gameplay_suite.add_result(PokemonHuntTests.test_core_gameplay())
    gameplay_suite.add_result(PokedexTests.test_search_workflow())
    gameplay_suite.add_result(WhosThatPokemonTests.test_game_flow())
    execution_time = time.time() - start_time
    print(f"Gameplay Tests completed in {execution_time:.2f}s")
    suites.append(gameplay_suite)
    print_test_suite_results(gameplay_suite, show_details)

    # UI Tests
    print("\n🖥️  Running UI Tests...")
    start_time = time.time()
    ui_suite = TestSuite("UI Tests")
    ui_suite.add_result(IDCardTests.test_complete_user_workflow())
    ui_suite.add_result(IDCardTests.test_voice_switching_performance())
    execution_time = time.time() - start_time
    print(f"UI Tests completed in {execution_time:.2f}s")
    suites.append(ui_suite)
    print_test_suite_results(ui_suite, show_details)

    # Audio Tests
    print("\n🎵 Running Audio Tests...")
    start_time = time.time()
    audio_suite = TestSuite("Audio Tests")
    audio_suite.add_result(AudioTests.test_cross_app_audio_integration())
    execution_time = time.time() - start_time
    print(f"Audio Tests completed in {execution_time:.2f}s")
    suites.append(audio_suite)
    print_test_suite_results(audio_suite, show_details)

    # System Tests
    print("\n🔧 Running System Tests...")
    start_time = time.time()
    system_suite = TestSuite("System Tests")
    system_suite.add_result(SystemTests.test_scanner_ai_classification_pipeline())
    system_suite.add_result(SystemTests.test_game_state_persistence())
    execution_time = time.time() - start_time
    print(f"System Tests completed in {execution_time:.2f}s")
    suites.append(system_suite)
    print_test_suite_results(system_suite, show_details)

    print_comprehensive_summary(suites)

    all_passed = all(suite.is_all_passed() for suite in suites)
    return all_passed, suites


def create_argument_parser() -> argparse.ArgumentParser:
    """Create command line argument parser."""
    parser = argparse.ArgumentParser(
        description="Run user-focused tests for Pokemon games",
        epilog="Tests actual gameplay functionality, not technical implementation details.",
    )

    parser.add_argument(
        "--details", action="store_true", help="Show detailed test results and execution times"
    )

    return parser


def main() -> int:
    """Main entry point."""
    parser = create_argument_parser()
    args = parser.parse_args()

    try:
        success, suites = run_user_focused_tests(show_details=args.details)
        return 0 if success else 1

    except KeyboardInterrupt:
        print("\n❌ Testing interrupted by user")
        return 1
    except Exception as e:
        print(f"\n❌ Testing framework error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
