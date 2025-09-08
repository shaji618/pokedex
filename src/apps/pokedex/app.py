import random

import pygame

from src.apps.pokedex.search import compute_next_letters, draw_letter_strip, filter_names_by_prefix
from src.utils.focus_integration import (
    FocusableElement,
    FocusIntegrationMixin,
    create_grid_elements,
)
from src.utils.focus_manager import NavigationAction, NavigationResult
from src.utils.focus_renderer import FocusRenderer
from src.utils.image_util import load_and_scale_image
from src.utils.play_button_util import is_any_audio_playing
from src.utils.pokemon_card import PokemonCard
from src.utils.pokemon_image_util import images_root, index_images
from src.utils.ui_constants import DARK_BG


APP_DATA = {
    "name": "Pokédex",
    "menu_icon_bg_color": (255, 203, 5),
}


def _load_thumbnail(path: str, box_size: tuple[int, int]) -> pygame.Surface | None:
    box_width, box_height = box_size
    scaled_image = load_and_scale_image(path, (box_width, box_height))
    if scaled_image is None:
        return None
    box = pygame.Surface((box_width, box_height), pygame.SRCALPHA)
    rectangle = scaled_image.get_rect(center=(box_width // 2, box_height // 2))
    box.blit(scaled_image, rectangle)
    return box


_display_name_cache: dict[str, str] = {}


def _get_pokemon_display_name(species_directory: str) -> str:
    if species_directory in _display_name_cache:
        return _display_name_cache[species_directory]
    import json

    metadata_path = images_root() / species_directory / "metadata.json"
    if metadata_path.exists():
        try:
            with open(metadata_path, encoding="utf-8") as file:
                metadata = json.load(file)
                name = metadata.get("name", species_directory.replace("_", " ").title())
                _display_name_cache[species_directory] = name
                return name
        except Exception:
            pass
    fallback_name = species_directory.replace("_", " ").title()
    _display_name_cache[species_directory] = fallback_name
    return fallback_name


def _draw_grid(
    screen: pygame.Surface,
    area: pygame.Rect,
    names: list[str],
    thumbnails: dict[str, pygame.Surface],
    columns: int,
    cell_size: tuple[int, int],
    scroll_rows: int,
) -> list[tuple[str, pygame.Rect]]:
    cell_width, cell_height = cell_size
    gap = 14
    label_font = pygame.font.Font(None, 24)
    start_index = scroll_rows * columns
    rows_visible = max(1, (area.height + gap) // (cell_height + gap))
    end_index = min(len(names), start_index + rows_visible * columns)
    tile_data = []
    for i in range(start_index, end_index):
        index_in_page = i - start_index
        row = index_in_page // columns
        column = index_in_page % columns
        y = area.top + row * (cell_height + gap)
        x = area.left + column * (cell_width + gap)
        name = names[i]
        tile_rect = pygame.Rect(x, y, cell_width, cell_height)
        pygame.draw.rect(screen, (30, 30, 34), tile_rect, border_radius=10)
        pygame.draw.rect(screen, (60, 60, 68), tile_rect, width=1, border_radius=10)
        image = thumbnails.get(name)
        if image:
            image_rect = image.get_rect(center=tile_rect.center)
            screen.blit(image, image_rect)
        label = _get_pokemon_display_name(name)
        label_surface = label_font.render(label, True, (230, 230, 235))
        label_rect = label_surface.get_rect(midbottom=(tile_rect.centerx, tile_rect.bottom - 6))
        screen.blit(label_surface, label_rect)
        tile_data.append((name, tile_rect))
    return tile_data


class PokedexApp(FocusIntegrationMixin):
    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen
        self.clock = pygame.time.Clock()
        self.running = True
        screen_width, screen_height = screen.get_size()
        search_height = max(42, int(screen_height * 0.08))
        self.search_rect = pygame.Rect(16, 12, screen_width - 32, search_height)
        self.grid_area = pygame.Rect(
            16,
            self.search_rect.bottom + 12,
            screen_width - 32,
            screen_height - (self.search_rect.bottom + 24),
        )
        min_cell_width, min_cell_height = 140, 140
        self.gap = 14
        self.columns = max(1, (self.grid_area.width + self.gap) // (min_cell_width + self.gap))
        self.cell_width = (self.grid_area.width - (self.columns - 1) * self.gap) // self.columns
        self.cell_height = min_cell_height
        indexed = index_images(images_root())
        self.all_names = [name for name, _ in indexed]
        random.shuffle(self.all_names)
        self.name_to_path: dict[str, str] = dict(indexed)
        self.thumbnails: dict[str, pygame.Surface] = {}
        self.prefix = ""
        self.random_selection_cache: dict[str, list[str]] = {}
        self.search_mode = True
        self.search_hits: list[tuple[str, pygame.Rect]] = []
        self.grid_tiles: list[tuple[str, pygame.Rect]] = []

        class SearchFocusRenderer(FocusRenderer):
            def draw_focus_indicator(self, screen: pygame.Surface, rect: pygame.Rect) -> None:
                clear_padding = 6
                if rect.width > 60:
                    focus_rect = pygame.Rect(
                        rect.left - clear_padding,
                        rect.top - clear_padding,
                        rect.width + clear_padding * 2,
                        rect.height + clear_padding * 2,
                    )
                    corner_length = max(6, min(10, rect.height // 3))
                else:
                    font_size = min(32, max(16, int((rect.height - 12) * 0.8)))
                    font = pygame.font.Font(None, font_size)
                    text_height = font.get_height()
                    focus_rect = pygame.Rect(
                        rect.left, rect.centery - text_height // 2 - 2, rect.width, text_height + 4
                    )
                    corner_length = max(4, min(8, text_height // 3))
                self._draw_corner_brackets(screen, focus_rect, corner_length)

        search_focus_renderer = SearchFocusRenderer(thickness=2, corner_size_factor=0.2, padding=0)
        self.init_focus_system(renderer=search_focus_renderer)

    def get_visible_names(self, capacity: int) -> list[str]:
        candidates = filter_names_by_prefix(self.all_names, self.prefix)
        if not self.prefix:
            return self.all_names[:capacity]
        if len(candidates) <= capacity:
            return candidates
        cache_key = self.prefix
        if cache_key not in self.random_selection_cache:
            self.random_selection_cache[cache_key] = random.sample(candidates, capacity)
        return self.random_selection_cache[cache_key]

    def canonical_key(self, name: str) -> str:
        import re

        s = name.lower()
        s = s.replace("♀", "-f").replace("♂", "-m")
        s = s.replace("_", "-")
        s = re.sub(r"[^a-z0-9-]", "-", s).strip("-")
        return s

    def map_evo_key_to_species_directory(self, key: str) -> str | None:
        if key in self.name_to_path:
            return key
        for candidate in (key.replace("-", "_"), key.replace("-", ""), key.replace("_", "-")):
            if candidate in self.name_to_path:
                return candidate
        for name in self.all_names:
            if self.canonical_key(name) == key:
                return name
        return None

    def get_focusable_elements(self) -> list[FocusableElement]:
        elements = []
        if self.search_mode:
            for letter, rect in self.search_hits:

                def make_search_callback(letter_text: str) -> callable:
                    def callback() -> None:
                        if letter_text == "CLEAR":
                            self.clear_search()
                        else:
                            self.add_to_search(letter_text.lower())
                        self.update_focus_elements()
                        self.focus_manager.current_row = 0
                        self.focus_manager.current_column = 0
                        return None

                    return callback

                elements.append(
                    FocusableElement(
                        rect=rect,
                        callback=make_search_callback(letter),
                        enabled=True,
                        metadata={"type": "search_letter", "letter": letter},
                    )
                )
        else:
            for name, rect in self.grid_tiles:

                def make_grid_callback(pokemon_name: str) -> callable:
                    def callback() -> None:
                        self.select_pokemon(pokemon_name)
                        return None

                    return callback

                elements.append(
                    FocusableElement(
                        rect=rect,
                        callback=make_grid_callback(name),
                        enabled=True,
                        metadata={"type": "pokemon_tile", "name": name},
                    )
                )
        return elements

    def handle_focus_event(self, event: pygame.event.Event) -> bool:
        if event.type != pygame.KEYDOWN:
            return False
        if event.key == pygame.K_ESCAPE:
            self.running = False
            return True
        if event.key == pygame.K_BACKSPACE:
            self.clear_search()
            self.search_mode = True
            self.update_focus_elements()
            return True
        if event.key == pygame.K_UP:
            if self.search_mode:
                self.search_mode = False
                self.focus_last_pokemon()
                return True
            else:
                if self.focus_manager.current_row == 0:
                    self.search_mode = True
                    self.update_focus_elements()
                    self.focus_manager.current_row = 0
                    self.focus_manager.current_column = 0
                    return True
        if event.key == pygame.K_DOWN and self.search_mode:
            self.search_mode = False
            self.focus_first_pokemon()
            return True
        return super().handle_focus_event(event)

    def clear_search(self) -> None:
        old_prefix = self.prefix
        self.prefix = ""
        if self.prefix != old_prefix:
            self.random_selection_cache.clear()

    def add_to_search(self, letter: str) -> None:
        old_prefix = self.prefix
        self.prefix += letter
        if self.prefix != old_prefix:
            self.random_selection_cache.clear()

    def select_pokemon(self, name: str) -> None:
        card_app = PokemonCard(self.screen, name)
        result = card_app.run_modal()
        if result == NavigationAction.EXIT_TO_LAUNCHER:
            self.running = False
        self.update_focus_elements()

    def focus_first_pokemon(self) -> None:
        self.update_focus_elements()
        elements = self.get_focusable_elements()
        if elements:
            self.focus_manager.current_row = 0
            self.focus_manager.current_column = 0

    def focus_last_pokemon(self) -> None:
        self.update_focus_elements()
        elements = self.get_focusable_elements()
        if elements:
            columns = self.columns if not self.search_mode else len(elements)
            total_elements = len(elements)
            self.focus_manager.current_row = (total_elements - 1) // columns
            self.focus_manager.current_column = (total_elements - 1) % columns

    def update_focus_elements(self) -> None:
        elements = self.get_focusable_elements()
        columns = (len(elements) if elements else 1) if self.search_mode else self.columns
        callbacks = [elem.callback for elem in elements]
        enabled_mask = [elem.enabled for elem in elements]
        grid_elements_2d = create_grid_elements(
            [elem.rect for elem in elements], callbacks, columns, enabled_mask
        )
        element_index = 0
        for row in grid_elements_2d:
            for grid_element in row:
                if element_index < len(elements):
                    grid_element.metadata = elements[element_index].metadata
                    element_index += 1
        self.focus_manager.update_elements(grid_elements_2d)

    def run(self) -> None:
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    # Cleanup handled by card instance
                    pass
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False
                    else:
                        self.handle_focus_event(event)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.handle_mouse_click(event)
            self.update_display()

    def handle_mouse_click(self, event: pygame.event.Event) -> None:
        mouse_x, mouse_y = event.pos
        for label, rect in self.search_hits:
            if rect.collidepoint(mouse_x, mouse_y):
                if label == "CLEAR":
                    self.clear_search()
                else:
                    self.add_to_search(label.lower())
                self.update_focus_elements()
                break
        else:
            rows_visible = max(
                1, (self.grid_area.height + self.gap) // (self.cell_height + self.gap)
            )
            capacity = self.columns * rows_visible
            visible = self.get_visible_names(capacity)
            for i, name in enumerate(visible):
                row = i // self.columns
                col = i % self.columns
                y = self.grid_area.top + row * (self.cell_height + self.gap)
                x = self.grid_area.left + col * (self.cell_width + self.gap)
                tile_rect = pygame.Rect(x, y, self.cell_width, self.cell_height)
                if tile_rect.collidepoint(mouse_x, mouse_y):
                    self.select_pokemon(name)
                    break

    def update_display(self) -> None:
        rows_visible = max(1, (self.grid_area.height + self.gap) // (self.cell_height + self.gap))
        capacity = self.columns * rows_visible
        visible = self.get_visible_names(capacity)
        for name in visible:
            if name not in self.thumbnails:
                path = self.name_to_path.get(name)
                if path:
                    surface = _load_thumbnail(path, (self.cell_width, self.cell_height - 28))
                    if surface is not None:
                        self.thumbnails[name] = surface
        self.screen.fill(DARK_BG)
        candidates = filter_names_by_prefix(self.all_names, self.prefix)
        next_letters = [] if len(candidates) == 1 else compute_next_letters(candidates, self.prefix)
        self.search_hits = draw_letter_strip(
            self.screen, self.search_rect, next_letters, self.prefix
        )
        if visible:
            self.grid_tiles = _draw_grid(
                self.screen,
                self.grid_area,
                visible,
                self.thumbnails,
                self.columns,
                (self.cell_width, self.cell_height),
                0,
            )
        else:
            message_font = pygame.font.Font(None, 28)
            message = "No matches. Click CLEAR to reset"
            surface = message_font.render(message, True, (190, 190, 200))
            self.screen.blit(surface, surface.get_rect(center=self.grid_area.center))
            self.grid_tiles = []
        self.update_focus_elements()
        if self.search_mode and self.get_focusable_elements():
            if self.focus_manager.current_row < 0 or self.focus_manager.current_column < 0:
                self.focus_manager.current_row = 0
                self.focus_manager.current_column = 0
        self.draw_focus_indicator(self.screen)
        pygame.display.flip()
        self.clock.tick(60)

    def draw_focus_indicator(self, screen: pygame.Surface) -> None:
        if is_any_audio_playing():
            return
        super().draw_focus_indicator(screen)

    def handle_navigation_result(self, result: NavigationResult) -> bool:
        """Handle navigation results from focus system."""
        if result.action == NavigationAction.EXIT:
            self.running = False
            return True
        elif result.action == NavigationAction.ACTIVATE:
            # Focus system handled the activation
            return True
        return False


def run_on_existing_display(screen: pygame.Surface) -> None:
    app = PokedexApp(screen)
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
