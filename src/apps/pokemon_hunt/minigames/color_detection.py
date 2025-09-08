"""Color detection mini-game for Pokemon Hunt using camera."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import cv2
import numpy as np
import pygame

from src.utils.camera_util import CameraCapture
from src.utils.pokemon_types import PokemonType, TYPE_WEAK_TO
from .base_minigame import MiniGame, MiniGameResult

if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)

# Color detection constants
COLOR_DETECTION_BASE_TIME = 15.0  # base seconds to find target colors
COLOR_DETECTION_TIME_PER_WEAKNESS = 3.0  # additional seconds per weakness type
COLOR_DETECTION_SUCCESS_THRESHOLD = 0.20  # 5% of screen must be target color
COLOR_DETECTION_FEEDBACK_DURATION = 2.0  # seconds to show success/failure message

# Pokemon type to color mappings (thematically appropriate)
TYPE_COLOR_MAPPINGS = {
    PokemonType.NORMAL: "gray",
    PokemonType.FIRE: "red",
    PokemonType.WATER: "blue",
    PokemonType.ELECTRIC: "yellow",
    PokemonType.GRASS: "green",
    PokemonType.ICE: "cyan",
    PokemonType.FIGHTING: "brown",
    PokemonType.POISON: "purple",
    PokemonType.GROUND: "brown",
    PokemonType.FLYING: "white",
    PokemonType.PSYCHIC: "pink",
    PokemonType.BUG: "bright_green",  # brighter green than grass
    PokemonType.ROCK: "gray",
    PokemonType.GHOST: "purple",
    PokemonType.DRAGON: "purple",
    PokemonType.DARK: "black",
    PokemonType.STEEL: "silver",
    PokemonType.FAIRY: "pink",
}

# HSV color ranges for detection (Hue, Saturation, Value)
COLOR_HSV_RANGES = {
    "red": [
        # Red wraps around in HSV, so we need two ranges
        ((0, 50, 50), (10, 255, 255)),  # Lower red range
        ((170, 50, 50), (180, 255, 255)),  # Upper red range
    ],
    "orange": [((10, 50, 50), (25, 255, 255))],
    "yellow": [((25, 50, 50), (35, 255, 255))],
    "bright_green": [((35, 50, 50), (65, 255, 255))],  # Bright green
    "green": [((65, 50, 50), (85, 255, 255))],  # Darker green
    "cyan": [((85, 50, 50), (100, 255, 255))],
    "blue": [((100, 50, 50), (130, 255, 255))],
    "purple": [((130, 50, 50), (160, 255, 255))],
    "pink": [((160, 50, 50), (170, 255, 255))],
    "brown": [((10, 50, 20), (25, 255, 150))],  # Orange/red with lower saturation and value
    "gray": [((0, 0, 50), (180, 30, 200))],  # Any hue, low saturation, medium value
    "silver": [((0, 0, 150), (180, 30, 255))],  # Any hue, low saturation, high value
    "white": [((0, 0, 200), (180, 30, 255))],  # Any hue, very low saturation, high value
    "black": [((0, 0, 0), (180, 255, 50))],  # Any hue, any saturation, low value
}


# RGB colors for displaying colored text
COLOR_RGB = {
    "red": (255, 100, 100),
    "orange": (255, 165, 0),
    "yellow": (255, 255, 100),
    "bright_green": (150, 255, 150),
    "green": (100, 255, 100),
    "cyan": (100, 255, 255),
    "blue": (100, 150, 255),
    "purple": (200, 100, 255),
    "pink": (255, 150, 200),
    "brown": (165, 100, 42),
    "gray": (150, 150, 150),
    "silver": (192, 192, 192),
    "white": (255, 255, 255),
    "black": (100, 100, 100),  # Slightly gray so it's visible
}


class ColorDetection(MiniGame):
    """Camera-based color detection mini-game."""

    def __init__(
        self,
        screen: pygame.Surface,
        pokemon_species: str,
        pokemon_speed: int,
        pokemon_types: list[str],
    ) -> None:
        """Initialize the color detection mini-game.

        Args:
            screen: The pygame screen surface to render on
            pokemon_species: Name of the Pokemon being caught
            pokemon_speed: Speed stat of the Pokemon (affects difficulty)
            pokemon_types: List of Pokemon types to determine target colors based on weaknesses
        """
        super().__init__(screen, pokemon_species, pokemon_speed)
        self.pokemon_types = pokemon_types

        # Determine weakness types and their corresponding colors
        self.weakness_types = self._determine_weakness_types()
        self.valid_colors = self._get_colors_for_weaknesses()

        # Calculate time limit based on number of weaknesses
        self.time_limit = COLOR_DETECTION_BASE_TIME + (
            len(self.weakness_types) * COLOR_DETECTION_TIME_PER_WEAKNESS
        )

        # Camera setup
        self.camera: CameraCapture | None = None
        self.camera_initialized = False

        # Game state
        self.start_time = 0.0
        self.time_remaining = self.time_limit
        self.challenge_completed = False
        self.showing_feedback = False
        self.feedback_start_time = 0.0
        self.success = False
        self.detected_color = ""  # Which color was detected for success message

        # Visual feedback
        self.detection_percentage = 0.0
        self.last_frame: pygame.Surface | None = None

    def _determine_weakness_types(self) -> list[PokemonType]:
        """Determine what types this Pokemon is weak to."""
        if not self.pokemon_types:
            return [PokemonType.FIRE]  # Default fallback

        weakness_types = set()

        for type_name in self.pokemon_types:
            try:
                pokemon_type = PokemonType(type_name.lower())
                # Get what this type is weak to
                weaknesses = TYPE_WEAK_TO.get(pokemon_type, set())
                weakness_types.update(weaknesses)
            except ValueError:
                logger.warning(f"Unknown Pokemon type: {type_name}")

        # Convert back to list, sorted for consistency
        weakness_list = sorted(list(weakness_types), key=lambda x: x.value)

        # Ensure we have at least one weakness
        if not weakness_list:
            weakness_list = [PokemonType.FIRE]

        return weakness_list

    def _get_colors_for_weaknesses(self) -> list[str]:
        """Get the colors corresponding to weakness types."""
        colors = []
        for weakness_type in self.weakness_types:
            color = TYPE_COLOR_MAPPINGS.get(weakness_type, "red")
            if color not in colors:  # Avoid duplicates
                colors.append(color)
        return colors

    def start(self) -> None:
        """Start the color detection mini-game."""
        self.start_time = time.time()
        self.time_remaining = self.time_limit
        self.challenge_completed = False
        self.showing_feedback = False
        self.success = False
        self.detection_percentage = 0.0
        self.detected_color = ""
        self.result = MiniGameResult.IN_PROGRESS

        # Initialize camera
        try:
            self.camera = CameraCapture()
            self.camera.initialize()
            self.camera_initialized = True
            logger.info(f"Camera initialized for color detection mini-game")
        except Exception as e:
            logger.error(f"Failed to initialize camera: {e}")
            self.camera_initialized = False
            # Fail immediately if camera can't be initialized
            self._handle_failure("Camera not available")
            return

        weakness_names = [wt.value for wt in self.weakness_types]
        color_names = [color.replace("_", " ") for color in self.valid_colors]
        logger.info(
            f"Color detection started for {self.pokemon_species} - weak to {weakness_names}, looking for colors {color_names}"
        )

        # Start preparation phase
        self.start_preparation()

    def update(self, dt: float) -> None:
        """Update the color detection mini-game."""
        if self.result != MiniGameResult.IN_PROGRESS:
            return

        # Handle preparation phase
        if self.preparation_active:
            if self.update_preparation(dt):
                # Preparation complete, start actual challenge
                logger.debug("Color detection preparation complete - starting camera detection!")
            return

        # Handle feedback display period
        if self.showing_feedback:
            if time.time() - self.feedback_start_time >= COLOR_DETECTION_FEEDBACK_DURATION:
                # Feedback complete, set final result
                self.result = MiniGameResult.SUCCESS if self.success else MiniGameResult.FAILURE
            return

        if self.challenge_completed or not self.camera_initialized:
            return

        # Update time remaining
        self.time_remaining = self.time_limit - (time.time() - self.start_time)

        # Check if time is up
        if self.time_remaining <= 0:
            self._handle_failure("Time's up!")
            return

        # Get camera frame and analyze for target color
        if self.camera is not None:
            frame_surface = self.camera.get_frame()
            if frame_surface is not None:
                self.last_frame = frame_surface
                self._analyze_frame_for_color(frame_surface)

    def _analyze_frame_for_color(self, frame_surface: pygame.Surface) -> None:
        """Analyze camera frame for target color."""
        try:
            # Convert pygame surface to OpenCV format
            w, h = frame_surface.get_size()
            frame_array = pygame.surfarray.array3d(frame_surface)
            # Transpose because pygame and opencv have different axis conventions
            frame_array = np.transpose(frame_array, (1, 0, 2))
            # Convert RGB to BGR for OpenCV
            frame_bgr = cv2.cvtColor(frame_array, cv2.COLOR_RGB2BGR)

            # Convert to HSV for better color detection
            frame_hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)

            # Check each valid color and find the one with highest percentage
            best_percentage = 0.0
            best_color = ""

            for color in self.valid_colors:
                color_ranges = COLOR_HSV_RANGES.get(color, [])
                if not color_ranges:
                    continue

                # Create mask for this color
                mask = None
                for lower, upper in color_ranges:
                    range_mask = cv2.inRange(frame_hsv, np.array(lower), np.array(upper))
                    if mask is None:
                        mask = range_mask
                    else:
                        mask = cv2.bitwise_or(mask, range_mask)

                if mask is not None:
                    # Calculate percentage of frame that matches this color
                    total_pixels = mask.shape[0] * mask.shape[1]
                    color_pixels = cv2.countNonZero(mask)
                    percentage = color_pixels / total_pixels

                    if percentage > best_percentage:
                        best_percentage = percentage
                        best_color = color

            self.detection_percentage = best_percentage

            # Check if we've detected enough of any valid color
            if self.detection_percentage >= COLOR_DETECTION_SUCCESS_THRESHOLD:
                self.detected_color = best_color
                self._handle_success()

        except Exception as e:
            logger.warning(f"Error analyzing camera frame: {e}")

    def _handle_success(self) -> None:
        """Handle successful color detection."""
        self.success = True
        self.challenge_completed = True
        self.showing_feedback = True
        self.feedback_start_time = time.time()
        logger.info(
            f"Color detection SUCCESS! Found {self.detection_percentage:.1%} of {self.detected_color} (weakness exploitation)"
        )

    def _handle_failure(self, reason: str) -> None:
        """Handle color detection failure."""
        self.success = False
        self.challenge_completed = True
        self.showing_feedback = True
        self.feedback_start_time = time.time()
        logger.info(f"Color detection FAILED! {reason}")

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle pygame events."""
        # This mini-game doesn't require specific key presses, just camera detection
        return False

    def render_instructions(self) -> None:
        """Render the color detection instructions."""
        screen_center_x = self.screen.get_width() // 2

        # Get fonts
        font_large = pygame.font.Font(None, 48)
        font_medium = pygame.font.Font(None, 36)

        # Main instruction with Pokemon name and weaknesses
        weakness_names = [wt.value for wt in self.weakness_types]
        weakness_text = ", ".join(weakness_names[:-1]) + (
            " and " + weakness_names[-1]
            if len(weakness_names) > 1
            else weakness_names[0]
            if weakness_names
            else ""
        )

        # First line: Pokemon weakness info
        pokemon_text = f"{self.pokemon_species.title()} is weak to {weakness_text}!"
        pokemon_surface = font_medium.render(pokemon_text, True, (255, 255, 255))
        pokemon_rect = pokemon_surface.get_rect(center=(screen_center_x, 60))
        self.screen.blit(pokemon_surface, pokemon_rect)

        # Second line: Point camera instruction with colored text
        instruction_start = "Point the camera at something "
        y_pos = 100

        # First, calculate total width of the entire instruction line
        total_width = 0

        # Width of instruction start
        instruction_surface = font_large.render(instruction_start, True, (255, 255, 255))
        total_width += instruction_surface.get_width()

        # Width of colored text and separators
        for i, color in enumerate(self.valid_colors):
            color_name = color.replace("_", " ")  # Convert "bright_green" to "bright green"

            # Add separator width (except for first color)
            if i > 0:
                if i == len(self.valid_colors) - 1:  # Last color
                    separator = " or "
                else:
                    separator = ", "
                sep_surface = font_large.render(separator, True, (255, 255, 255))
                total_width += sep_surface.get_width()

            # Add color name width
            color_surface = font_large.render(color_name, True, COLOR_RGB[color])
            total_width += color_surface.get_width()

        # Width of exclamation mark
        exclaim_surface = font_large.render("!", True, (255, 255, 255))
        total_width += exclaim_surface.get_width()

        # Now center the entire line
        start_x = screen_center_x - (total_width // 2)
        current_x = start_x

        # Draw the instruction start
        self.screen.blit(instruction_surface, (current_x, y_pos))
        current_x += instruction_surface.get_width()

        # Draw each color name in its corresponding color
        for i, color in enumerate(self.valid_colors):
            color_name = color.replace("_", " ")  # Convert "bright_green" to "bright green"
            color_rgb = COLOR_RGB[color]

            # Add comma and space before color (except first)
            if i > 0:
                if i == len(self.valid_colors) - 1:  # Last color
                    separator = " or "
                else:
                    separator = ", "
                sep_surface = font_large.render(separator, True, (255, 255, 255))
                self.screen.blit(sep_surface, (current_x, y_pos))
                current_x += sep_surface.get_width()

            # Draw colored text
            color_surface = font_large.render(color_name, True, color_rgb)
            self.screen.blit(color_surface, (current_x, y_pos))
            current_x += color_surface.get_width()

        # Add exclamation mark
        self.screen.blit(exclaim_surface, (current_x, y_pos))

    def render(self) -> None:
        """Render the color detection mini-game."""
        # Draw camera feed as background if available
        if self.last_frame is not None:
            # Scale camera frame to fit screen
            screen_rect = self.screen.get_rect()
            frame_w, frame_h = self.last_frame.get_size()
            scale = max(screen_rect.width / frame_w, screen_rect.height / frame_h)
            new_size = (max(1, int(frame_w * scale)), max(1, int(frame_h * scale)))
            scaled_frame = pygame.transform.smoothscale(self.last_frame, new_size)

            # Center the frame on screen
            frame_rect = scaled_frame.get_rect(center=screen_rect.center)
            self.screen.blit(scaled_frame, frame_rect)
        else:
            # Fallback: black background
            self.screen.fill((0, 0, 0))

        # Handle preparation phase rendering
        if self.preparation_active:
            # Semi-transparent overlay for UI elements
            overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 150))  # Darker overlay during preparation
            self.screen.blit(overlay, (0, 0))

            self.render_instructions()
            self.render_preparation_overlay()
            return

        # Semi-transparent overlay for UI elements
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 100))  # Dark transparent overlay
        self.screen.blit(overlay, (0, 0))

        # Get screen center for positioning
        screen_center_x = self.screen.get_width() // 2
        screen_center_y = self.screen.get_height() // 2

        # Draw main instruction text
        font_large = pygame.font.Font(None, 48)
        font_medium = pygame.font.Font(None, 36)
        font_small = pygame.font.Font(None, 28)

        if not self.challenge_completed:
            # Timer
            time_text = f"Time: {self.time_remaining:.1f}s"
            time_surface = font_medium.render(time_text, True, (255, 255, 255))
            time_rect = time_surface.get_rect(center=(screen_center_x, 150))
            self.screen.blit(time_surface, time_rect)

            # Detection progress
            if self.detection_percentage > 0:
                progress_text = f"Color detected: {self.detection_percentage:.1%}"
                progress_color = (
                    (0, 255, 0)
                    if self.detection_percentage >= COLOR_DETECTION_SUCCESS_THRESHOLD
                    else (255, 255, 0)
                )
                progress_surface = font_small.render(progress_text, True, progress_color)
                progress_rect = progress_surface.get_rect(center=(screen_center_x, 190))
                self.screen.blit(progress_surface, progress_rect)

            # Progress bar
            bar_width = 300
            bar_height = 20
            bar_x = screen_center_x - bar_width // 2
            bar_y = 210

            # Background bar
            pygame.draw.rect(self.screen, (100, 100, 100), (bar_x, bar_y, bar_width, bar_height))

            # Progress fill
            fill_width = int(
                bar_width * min(1.0, self.detection_percentage / COLOR_DETECTION_SUCCESS_THRESHOLD)
            )
            if fill_width > 0:
                fill_color = (
                    (0, 255, 0)
                    if self.detection_percentage >= COLOR_DETECTION_SUCCESS_THRESHOLD
                    else (255, 255, 0)
                )
                pygame.draw.rect(self.screen, fill_color, (bar_x, bar_y, fill_width, bar_height))

            # Threshold marker
            threshold_x = bar_x + int(bar_width * 1.0)  # At 100% of threshold
            pygame.draw.line(
                self.screen,
                (255, 255, 255),
                (threshold_x, bar_y),
                (threshold_x, bar_y + bar_height),
                2,
            )

        else:
            # Show result
            if self.success:
                color_name = (
                    self.detected_color.replace("_", " ") if self.detected_color else "target color"
                )
                result_text = f"Perfect! {color_name.title()} detected!"
                result_color = (0, 255, 0)
            else:
                weakness_names = [wt.value for wt in self.weakness_types]
                weakness_text = ", ".join(weakness_names[:-1]) + (
                    " and " + weakness_names[-1]
                    if len(weakness_names) > 1
                    else weakness_names[0]
                    if weakness_names
                    else ""
                )
                result_text = f"Failed to exploit {weakness_text} weakness!"
                result_color = (255, 0, 0)

            result_surface = font_large.render(result_text, True, result_color)
            result_rect = result_surface.get_rect(center=(screen_center_x, screen_center_y))
            self.screen.blit(result_surface, result_rect)

        # Camera unavailable message
        if not self.camera_initialized:
            error_text = "Camera not available!"
            error_surface = font_large.render(error_text, True, (255, 0, 0))
            error_rect = error_surface.get_rect(center=(screen_center_x, screen_center_y))
            self.screen.blit(error_surface, error_rect)

    def cleanup(self) -> None:
        """Clean up camera resources."""
        if self.camera is not None:
            self.camera.cleanup()
            self.camera = None
        self.camera_initialized = False
