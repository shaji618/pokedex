"""Mini-games for Pokemon Hunt post-catch challenges."""

from .base_minigame import MiniGame, MiniGameResult
from .timing_challenge import TimingChallenge
from .color_detection import ColorDetection

__all__ = ["MiniGame", "MiniGameResult", "TimingChallenge", "ColorDetection"]
