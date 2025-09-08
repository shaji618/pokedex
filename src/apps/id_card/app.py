import threading
from dataclasses import dataclass
from datetime import date, datetime

import pygame

from src.apps.id_card.voice_selector import (
    _format_voice_label,
    _get_voice_play_button,
    draw_voice_selector,
    handle_voice_selector_click,
    stop_voice_sample,
)
from src.utils.focus_integration import FocusIntegrationMixin
from src.utils.focus_manager import FocusableElement, NavigationAction, NavigationResult
from src.utils.focus_renderer import FocusRenderer
from src.utils.image_util import load_image_from_resources
from src.utils.logger import get_logger
from src.utils.play_button_util import is_any_audio_playing
from src.utils.pokemon_card import _canonical_key, _load_sprite_for_key
from src.utils.surface_util import scale_surface_to_fit
from src.utils.tts_util import (
    get_selected_voice,
    is_speaking,
    list_available_voices,
    set_selected_voice,
)
from src.utils.ui_constants import BLUE_BORDER, CARD_BG, DARK_BG, DARK_TEXT
from src.utils.user_config import BIRTHDAY, FAVORITE_POKEMON, NAME


APP_DATA = {
    "name": "ID Card",
    "menu_icon_bg_color": (255, 255, 255),
}


def _preload_adjacent_voices(voices: list[str], current_index: int) -> None:
    def _background_preload() -> None:
        try:
            for offset in [-1, 1]:
                adjacent_index = (current_index + offset) % len(voices)
                adjacent_voice = voices[adjacent_index]
                set_selected_voice(adjacent_voice)
            set_selected_voice(voices[current_index])
        except Exception:
            pass

    thread = threading.Thread(target=_background_preload, daemon=True)
    thread.start()


