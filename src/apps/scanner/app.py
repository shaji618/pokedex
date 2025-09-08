from __future__ import annotations

import contextlib
import os
from collections.abc import Callable
from typing import Any

import pygame
from PIL import Image

from src.utils.camera_util import open_camera_capture
from src.utils.focus_integration import FocusIntegrationMixin
from src.utils.focus_manager import FocusableElement, NavigationAction, NavigationResult
from src.utils.logger import get_logger
from src.utils.model_util import load_vit_model, safe_forward_logits, warmup_model
from src.utils.path_util import project_root
from src.utils.play_button_util import is_any_audio_playing
from src.utils.pokemon_card import PokemonCard, _map_key_to_dirname
from src.utils.ui_constants import DARKER_BG, LIGHT_TEXT
from src.utils.ui_util import LoadingCanceledError, run_with_loading


APP_DATA = {
    "name": "Pokémon Scanner",
    "menu_icon_bg_color": (250, 35, 35),
}


def _load_model(local_model_directory: str) -> tuple[Any, Any, str]:
    return load_vit_model(local_model_directory)


def _classify_image(model: Any, processor: Any, device: str, image_path: str) -> str | None:
    if not os.path.exists(image_path):
        return None
    image = Image.open(image_path).convert("RGB")
    inputs = processor(images=image, return_tensors="pt")
    inputs = {k: v.to(device) for k, v in inputs.items()}
    logits = safe_forward_logits(model, inputs, device)
    predicted_id = int(logits.argmax(-1).item())
    return str(model.config.id2label.get(predicted_id) or "")


def _map_prediction_to_dirname(prediction: str) -> str | None:
    key = prediction.strip().lower().replace(" ", "-")
    return _map_key_to_dirname(key)


def _show_pokemon_card(screen: pygame.Surface, species_dirname: str) -> NavigationAction:
    card_app = PokemonCard(screen, species_dirname)
    return card_app.run_modal()


def _run_with_loading(screen: pygame.Surface, status_text: str, fn: Callable[[], Any]) -> Any:
    root_path = str(project_root())
    gif_path = os.path.join(root_path, "src", "utils", "media", "loading.gif")
    return run_with_loading(
        screen,
        status_text,
        fn,
        gif_path=gif_path,
        background_color=(255, 255, 255),
        text_color=(30, 30, 34),
        gif_max_size=(220, 220),
        sfx_path=os.path.join(root_path, "src", "utils", "media", "wobble.mp3"),
    )


def _load_model_with_warmup(local_model_directory: str) -> tuple[Any, Any, str]:
    model, processor, device = _load_model(local_model_directory)
    with contextlib.suppress(Exception):
        warmup_model(model, device)
    return model, processor, device


def _ensure_model(
    screen: pygame.Surface, bundle: tuple[Any, Any, str] | None, model_directory: str
) -> tuple[Any, Any, str]:
    if bundle is not None:
        return bundle
    return _run_with_loading(
        screen,
        "Loading…",
        lambda: _load_model_with_warmup(model_directory),
    )


def _classify_with_overlay(
    screen: pygame.Surface, model_bundle: tuple[Any, Any, str], image_path: str
) -> str | None:
    model, processor, device = model_bundle
    return _run_with_loading(
        screen,
        "Detecting Pokémon: reading photo…",
        lambda: _classify_image(model, processor, device, image_path),
    )


class ScannerApp(FocusIntegrationMixin):
    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen
        self.model_bundle: tuple[object, object, str] | None = None
        self.local_model_directory = os.path.join(str(project_root()), "pokemon_classifier")

    def get_focusable_elements(self) -> list[list[FocusableElement]]:
        return [[]]

    def handle_navigation_result(self, _result: NavigationResult) -> bool:
        return False

    def draw_focus_indicator(self, screen: pygame.Surface) -> None:
        if is_any_audio_playing():
            return
        super().draw_focus_indicator(screen)

    def run(self) -> None:
        title_font = pygame.font.Font(None, 64)
        try:
            self.model_bundle = _run_with_loading(
                self.screen,
                "Loading…",
                lambda: _load_model_with_warmup(self.local_model_directory),
            )
        except LoadingCanceledError:
            return
        except Exception as e:
            import traceback

            error_details = f"Model load failed: {e}\n{traceback.format_exc()}"
            logger = get_logger()
            logger.error(f"Model load error: {error_details}")
            status_message = f"Model load failed: {e}"
            _draw_error_screen(self.screen, title_font, status_message)
            _draw_error_instructions(self.screen)
            pygame.display.flip()
            _wait_for_key_press()
            return
        running = True
        while running:
            try:
                photo_path = open_camera_capture(self.screen, preview_label="Preview")
                if photo_path:
                    prediction = _classify_with_overlay(self.screen, self.model_bundle, photo_path)
                    species_directory = (
                        _map_prediction_to_dirname(prediction) if prediction else None
                    )
                    if species_directory:
                        card_result = _show_pokemon_card(self.screen, species_directory)
                        if card_result == NavigationAction.EXIT_TO_LAUNCHER:
                            running = False
                        elif card_result == NavigationAction.EXIT_TO_PARENT:
                            continue
                    else:
                        error_message = (
                            f"Unknown species: {prediction}" if prediction else "No prediction"
                        )
                        _show_error_and_continue(self.screen, error_message)
                else:
                    running = False
            except LoadingCanceledError:
                running = False
            except Exception as e:
                import traceback

                error_details = f"Camera error: {e}\n{traceback.format_exc()}"
                logger = get_logger()
                logger.error(f"Scanner error: {error_details}")
                if not _show_error_and_ask_retry(self.screen, title_font, f"Error: {e}"):
                    running = False
        # Cleanup handled by card instance
        pass


