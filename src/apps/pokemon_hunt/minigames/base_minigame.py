"""Base class for Pokemon Hunt mini-games."""

from __future__ import annotations

import abc
import time
from enum import Enum
from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    pass


class MiniGameResult(Enum):
    """Result of a mini-game."""

    SUCCESS = "success"
    FAILURE = "failure"
    IN_PROGRESS = "in_progress"


class MiniGame(abc.ABC):
    """Base class for all Pokemon Hunt mini-games."""

    # Class variables for preparation timing (same for all mini-games)
    INSTRUCTION_DISPLAY_TIME = 2.0  # seconds for just instructions
    COUNTDOWN_TIME = 3.0  # seconds for countdown phase

    def __init__(self, screen: pygame.Surface, pokemon_species: str, pokemon_speed: int) -> None:
        """Initialize the mini-game.

        Args:
            screen: The pygame screen surface to render on
            pokemon_species: Name of the Pokemon being caught
            pokemon_speed: Speed stat of the Pokemon (affects difficulty)
        """
        self.screen = screen
        self.pokemon_species = pokemon_species
        self.pokemon_speed = pokemon_speed
        self.result = MiniGameResult.IN_PROGRESS

        # Preparation phase state
        self.preparation_active = True
        self.preparation_start_time = 0.0
        self.instruction_phase_complete = False

    @abc.abstractmethod
    def start(self) -> None:
        """Start the mini-game."""
        pass

    @abc.abstractmethod
    def update(self, dt: float) -> None:
        """Update the mini-game state.

        Args:
            dt: Delta time in seconds since last update
        """
        pass

    @abc.abstractmethod
    def render(self) -> None:
        """Render the mini-game to the screen."""
        pass

    @abc.abstractmethod
    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle a pygame event.

        Args:
            event: The pygame event to handle

        Returns:
            True if the event was handled, False otherwise
        """
        pass

    @abc.abstractmethod
    def render_instructions(self) -> None:
        """Render the instruction content for this mini-game.

        This method should draw the game-specific instructions to the screen.
        It will be called during the preparation phase.
        """
        pass

    def is_complete(self) -> bool:
        """Check if the mini-game is complete.

        Returns:
            True if the mini-game has finished (success or failure)
        """
        return self.result != MiniGameResult.IN_PROGRESS

    def get_result(self) -> MiniGameResult:
        """Get the result of the mini-game.

        Returns:
            The current result of the mini-game
        """
        return self.result

    def start_preparation(self) -> None:
        """Start the preparation phase."""
        self.preparation_active = True
        self.preparation_start_time = time.time()
        self.instruction_phase_complete = False

    def update_preparation(self, dt: float) -> bool:
        """Update preparation phase.

        Returns:
            True when preparation is complete and mini-game should start
        """
        if not self.preparation_active:
            return True

        elapsed = time.time() - self.preparation_start_time

        # Check if instruction phase is complete
        if not self.instruction_phase_complete and elapsed >= self.INSTRUCTION_DISPLAY_TIME:
            self.instruction_phase_complete = True

        # Check if entire preparation is complete
        total_preparation_time = self.INSTRUCTION_DISPLAY_TIME + self.COUNTDOWN_TIME
        if elapsed >= total_preparation_time:
            self.preparation_active = False
            return True

        return False

    def render_preparation_overlay(self) -> None:
        """Render the preparation phase overlay (countdown).

        This renders the visual countdown over the instruction content.
        """
        if not self.preparation_active or not self.instruction_phase_complete:
            return

        elapsed = time.time() - self.preparation_start_time
        countdown_elapsed = elapsed - self.INSTRUCTION_DISPLAY_TIME
        countdown_remaining = self.COUNTDOWN_TIME - countdown_elapsed

        if countdown_remaining > 0:
            # Calculate which number to show (3, 2, 1)
            countdown_number = int(countdown_remaining) + 1
            if countdown_number > 0:
                # Render large countdown number
                font = pygame.font.Font(None, 120)
                countdown_text = str(countdown_number)
                countdown_surface = font.render(countdown_text, True, (255, 255, 100))

                # Add shadow for visibility
                shadow_surface = font.render(countdown_text, True, (0, 0, 0))

                screen_center_x = self.screen.get_width() // 2
                screen_center_y = self.screen.get_height() // 2

                # Draw shadow
                shadow_rect = shadow_surface.get_rect(
                    center=(screen_center_x + 3, screen_center_y + 3)
                )
                self.screen.blit(shadow_surface, shadow_rect)

                # Draw countdown number
                countdown_rect = countdown_surface.get_rect(
                    center=(screen_center_x, screen_center_y)
                )
                self.screen.blit(countdown_surface, countdown_rect)
