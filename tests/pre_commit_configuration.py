from __future__ import annotations

import os


def is_running_in_pre_commit() -> bool:
    return (
        os.environ.get("PRE_COMMIT") == "1"
        or os.environ.get("CI") == "true"
        or os.environ.get("GITHUB_ACTIONS") == "true"
    )


def get_pre_commit_test_configuration() -> dict[str, bool]:
    if is_running_in_pre_commit():
        return {
            "skip_camera_tests": True,
            "skip_heavy_ml_tests": True,
            "use_quick_mode": True,
            "reduce_sample_sizes": True,
            "shorter_timeouts": True,
            "skip_memory_tests": False,
            "skip_consistency_tests": True,
        }
    else:
        return {
            "skip_camera_tests": False,
            "skip_heavy_ml_tests": False,
            "use_quick_mode": False,
            "reduce_sample_sizes": False,
            "shorter_timeouts": False,
            "skip_memory_tests": False,
            "skip_consistency_tests": False,
        }