def _parse_birthday(birthday_string: str) -> date | None:
    if not birthday_string:
        return None
    try:
        return date.fromisoformat(birthday_string)
    except ValueError:
        pass
    for format in ("%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(birthday_string, format).date()
        except ValueError:
            continue
    return None


def _calculate_age(birthday: date) -> int:
    today = date.today()
    years = today.year - birthday.year
    if (today.month, today.day) < (birthday.month, birthday.day):
        years -= 1
    return max(0, years)


def _load_headshot_raw() -> pygame.Surface:
    image = load_image_from_resources("src.apps.id_card", "headshot.png")
    if image is None:
        raise FileNotFoundError("Could not load headshot.jpg")
    return image


def _load_header_raw() -> pygame.Surface:
    image = load_image_from_resources("src.apps.id_card", "header.png")
    if image is None:
        raise FileNotFoundError("Could not load header.png")
    return image


@dataclass
class BioCell:
    label: str
    value: str

    def draw(
        self,
        screen: pygame.Surface,
        rect: pygame.Rect,
        label_font: pygame.font.Font,
        value_font: pygame.font.Font,
        text_color: tuple[int, int, int],
        inner_margin: int,
        gap: int,
        rule_thickness: int,
        rule_color: tuple[int, int, int] = (40, 90, 180),
    ) -> None:
        available_width = rect.width - 2 * inner_margin
        max_height = label_font.get_height()
        base_size = label_font.get_height()
        size = base_size
        min_size = 10
        fitted_font = None
        while size >= min_size:
            font = pygame.font.Font(None, size)
            test_surface = font.render(self.label, True, text_color)
            if (
                test_surface.get_width() <= available_width
                and test_surface.get_height() <= max_height
            ):
                fitted_font = font
                break
            size -= 1
        if fitted_font is None:
            fitted_font = pygame.font.Font(None, min_size)
        label_surface = fitted_font.render(self.label, True, text_color)
        label_x = rect.left + inner_margin
        label_y = rect.top + inner_margin
        screen.blit(label_surface, (label_x, label_y))
        value_surface = value_font.render(self.value, True, (10, 10, 20))
        value_x = rect.left + inner_margin
        value_y = label_y + label_font.get_height() + gap
        screen.blit(value_surface, (value_x, value_y))
        rule_left = rect.left + inner_margin
        rule_right = rect.right - inner_margin
        rule_y = value_y + value_font.get_height() + gap
        pygame.draw.line(
            screen, rule_color, (rule_left, rule_y), (rule_right, rule_y), width=rule_thickness
        )


@dataclass
class PokemonCell(BioCell):
    sprite: pygame.Surface | None = None

    def draw(
        self,
        screen: pygame.Surface,
        rect: pygame.Rect,
        label_font: pygame.font.Font,
        value_font: pygame.font.Font,
        text_color: tuple[int, int, int],
        inner_margin: int,
        gap: int,
        rule_thickness: int,
        rule_color: tuple[int, int, int] = (40, 90, 180),
    ) -> None:
        available_width = rect.width - 2 * inner_margin
        max_height = label_font.get_height()
        base_size = label_font.get_height()
        size = base_size
        min_size = 10
        fitted_font = None
        while size >= min_size:
            font = pygame.font.Font(None, size)
            test_surface = font.render(self.label, True, text_color)
            if (
                test_surface.get_width() <= available_width
                and test_surface.get_height() <= max_height
            ):
                fitted_font = font
                break
            size -= 1
        if fitted_font is None:
            fitted_font = pygame.font.Font(None, min_size)

        label_surface = fitted_font.render(self.label, True, text_color)
        label_x = rect.left + inner_margin
        label_y = rect.top + inner_margin
        screen.blit(label_surface, (label_x, label_y))

        value_y = label_y + label_font.get_height() + gap

        value_surface = value_font.render(self.value, True, (10, 10, 20))
        value_x = rect.left + inner_margin
        screen.blit(value_surface, (value_x, value_y))

        if self.sprite:
            text_height = value_font.get_height()
            sprite_height = int(text_height * 1.5)
            sprite_size = (sprite_height, sprite_height)

            scaled_sprite = scale_surface_to_fit(self.sprite, sprite_size)

            sprite_gap = 8
            sprite_rect = scaled_sprite.get_rect()
            sprite_rect.left = value_x + value_surface.get_width() + sprite_gap - 17
            sprite_rect.centery = value_y + text_height // 2
            sprite_rect.y -= 18
            screen.blit(scaled_sprite, sprite_rect)

        rule_left = rect.left + inner_margin
        rule_right = rect.right - inner_margin
        rule_y = value_y + value_font.get_height() + gap
        pygame.draw.line(
            screen, rule_color, (rule_left, rule_y), (rule_right, rule_y), width=rule_thickness
        )


def create_name(name: str) -> BioCell:
    return BioCell("NAME", name)


def create_age(birthday_str: str) -> BioCell:
    parsed = _parse_birthday(birthday_str)
    age_value = str(_calculate_age(parsed)) if parsed else "-"
    return BioCell("AGE", age_value)


def create_favorite_pokemon(pokemon: str) -> PokemonCell:
    key = _canonical_key(pokemon)
    sprite = _load_sprite_for_key(key, max_inner=(100, 100))
    return PokemonCell("FAVORITE POKÉMON", pokemon, sprite=sprite)


def _compute_cell_metrics(
    cell_width: int,
    area_height: int,
    label_font: pygame.font.Font,
    value_font: pygame.font.Font,
) -> tuple[int, int, int, int]:
    inner_margin = max(8, int(min(cell_width, area_height) * 0.06))
    label_h = label_font.get_height()
    value_h = value_font.get_height()
    gap = max(6, inner_margin // 2)
    rule_thickness = 2
    row_height = inner_margin + label_h + gap + value_h + gap + rule_thickness + inner_margin
    return inner_margin, gap, rule_thickness, row_height


def _render_biodata(
    screen: pygame.Surface,
    items: list[BioCell],
    area: pygame.Rect,
    label_font: pygame.font.Font,
    value_font: pygame.font.Font,
    text_color: tuple[int, int, int],
    *,
    skip_indices: set[int] | None = None,
) -> list[pygame.Rect]:
    columns = 2 if len(items) > 1 else 1
    if columns < 1:
        return []
    cell_width = area.width // columns
    inner_margin, gap, rule_thickness, row_height = _compute_cell_metrics(
        cell_width, area.height, label_font, value_font
    )
    rects: list[pygame.Rect] = []
    for index, cell in enumerate(items):
        row_index = index // columns
        column_index = index % columns
        cell_x = area.left + column_index * cell_width
        cell_y = area.top + row_index * row_height
        cell_rect = pygame.Rect(cell_x, cell_y, cell_width, row_height)
        rects.append(cell_rect)
        if skip_indices and index in skip_indices:
            continue
        cell.draw(
            screen,
            cell_rect,
            label_font,
            value_font,
            text_color,
            inner_margin,
            gap,
            rule_thickness,
        )
    return rects


def draw_id_card(
    screen: pygame.Surface,
    current_voice: str | None = None,
    has_unsaved_changes: bool = False,
    show_save_feedback: bool = False,
    saved_voice: str | None = None,
) -> tuple[pygame.Rect | None, pygame.Rect | None, pygame.Rect | None]:
    screen_width, screen_height = screen.get_size()
    card_width = int(min(1200, screen_width * 0.85))
    card_height = int(min(720, screen_height * 0.7))
    card_rect = pygame.Rect(0, 0, card_width, card_height)
    card_rect.center = (screen_width // 2, screen_height // 2)
    bg_color = DARK_BG
    card_bg = CARD_BG
    card_border = BLUE_BORDER
    text_color = DARK_TEXT
    screen.fill(bg_color)
    pygame.draw.rect(screen, card_bg, card_rect, border_radius=20)
    pygame.draw.rect(screen, card_border, card_rect, width=6, border_radius=20)

    def scaled(size_factor: float, minimum: int, maximum: int) -> int:
        return max(minimum, min(maximum, int(card_height * size_factor)))

    label_font = pygame.font.Font(None, scaled(0.07, 26, 56))
    value_font = pygame.font.Font(None, scaled(0.08, 30, 64))
    if not hasattr(draw_id_card, "_raw_header"):
        draw_id_card._raw_header = _load_header_raw()
        draw_id_card._header_cache_size = None
        draw_id_card._scaled_header = None
    target_header_height = scaled(0.12, 36, 96)
    target_header_width = int(card_width * 0.6)
    if getattr(draw_id_card, "_header_cache_size", None) != (
        target_header_width,
        target_header_height,
    ):
        draw_id_card._scaled_header = scale_surface_to_fit(
            draw_id_card._raw_header, (target_header_width, target_header_height)
        )
        draw_id_card._header_cache_size = (target_header_width, target_header_height)
    header_surf = draw_id_card._scaled_header
    title_rect = header_surf.get_rect(midtop=(card_rect.centerx, card_rect.top + 18))
    screen.blit(header_surf, title_rect)
    padding = max(16, int(card_height * 0.04))
    inner = card_rect.inflate(-padding * 2, -padding * 2)
    content_top = title_rect.bottom + max(12, int(card_height * 0.02))
    content_area = pygame.Rect(inner.left, content_top, inner.width, inner.bottom - content_top)
    max_photo_width = int(content_area.width * 0.32)
    max_photo_h = int(content_area.height * 0.65)
    if not hasattr(draw_id_card, "_raw_headshot"):
        draw_id_card._raw_headshot = _load_headshot_raw()
        draw_id_card._cache_size = None
        draw_id_card._scaled = None
    if getattr(draw_id_card, "_cache_size", None) != (max_photo_width, max_photo_h):
        draw_id_card._scaled = scale_surface_to_fit(
            draw_id_card._raw_headshot, (max_photo_width, max_photo_h)
        )
        draw_id_card._cache_size = (max_photo_width, max_photo_h)
    headshot = draw_id_card._scaled
    padding_around_image = 8
    actual_w, actual_h = headshot.get_size()
    photo_w = actual_w + 2 * padding_around_image
    photo_h = actual_h + 2 * padding_around_image
    photo_rect = pygame.Rect(content_area.left, content_area.top, photo_w, photo_h)
    headshot_rect = headshot.get_rect()
    headshot_rect.center = photo_rect.center
    pygame.draw.rect(screen, (210, 212, 220), photo_rect, border_radius=12)
    screen.blit(headshot, headshot_rect)
    pygame.draw.rect(screen, (190, 192, 200), photo_rect, width=2, border_radius=12)
    information_left = photo_rect.right + padding
    biodata_area = pygame.Rect(
        information_left,
        content_area.top,
        content_area.right - information_left,
        content_area.height,
    )
    if current_voice is None:
        current_voice = get_selected_voice()
    voice_label = _format_voice_label(current_voice)
    if has_unsaved_changes:
        voice_label += " *"
    biodata_items: list[BioCell] = [
        create_name(NAME),
        create_age(BIRTHDAY),
        create_favorite_pokemon(FAVORITE_POKEMON),
        BioCell("TTS VOICE", voice_label),
    ]
    voice_index = 3
    rects = _render_biodata(
        screen,
        biodata_items,
        biodata_area,
        label_font,
        value_font,
        text_color,
        skip_indices={voice_index},
    )
    left_arrow_rect: pygame.Rect | None = None
    right_arrow_rect: pygame.Rect | None = None
    play_button_rect: pygame.Rect | None = None
    if 0 <= voice_index < len(rects):
        is_saved_voice = current_voice == saved_voice
        left_arrow_rect, right_arrow_rect, play_button_rect = draw_voice_selector(
            screen,
            rects[voice_index],
            label_font,
            value_font,
            current_voice,
            biodata_area.height,
            show_save_feedback,
            is_saved_voice,
        )
    return left_arrow_rect, right_arrow_rect, play_button_rect


class IDCardApp(FocusIntegrationMixin):
    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen
        self.clock = pygame.time.Clock()
        self.running = True
        icon_focus_renderer = FocusRenderer(thickness=2, corner_size_factor=0.3, padding=4)
        self.init_focus_system(renderer=icon_focus_renderer)
        self.voices = list_available_voices()
        self.current_index = 0
        self.saved_index = 0
        self.left_rect: pygame.Rect | None = None
        self.right_rect: pygame.Rect | None = None
        self.play_rect: pygame.Rect | None = None
        self.sample_playing_voice: str | None = None
        self._initialize_voice_selection()

    def _initialize_voice_selection(self) -> None:
        if self.voices:
            try:
                saved_voice = get_selected_voice()
                self.saved_index = (
                    self.voices.index(saved_voice) if saved_voice in self.voices else 0
                )
            except Exception:
                self.saved_index = 0
            if get_selected_voice() is None and 0 <= self.saved_index < len(self.voices):
                set_selected_voice(self.voices[self.saved_index])
                self.saved_index = 0
            current_voice = get_selected_voice()
            if current_voice:
                set_selected_voice(current_voice)
            self.current_index = self.saved_index
        else:
            self.saved_index = -1
            self.current_index = -1

    def get_focusable_elements(self) -> list[FocusableElement]:
        if not self.voices or not self.play_rect or not self.left_rect or not self.right_rect:
            return []

        def play_voice_sample() -> None:
            if self.voices and 0 <= self.current_index < len(self.voices):
                preview_voice = self.voices[self.current_index]
                play_button = _get_voice_play_button(preview_voice)
                if play_button.handle_click():
                    self.sample_playing_voice = preview_voice

        def previous_voice() -> None:
            if self.voices:
                stop_voice_sample()
                self.current_index = (self.current_index - 1) % len(self.voices)
                _preload_adjacent_voices(self.voices, self.current_index)

        def next_voice() -> None:
            if self.voices:
                stop_voice_sample()
                self.current_index = (self.current_index + 1) % len(self.voices)
                _preload_adjacent_voices(self.voices, self.current_index)

        play_button = FocusableElement(
            rect=self.play_rect, callback=play_voice_sample, metadata={"name": "play_button"}
        )
        left_arrow = FocusableElement(
            rect=self.left_rect, callback=previous_voice, metadata={"name": "left_arrow"}
        )
        right_arrow = FocusableElement(
            rect=self.right_rect, callback=next_voice, metadata={"name": "right_arrow"}
        )
        self.play_button_element = play_button
        self.left_arrow_element = left_arrow
        self.right_arrow_element = right_arrow
        return [[play_button], [left_arrow, right_arrow]]

    def handle_focus_event(self, event: pygame.event.Event) -> bool:
        if event.type != pygame.KEYDOWN:
            return False
        if not hasattr(self, "play_button_element"):
            return super().handle_focus_event(event)
        focused = self.get_focused_element()
        if not focused:
            return super().handle_focus_event(event)
        if event.key == pygame.K_UP:
            if focused == self.left_arrow_element or focused == self.right_arrow_element:
                self.focus_manager.current_row = 0
                self.focus_manager.current_column = 0
                return True
            elif focused == self.play_button_element:
                self.focus_manager.current_row = 1
                self.focus_manager.current_column = 0
                return True
        elif event.key == pygame.K_DOWN:
            if focused == self.play_button_element:
                self.focus_manager.current_row = 1
                self.focus_manager.current_column = 0
                return True
            elif focused == self.left_arrow_element or focused == self.right_arrow_element:
                self.focus_manager.current_row = 0
                self.focus_manager.current_column = 0
                return True
        elif event.key == pygame.K_LEFT:
            if focused == self.play_button_element:
                self.focus_manager.current_row = 1
                self.focus_manager.current_column = 0
                return True
            elif focused == self.left_arrow_element:
                self.focus_manager.current_row = 0
                self.focus_manager.current_column = 0
                return True
            elif focused == self.right_arrow_element:
                self.focus_manager.current_column = 0
                return True
        elif event.key == pygame.K_RIGHT:
            if focused == self.play_button_element:
                self.focus_manager.current_row = 1
                self.focus_manager.current_column = 0
                return True
            elif focused == self.left_arrow_element:
                self.focus_manager.current_column = 1
                return True
            elif focused == self.right_arrow_element:
                self.focus_manager.current_row = 0
                self.focus_manager.current_column = 0
                return True
        elif event.key == pygame.K_RETURN:
            result = self.focus_manager.activate_current()
            if result:
                return self.handle_navigation_result(result)
        elif event.key == pygame.K_ESCAPE:
            result = NavigationResult(action=NavigationAction.EXIT_TO_LAUNCHER)
            return self.handle_navigation_result(result)
        return False

    def handle_navigation_result(self, result: NavigationResult) -> bool:
        if (
            result.action == NavigationAction.EXIT
            or result.action == NavigationAction.EXIT_TO_LAUNCHER
        ):
            stop_voice_sample()
            self.running = False
            return True
        elif result.action == NavigationAction.ACTIVATE:
            return True
        return False

    def handle_global_keys(self, event: pygame.event.Event) -> bool:
        if event.type != pygame.KEYDOWN:
            return False
        if (
            event.key == pygame.K_SPACE
            and self.voices
            and 0 <= self.current_index < len(self.voices)
        ):
            set_selected_voice(self.voices[self.current_index])
            self.saved_index = self.current_index
            return True
        elif event.key in (pygame.K_q, pygame.K_ESCAPE, pygame.K_BACKSPACE):
            stop_voice_sample()
            self.running = False
            return True
        return False

    def handle_mouse_events(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN:
            mouse_x, mouse_y = event.pos
            new_index, action = handle_voice_selector_click(
                (mouse_x, mouse_y),
                self.left_rect,
                self.right_rect,
                self.play_rect,
                self.voices,
                self.current_index,
            )
            if action in ("prev", "next"):
                self.current_index = new_index
                return True
            elif action == "play":
                if self.voices and 0 <= self.current_index < len(self.voices):
                    self.sample_playing_voice = get_selected_voice()
                return True
            elif action == "disabled":
                return True
            elif action is None:
                stop_voice_sample()
                self.running = False
                return True
        return False

    def run(self) -> None:
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    stop_voice_sample()
                    self.running = False
                elif not self.handle_focus_event(event):
                    if not self.handle_global_keys(event):
                        self.handle_mouse_events(event)
            if self.sample_playing_voice is not None and not is_speaking():
                self.sample_playing_voice = None
            show_save_feedback = False
            current_voice = (
                self.voices[self.current_index]
                if self.voices and 0 <= self.current_index < len(self.voices)
                else None
            )
            has_unsaved_changes = self.current_index != self.saved_index
            try:
                saved_voice = (
                    self.voices[self.saved_index]
                    if self.voices and 0 <= self.saved_index < len(self.voices)
                    else None
                )
                self.left_rect, self.right_rect, self.play_rect = draw_id_card(
                    self.screen, current_voice, has_unsaved_changes, show_save_feedback, saved_voice
                )
            except Exception as e:
                import traceback

                error_details = f"Error in draw_id_card: {e}\n{traceback.format_exc()}"
                logger = get_logger()
                logger.error(error_details)
                self.left_rect = pygame.Rect(50, 100, 20, 20)
                self.right_rect = pygame.Rect(150, 100, 20, 20)
                self.play_rect = pygame.Rect(100, 50, 30, 30)
            self.update_focus_elements()
            if not hasattr(self, "_focus_initialized") and hasattr(self, "play_button_element"):
                self.focus_manager.current_row = 0
                self.focus_manager.current_column = 0
                self._focus_initialized = True
            self.draw_focus_indicator(self.screen)
            pygame.display.flip()
            self.clock.tick(60)

    def draw_focus_indicator(self, screen: pygame.Surface) -> None:
        if is_any_audio_playing():
            return
        super().draw_focus_indicator(screen)


def run_on_existing_display(screen: pygame.Surface) -> None:
    app = IDCardApp(screen)
    app.run()


def run() -> None:
    pygame.init()
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    run_on_existing_display(screen)
    pygame.quit()


if __name__ == "__main__":
    run()
