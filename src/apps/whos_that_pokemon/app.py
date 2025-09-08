import os
import random

import pygame

from src.utils.audio_util import (
    AudioChannel,
    play_music_once,
    play_pokemon_cry,
    stop_music,
    stop_named_channel,
)
from src.utils.focus_integration import FocusIntegrationMixin
from src.utils.focus_manager import FocusableElement, NavigationAction, NavigationResult
from src.utils.focus_renderer import FocusRenderer
from src.utils.image_util import load_image_safe
from src.utils.play_button_util import is_any_audio_playing
from src.utils.pokemon_card import load_card_images
from src.utils.pokemon_image_util import images_root, index_images, make_silhouette
from src.utils.surface_util import scale_surface_to_fit


APP_DATA = {
    "name": "Who's That Pokémon?",
    "menu_icon_bg_color": (255, 203, 5),
}


def _render(
    screen: pygame.Surface,
    background_scaled: pygame.Surface,
    creature_scaled: pygame.Surface,
    phase: int,
    name_scaled: pygame.Surface | None,
) -> None:
    screen_width, screen_height = screen.get_size()
    if phase == 0:
        screen.blit(background_scaled, (0, 0))
        left_margin = max(20, int(screen_width * 0.04))
        top_margin = max(20, int(screen_height * 0.08))
        box_width = int(screen_width * 0.44)
        box_height = int(screen_height * 0.7)
        target_box = pygame.Rect(left_margin, top_margin, box_width, box_height)
        shown = make_silhouette(creature_scaled)
        creature_rect = shown.get_rect(center=target_box.center)
        screen.blit(shown, creature_rect)
    elif phase == 1:
        screen.blit(background_scaled, (0, 0))
        left_margin = max(20, int(screen_width * 0.04))
        top_margin = max(20, int(screen_height * 0.08))
        box_width = int(screen_width * 0.44)
        box_height = int(screen_height * 0.7)
        target_box = pygame.Rect(left_margin, top_margin, box_width, box_height)
        creature_rect = creature_scaled.get_rect(center=target_box.center)
        screen.blit(creature_scaled, creature_rect)
    else:
        screen.fill((0, 0, 0))
        if name_scaled is not None:
            name_rect = name_scaled.get_rect(center=(screen_width // 2, screen_height // 2))
            screen.blit(name_scaled, name_rect)


class WhosThatPokemonApp(FocusIntegrationMixin):
    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen
        self.clock = pygame.time.Clock()
        self.running = True
        invisible_renderer = FocusRenderer(thickness=0, padding=0)
        self.init_focus_system(renderer=invisible_renderer)
        self.phase = 0
        bg_path = os.path.join(os.path.dirname(__file__), "background.png")
        background = load_image_safe(bg_path, convert_alpha=False)
        if background is None:
            raise FileNotFoundError(f"Could not load background: {bg_path}")
        screen_width, screen_height = screen.get_size()
        self.background_scaled = pygame.transform.smoothscale(
            background, (screen_width, screen_height)
        )
        self.pairs = index_images(images_root())
        if not self.pairs:
            raise FileNotFoundError("No creature images found")
        app_directory = os.path.dirname(__file__)
        self.intro_path = os.path.join(app_directory, "whos_that_pokemon.mp3")
        self._load_new_pokemon()
        self._start_intro_music()

    def _load_new_pokemon(self) -> None:
        screen_width, screen_height = self.screen.get_size()
        self.species, creature_path = random.choice(self.pairs)
        creature = load_image_safe(creature_path)
        if creature is None:
            raise FileNotFoundError(f"Could not load creature: {creature_path}")
        left_margin = max(20, int(screen_width * 0.04))
        top_margin = max(20, int(screen_height * 0.08))
        box_width = int(screen_width * 0.44)
        box_height = int(screen_height * 0.7)
        self.target_box = pygame.Rect(left_margin, top_margin, box_width, box_height)
        self.creature_scaled = scale_surface_to_fit(
            creature, (self.target_box.width, self.target_box.height)
        )
        _, name_logo = load_card_images(self.species)
        self.name_scaled = None
        if name_logo is not None:
            name_box_width = int(screen_width * 0.6)
            name_box_height = int(screen_height * 0.25)
            self.name_scaled = scale_surface_to_fit(name_logo, (name_box_width, name_box_height))

    def _start_intro_music(self) -> None:
        play_music_once(self.intro_path, volume=0.6)

    def _advance_game(self) -> None:
        if self.phase == 0:
            self.phase = 1
            play_pokemon_cry(self.species)
        elif self.phase == 1:
            self.phase = 2
        else:
            stop_named_channel(AudioChannel.CRY)
            self._load_new_pokemon()
            self.phase = 0
            self._start_intro_music()

    def get_focusable_elements(self) -> list[FocusableElement]:
        screen_width, screen_height = self.screen.get_size()
        game_rect = pygame.Rect(0, 0, screen_width, screen_height)
        game_element = FocusableElement(
            rect=game_rect, callback=self._advance_game, metadata={"name": "game_area"}
        )
        return [[game_element]]

    def handle_focus_event(self, event: pygame.event.Event) -> bool:
        if event.type != pygame.KEYDOWN:
            return False
        if event.key == pygame.K_RIGHT:
            self._advance_game()
            return True
        elif event.key == pygame.K_RETURN:
            result = self.focus_manager.activate_current()
            if result:
                return self.handle_navigation_result(result)
        elif event.key in (pygame.K_ESCAPE, pygame.K_BACKSPACE):
            result = NavigationResult(action=NavigationAction.EXIT_TO_LAUNCHER)
            return self.handle_navigation_result(result)
        elif event.key in (pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT):
            return True
        return False

    def handle_navigation_result(self, result: NavigationResult) -> bool:
        if (
            result.action == NavigationAction.EXIT
            or result.action == NavigationAction.EXIT_TO_LAUNCHER
        ):
            stop_music()
            stop_named_channel(AudioChannel.CRY)
            self.running = False
            return True
        elif result.action == NavigationAction.ACTIVATE:
            return True
        return False

    def handle_global_keys(self, event: pygame.event.Event) -> bool:
        if event.type != pygame.KEYDOWN:
            return False
        if event.key == pygame.K_SPACE:
            self._advance_game()
            return True
        return False

    def run(self) -> None:
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    stop_music()
                    stop_named_channel(AudioChannel.CRY)
                    self.running = False
                elif not self.handle_focus_event(event):
                    self.handle_global_keys(event)
            self.update_focus_elements()
            self._render()
            pygame.display.flip()
            self.clock.tick(60)

    def _render(self) -> None:
        screen_width, screen_height = self.screen.get_size()
        if self.phase == 0:
            self.screen.blit(self.background_scaled, (0, 0))
            shown = make_silhouette(self.creature_scaled)
            creature_rect = shown.get_rect(center=self.target_box.center)
            self.screen.blit(shown, creature_rect)
        elif self.phase == 1:
            self.screen.blit(self.background_scaled, (0, 0))
            creature_rect = self.creature_scaled.get_rect(center=self.target_box.center)
            self.screen.blit(self.creature_scaled, creature_rect)
        else:
            self.screen.fill((0, 0, 0))
            if self.name_scaled is not None:
                name_rect = self.name_scaled.get_rect(
                    center=(screen_width // 2, screen_height // 2)
                )
                self.screen.blit(self.name_scaled, name_rect)

    def draw_focus_indicator(self, screen: pygame.Surface) -> None:
        if is_any_audio_playing():
            return
        super().draw_focus_indicator(screen)


def run_on_existing_display(screen: pygame.Surface) -> None:
    app = WhosThatPokemonApp(screen)
    app.run()


def run() -> None:
    pygame.init()
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    run_on_existing_display(screen)
    pygame.quit()


def main() -> None:
    import pygame

    pygame.init()
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    try:
        run_on_existing_display(screen)
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
