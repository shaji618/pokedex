"""Test Configuration - User Experience Focused.

Only configuration needed for testing actual user workflows.
No more technical validation nonsense.
"""

from __future__ import annotations


# Performance thresholds that actually matter to users
PERFORMANCE_THRESHOLDS = {
    "voice_switch_seconds": 1.0,  # Voice switching should be instant
    "game_startup_seconds": 3.0,  # Games should start quickly
    "search_response_seconds": 0.5,  # Search should be responsive
}

# Test environment settings
TEST_SCREEN_SIZE = (800, 600)
TEST_TIMEOUT_SECONDS = 10.0