def run_on_existing_display(screen: pygame.Surface) -> None:
    app = ScannerApp(screen)
    app.run()


def _draw_error_screen(
    screen: pygame.Surface,
    title_font: pygame.font.Font,
    error_msg: str,
) -> None:
    screen.fill(DARKER_BG)
    title = title_font.render("Pokémon Scanner", True, LIGHT_TEXT)
    screen.blit(title, title.get_rect(midtop=(screen.get_width() // 2, 40)))
    error_font = pygame.font.Font(None, 28)
    words = error_msg.split(" ")
    lines = []
    current_line = ""
    max_width = screen.get_width() - 100
    for word in words:
        test_line = current_line + (" " if current_line else "") + word
        if error_font.size(test_line)[0] <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)
    start_y = screen.get_height() // 2 - (len(lines) * 30) // 2
    for i, line in enumerate(lines):
        error = error_font.render(line, True, (220, 100, 100))
        screen.blit(error, error.get_rect(center=(screen.get_width() // 2, start_y + i * 30)))


def _draw_error_instructions(screen: pygame.Surface) -> None:
    instruction_font = pygame.font.Font(None, 24)
    instruction = instruction_font.render(
        "Press any key to return to main menu", True, (180, 180, 190)
    )
    screen.blit(
        instruction,
        instruction.get_rect(center=(screen.get_width() // 2, screen.get_height() - 50)),
    )


def _wait_for_key_press() -> None:
    waiting = True
    while waiting:
        for event in pygame.event.get():
            if event.type == pygame.QUIT or event.type == pygame.KEYDOWN:
                waiting = False


def _show_error_and_continue(screen: pygame.Surface, error_msg: str) -> None:
    screen.fill((30, 30, 30))
    font = pygame.font.Font(None, 36)
    error = font.render(error_msg, True, (255, 100, 100))
    screen.blit(error, error.get_rect(center=screen.get_rect().center))
    hint_font = pygame.font.Font(None, 24)
    hint = hint_font.render("Press any key to continue", True, (200, 200, 200))
    screen.blit(hint, hint.get_rect(center=(screen.get_width() // 2, screen.get_height() - 50)))
    pygame.display.flip()
    _wait_for_key_press()


def _show_error_and_ask_retry(
    screen: pygame.Surface, title_font: pygame.font.Font, error_msg: str
) -> bool:
    screen.fill((30, 30, 30))
    title = title_font.render("Pokémon Scanner", True, (255, 255, 255))
    screen.blit(title, title.get_rect(midtop=(screen.get_width() // 2, 40)))
    error_font = pygame.font.Font(None, 28)
    error = error_font.render(error_msg, True, (255, 100, 100))
    screen.blit(
        error, error.get_rect(center=(screen.get_width() // 2, screen.get_height() // 2 - 50))
    )
    instruction_font = pygame.font.Font(None, 24)
    instructions = ["ENTER: Try again", "ESC: Return to menu"]
    y_offset = screen.get_height() // 2 + 50
    for i, instruction in enumerate(instructions):
        text = instruction_font.render(instruction, True, (200, 200, 200))
        text_rect = text.get_rect(center=(screen.get_width() // 2, y_offset + i * 30))
        screen.blit(text, text_rect)
    pygame.display.flip()
    waiting = True
    while waiting:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN:
                    return True
                elif event.key == pygame.K_ESCAPE:
                    return False
    return False


def _show_pokemon_card(screen: pygame.Surface, species_directory: str) -> NavigationAction:
    card_app = PokemonCard(screen, species_directory)
    return card_app.run_modal()


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
