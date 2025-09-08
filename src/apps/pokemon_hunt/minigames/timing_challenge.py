"""Timing challenge mini-game for Pokemon Hunt."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import pygame

from .base_minigame import MiniGame, MiniGameResult

if TYPE_CHECKING:
    pass


logger = logging.getLogger(__name__)

# Timing challenge constants
TIMING_CHALLENGE_SPEED_MULTIPLIER = 2.0  # How much Pokemon speed affects circle shrinking speed
TIMING_CHALLENGE_PREPARATION_DELAY = (
    1.0  # seconds to show instruction before circles start shrinking
)
TIMING_CHALLENGE_FEEDBACK_DURATION = (
    1.5  # seconds to show success/failure message before proceeding
)
TIMING_CIRCLE_MAX_RADIUS = 250  # starting radius of shrinking circle (larger = more challenging)
TIMING_CIRCLE_TARGET_RADIUS = 100  # target radius (outer edge of thick white border)
TIMING_CIRCLE_RING_THICKNESS = 10  # thickness of thick white target border
TIMING_POKEBALL_RADIUS = 45  # pokeball radius at center (too late if shrinking ring hits this)


class TimingChallenge(MiniGame):
    """Timing-based mini-game where player must time button press to catch Pokemon."""

    def __init__(
        self,
        screen: pygame.Surface,
        pokemon_species: str,
        pokemon_speed: int,
        pokeball_sprite: pygame.Surface,
    ) -> None:
        """Initialize the timing challenge.

        Args:
            screen: The pygame screen surface to render on
            pokemon_species: Name of the Pokemon being caught
            pokemon_speed: Speed stat of the Pokemon (affects difficulty)
            pokeball_sprite: The pokeball sprite to display in center
        """
        super().__init__(screen, pokemon_species, pokemon_speed)
        self.pokeball_sprite = pokeball_sprite

        # Challenge state
        self.start_time = 0.0
        self.challenge_completed = False
        self.feedback_start_time = 0.0
        self.showing_feedback = False

        # Circle animation
        self.circle_radius = 0
        self.circle_max_radius = TIMING_CIRCLE_MAX_RADIUS
        self.circle_target_radius = TIMING_CIRCLE_TARGET_RADIUS
        self.shrink_speed = 1.0  # Pixels per second shrinking

        # Visual feedback
        self.pokeball_inner_ring_color = (255, 255, 255)  # White by default
        self.failure_reason = ""  # Store specific failure reason for user feedback

    def start(self) -> None:
        """Start the timing challenge."""
        self.start_time = time.time()
        self.challenge_completed = False
        self.showing_feedback = False
        self.circle_radius = self.circle_max_radius
        self.pokeball_inner_ring_color = (255, 255, 255)  # Reset to white
        self.failure_reason = ""  # Reset failure reason
        self.result = MiniGameResult.IN_PROGRESS

        # Start preparation phase
        self.start_preparation()

        # Calculate shrinking speed based on Pokemon speed (faster Pokemon = harder timing)
        base_shrink_speed = 60  # Base pixels per second
        speed_bonus = self.pokemon_speed * TIMING_CHALLENGE_SPEED_MULTIPLIER
        self.shrink_speed = base_shrink_speed + speed_bonus

        logger.info(
            f"Timing challenge started for {self.pokemon_species} (speed: {self.pokemon_speed}, shrink_speed: {self.shrink_speed:.1f})"
        )

    def update(self, dt: float) -> None:
        """Update the timing challenge state."""
        if self.result != MiniGameResult.IN_PROGRESS:
            return

        # Handle preparation phase
        if self.preparation_active:
            if self.update_preparation(dt):
                # Preparation complete, start actual challenge
                logger.debug("Timing challenge preparation complete - circles start shrinking!")
            return

        # Handle feedback display period
        if self.showing_feedback:
            if time.time() - self.feedback_start_time >= TIMING_CHALLENGE_FEEDBACK_DURATION:
                # Feedback complete, set final result
                if self.pokeball_inner_ring_color == (0, 255, 0):  # Green = success
                    self.result = MiniGameResult.SUCCESS
                else:  # Red = failure
                    self.result = MiniGameResult.FAILURE
            return

        if self.challenge_completed:
            return

        # Shrink the circle
        self.circle_radius -= self.shrink_speed * dt

        # Check if circle has shrunk too small (hits the pokeball - "too late")
        if self.circle_radius <= TIMING_POKEBALL_RADIUS:
            self.failure_reason = "too late"
            logger.debug(
                f"Timing challenge failed - too late! Circle hit pokeball at radius: {self.circle_radius:.1f}"
            )
            self._handle_failure()

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle pygame events, particularly ENTER key presses."""
        if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
            if self.result == MiniGameResult.IN_PROGRESS and not self.showing_feedback:
                self._handle_button_press()
                return True
        return False

    def _handle_button_press(self) -> None:
        """Handle ENTER key press during timing challenge."""
        if self.challenge_completed or self.showing_feedback:
            return

        # Don't allow button presses during preparation phase
        if self.preparation_active:
            return

        # Check if timing is good (shrinking circle is within the thick white border zone)
        in_target_zone = TIMING_POKEBALL_RADIUS < self.circle_radius <= TIMING_CIRCLE_TARGET_RADIUS

        if in_target_zone:
            # Success!
            self.pokeball_inner_ring_color = (0, 255, 0)  # Green
            self.challenge_completed = True
            self.showing_feedback = True
            self.feedback_start_time = time.time()
            logger.info(
                f"Timing challenge SUCCESS! Circle radius: {self.circle_radius:.1f} (target zone: {TIMING_POKEBALL_RADIUS}-{TIMING_CIRCLE_TARGET_RADIUS})"
            )
        else:
            # Failure - determine if too early or too late
            if self.circle_radius > TIMING_CIRCLE_TARGET_RADIUS:
                self.failure_reason = "too early"
            elif self.circle_radius <= TIMING_POKEBALL_RADIUS:
                self.failure_reason = "too late"
            else:
                self.failure_reason = "missed target zone"
            logger.info(
                f"Timing challenge FAILED ({self.failure_reason})! Circle radius: {self.circle_radius:.1f}"
            )
            self._handle_failure()

    def _handle_failure(self) -> None:
        """Handle timing challenge failure."""
        self.pokeball_inner_ring_color = (255, 0, 0)  # Red
        self.challenge_completed = True
        self.showing_feedback = True
        self.feedback_start_time = time.time()
        logger.info(f"Timing challenge FAILED! Pokemon {self.pokemon_species} escaped!")

    def render_instructions(self) -> None:
        """Render the timing challenge instructions."""
        screen_center_x = self.screen.get_width() // 2
        screen_center_y = self.screen.get_height() // 2

        # Draw instruction text
        font = pygame.font.Font(None, 48)
        text = font.render(
            "Get ready! Hit the white border around the pokeball!", True, (255, 255, 100)
        )
        text_rect = text.get_rect(center=(screen_center_x, screen_center_y - 150))
        self.screen.blit(text, text_rect)

    def render(self) -> None:
        """Render the timing challenge elements."""
        # Center everything on screen
        screen_center_x = self.screen.get_width() // 2
        screen_center_y = self.screen.get_height() // 2
        center_pos = (screen_center_x, screen_center_y)

        # Draw thick target area as a filled circle (white/green/red) - this is the always-visible success zone
        pygame.draw.circle(
            self.screen,
            self.pokeball_inner_ring_color,
            center_pos,
            self.circle_target_radius,
        )

        # Cut out the inner pokeball area to make a clean donut shape
        # Use black as the cutout color for simplicity
        pygame.draw.circle(self.screen, (0, 0, 0), center_pos, TIMING_POKEBALL_RADIUS)

        # Draw pokeball at center (scaled up to be more prominent)
        pokeball_scale_factor = 2.5  # Make pokeball bigger
        pokeball_w, pokeball_h = self.pokeball_sprite.get_size()
        scaled_w = int(pokeball_w * pokeball_scale_factor)
        scaled_h = int(pokeball_h * pokeball_scale_factor)
        scaled_pokeball = pygame.transform.scale(self.pokeball_sprite, (scaled_w, scaled_h))

        pokeball_x = screen_center_x - (scaled_w // 2)
        pokeball_y = screen_center_y - (scaled_h // 2)
        self.screen.blit(scaled_pokeball, (pokeball_x, pokeball_y))

        # Handle preparation phase rendering
        if self.preparation_active:
            self.render_instructions()
            self.render_preparation_overlay()
            return

        # Draw shrinking ring LAST (highest z-index) so it's visible on top of everything
        if not self.challenge_completed and self.circle_radius > 0:
            shrinking_color = (255, 255, 0)  # Yellow shrinking ring
            pygame.draw.circle(
                self.screen,
                shrinking_color,
                center_pos,
                int(self.circle_radius),
                TIMING_CIRCLE_RING_THICKNESS,
            )

        # Draw instruction text based on current phase
        font = pygame.font.Font(None, 48)
        if not self.challenge_completed:
            # During active challenge - show active instruction
            text = font.render(
                "Press ENTER when yellow ring hits white border!", True, (255, 255, 255)
            )
        else:
            if self.pokeball_inner_ring_color == (0, 255, 0):  # Green
                text = font.render("Perfect timing! Pokemon caught!", True, (0, 255, 0))
            else:  # Red - show specific failure reason
                if self.failure_reason == "too early":
                    text = font.render("Too early! Pokemon escaped!", True, (255, 0, 0))
                elif self.failure_reason == "too late":
                    text = font.render("Too late! Pokemon escaped!", True, (255, 0, 0))
                else:
                    text = font.render("Missed target! Pokemon escaped!", True, (255, 0, 0))

        text_rect = text.get_rect(center=(screen_center_x, screen_center_y - 150))
        self.screen.blit(text, text_rect)
