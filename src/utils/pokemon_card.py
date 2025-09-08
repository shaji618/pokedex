from __future__ import annotations

import contextlib
import json
import os
import random
import re
import time
from typing import Any

import pygame
from PIL import Image

from src.utils.audio_util import pokemon_cry_exists, stop_named_channel
from src.utils.focus_integration import FocusIntegrationMixin
from src.utils.focus_manager import (
    FocusableElement,
    FocusManager,
    NavigationAction,
    NavigationResult,
)
from src.utils.focus_renderer import FocusRenderer
from src.utils.image_util import load_image_from_resources, load_animated_gif, AnimatedGif
from src.utils.palette import GEN_COLOR_MAP, TYPE_COLOR_MAP
from src.utils.pill_util import draw_pill
from src.utils.play_button_util import (
    PlayButton,
    create_pokemon_cry_play_button,
    is_any_audio_playing,
)
from src.utils.pokemon_image_util import images_root as _images_root
from src.utils.pokemon_types import TYPE_STRONG_AGAINST, TYPE_WEAK_TO, PokemonType
from src.utils.string_util import wrap_text
from src.utils.surface_util import grayscale_surface, scale_surface_to_fit
from src.utils.tts_util import _tts_state, is_speaking, speak_pokemon_description, stop_speech


# Global cache clearing function is no longer needed since we removed global caches


def _darken_color(color: tuple[int, int, int], factor: float = 0.7) -> tuple[int, int, int]:
    return (int(color[0] * factor), int(color[1] * factor), int(color[2] * factor))





# Arrow utilities for variant navigation (adapted from voice_selector.py)
def _load_variant_arrow_base() -> pygame.Surface | None:
    """Load the base arrow icon for variant navigation."""
    surf = load_image_from_resources("src.utils.media", "arrow.png")
    if surf is None:
        return None
    return pygame.transform.rotate(surf, -90)


def _get_variant_arrow_icon(target_height: int) -> pygame.Surface | None:
    """Get arrow icon scaled to target height for variant navigation."""
    if target_height <= 0:
        return None
    base = _load_variant_arrow_base()
    if base is None:
        return None
    bw, bh = base.get_size()
    scale = target_height / max(1, bh)
    new_size = (max(1, int(bw * scale)), max(1, int(bh * scale)))
    return pygame.transform.smoothscale(base, new_size)


# Constants
CIRCLE_DIAMETER: int = 64
EVOLUTION_GAP_X: int = 14
NAME_OVERLAY_HEIGHT_FRACTION: float = 0.34
NAME_OVERLAY_BOTTOM_OFFSET: int = 26
PILL_HEIGHT: int = 26
EVOLUTION_ROW_BOTTOM_SPACING: int = 26


# Global function - will be converted to method later
def load_card_images(species: str) -> tuple[pygame.Surface | None, pygame.Surface | None]:
    """Load card images for species. No global caching to prevent segfaults."""
    base = str(_images_root())
    species_directory = os.path.join(base, species)
    main_path = os.path.join(species_directory, "main.png")
    name_path = os.path.join(species_directory, "name.png")
    main_surface = None
    name_surface = None
    try:
        if os.path.exists(main_path):
            main_surface = pygame.image.load(main_path).convert_alpha()
    except Exception:
        main_surface = None
    try:
        if os.path.exists(name_path):
            name_surface = pygame.image.load(name_path).convert_alpha()
    except Exception:
        name_surface = None
    if name_surface is None:
        try:
            display = species.replace("_", " ").title()
            base_font_size = 72
            font = pygame.font.Font(None, base_font_size)
            text_color = (235, 235, 245)
            shadow_color = (30, 30, 36)
            text_surface = font.render(display, True, text_color)
            shadow_surface = font.render(display, True, shadow_color)
            padding = 8
            width = max(text_surface.get_width(), shadow_surface.get_width()) + padding * 2
            height = max(text_surface.get_height(), shadow_surface.get_height()) + padding * 2
            composed = pygame.Surface((width, height), pygame.SRCALPHA)
            composed.blit(shadow_surface, (padding + 2, padding + 2))
            composed.blit(text_surface, (padding, padding))
            name_surface = composed
        except Exception:
            name_surface = None
    return (main_surface, name_surface)


def render_pokemon_card_overlay(
    screen: pygame.Surface,
    screen_rect: pygame.Rect,
    species: str,
    *,
    custom_main_image: pygame.Surface | None = None,
    # Pass caches from the calling PokemonCard instance to avoid global state
    overlay_cache: dict | None = None,
    scaled_image_cache: dict | None = None,
    cry_play_buttons: dict | None = None,
    text_to_speech_play_buttons: dict | None = None,
    sprite_gray_cache: dict | None = None,
    pokedex_entry_cache: dict | None = None,
) -> dict[str, object]:
    """Render Pokemon card overlay. Uses passed caches instead of globals."""
    # Use passed caches or create temporary ones
    if overlay_cache is None:
        overlay_cache = {}
    if scaled_image_cache is None:
        scaled_image_cache = {}
    if cry_play_buttons is None:
        cry_play_buttons = {}
    if text_to_speech_play_buttons is None:
        text_to_speech_play_buttons = {}
    if sprite_gray_cache is None:
        sprite_gray_cache = {}
    if pokedex_entry_cache is None:
        pokedex_entry_cache = {}

    # Always use standardized behavior
    # Standardized behavior - always Pokedex-style (no flags needed)

    overlay_key = (screen_rect.width, screen_rect.height)
    overlay = overlay_cache.get(overlay_key)
    if overlay is None:
        overlay = pygame.Surface(screen_rect.size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        overlay_cache[overlay_key] = overlay
    screen.blit(overlay, screen_rect.topleft)
    card_width = min(900, int(screen_rect.width * 0.8))
    card_height = min(750, int(screen_rect.height * 0.75))
    card_rect = pygame.Rect(0, 0, card_width, card_height)
    card_rect.center = screen_rect.center
    pygame.draw.rect(screen, (28, 28, 34), card_rect, border_radius=16)
    pygame.draw.rect(screen, (80, 160, 240), card_rect, width=2, border_radius=16)
    if custom_main_image is not None:
        main_image = custom_main_image
        _, name_image = load_card_images(species)
    else:
        main_image, name_image = load_card_images(species)
    padding = 16
    content_rectangle = card_rect.inflate(-padding * 2, -padding * 2)
    header_height = 110 if name_image else 0
    header_area = pygame.Rect(
        content_rectangle.left, content_rectangle.top, content_rectangle.width, header_height
    )
    phonetic_surface = None
    extra_phonetic_height = 0
    if name_image:
        try:
            metadata_initial = _load_metadata(species)
            pronunciations = metadata_initial.get("pronunciations") or {}
            phonetic_text = str(pronunciations.get("phonetic") or "").strip()
            if phonetic_text:
                phonetic_font = pygame.font.Font(None, 20)
                phonetic_surface = phonetic_font.render(phonetic_text, True, (200, 200, 210))
                extra_phonetic_height = 4 + phonetic_surface.get_height() + 2
        except Exception:
            phonetic_surface = None
            extra_phonetic_height = 0
    body_top = (
        header_area.bottom
        + (padding if name_image else 0)
        + (extra_phonetic_height if phonetic_surface is not None else 0)
    )
    body_area = pygame.Rect(
        content_rectangle.left,
        body_top,
        content_rectangle.width,
        content_rectangle.bottom - body_top,
    )
    left_column_width = int(content_rectangle.width * 0.52)
    main_area = pygame.Rect(body_area.left, body_area.top, left_column_width, body_area.height)
    right_area = pygame.Rect(
        main_area.right + padding,
        body_area.top,
        body_area.right - (main_area.right + padding),
        body_area.height,
    )
    play_hit_rect: pygame.Rect | None = None
    if name_image and header_area.height > 0:
        try:
            name_key = (species, "name", header_area.width, header_area.height)
            scaled = scaled_image_cache.get(name_key)
            if scaled is None:
                scaled = scale_surface_to_fit(name_image, (header_area.width, header_area.height))
                scaled_image_cache[name_key] = scaled
            image_rect = scaled.get_rect(center=header_area.center)
            screen.blit(scaled, image_rect)
            try:
                has_cry = pokemon_cry_exists(species)
            except Exception:
                has_cry = False
            if has_cry:
                if species not in cry_play_buttons:
                    cry_play_buttons[species] = create_pokemon_cry_play_button(species)
                cry_button = cry_play_buttons[species]
                target_height = int(header_area.height * 0.5)
                button_rect = pygame.Rect(0, 0, target_height, target_height)
                button_rect.centery = image_rect.centery - max(2, int(target_height * 0.06))
                button_rect.left = image_rect.right + 8
                if button_rect.right > header_area.right - 6:
                    button_rect.right = header_area.right - 6
                    button_rect.left = button_rect.right - target_height
                cry_button.draw(screen, button_rect, target_height=target_height)
                if not cry_button.is_disabled():
                    play_hit_rect = button_rect.copy()
            metadata_types = _load_metadata(species).get("types") or []
            if metadata_types:
                type_labels = [pokemon_type.title() for pokemon_type in metadata_types]
                pill_height = PILL_HEIGHT
                gap_column = 8
                gap_row = 4
                padding_x = 12
                font = pygame.font.Font(None, 22)
                columns: list[list[tuple[pygame.Surface, int]]] = []
                for index, label in enumerate(type_labels):
                    surface = font.render(label, True, (20, 22, 24))
                    pill_width = surface.get_width() + padding_x * 2
                    column_index = index // 2
                    if column_index >= len(columns):
                        columns.append([])
                    columns[column_index].append((surface, pill_width))
                column_widths = [
                    max((width for (_surface, width) in column), default=0) for column in columns
                ]
                right_anchor = image_rect.left - 8
                baseline_y = image_rect.centery
                preliminary_x_lefts: list[int] = []
                for column_j, _column in enumerate(columns):
                    column_width = column_widths[column_j]
                    preliminary_x_lefts.append(
                        right_anchor - sum(column_widths[: column_j + 1]) - gap_column * column_j
                    )
                shift_delta_x = 0
                min_allowed = header_area.left + 6
                if preliminary_x_lefts and min(preliminary_x_lefts) < min_allowed:
                    shift_delta_x = min_allowed - min(preliminary_x_lefts)
                for column_j, column in enumerate(columns):
                    column_width = column_widths[column_j]
                    x_left = (
                        right_anchor
                        - sum(column_widths[: column_j + 1])
                        - gap_column * column_j
                        + shift_delta_x
                    )
                    for row_2, (_surface, _width) in enumerate(column):
                        label = type_labels[column_j * 2 + row_2]
                        try:
                            type_enum = PokemonType(label.lower())
                            type_top, type_bottom = TYPE_COLOR_MAP.get(
                                type_enum, ((180, 180, 180), (180, 180, 180))
                            )
                        except ValueError:
                            type_top, type_bottom = ((180, 180, 180), (180, 180, 180))
                        pill_rect = pygame.Rect(0, 0, column_width, pill_height)
                        if len(column) == 1:
                            pill_rect.centery = baseline_y
                        else:
                            if row_2 == 0:
                                pill_rect.bottom = baseline_y - gap_row // 2
                            else:
                                pill_rect.top = baseline_y + gap_row // 2
                        pill_rect.left = x_left
                        draw_pill(screen, pill_rect, type_top, type_bottom, label.upper(), font)
            if phonetic_surface is not None:
                phonetic_rect = phonetic_surface.get_rect()
                phonetic_rect.centerx = header_area.centerx
                phonetic_rect.top = header_area.bottom + 4
                screen.blit(phonetic_surface, phonetic_rect)
        except Exception:
            pass
    main_image_rect = None
    if main_image and main_area.height > 0 and main_area.width > 0:
        main_key = (species, "main", main_area.width, main_area.height)
        scaled = scaled_image_cache.get(main_key)
        if scaled is None:
            scaled = scale_surface_to_fit(main_image, (main_area.width, main_area.height))
            scaled_image_cache[main_key] = scaled
        image_rect = scaled.get_rect(center=main_area.center)
        main_image_rect = image_rect  # Capture for pills positioning
        screen.blit(scaled, image_rect)
    metadata = _load_metadata(species)
    evolution_hits, text_to_speech_play_hit_rect = _draw_right_panel(
        screen,
        right_area,
        species,
        metadata,
        sprite_gray_cache=sprite_gray_cache,
        text_to_speech_play_buttons=text_to_speech_play_buttons,
        pokedex_entry_cache=pokedex_entry_cache,
    )
    return {
        "card_rect": card_rect,
        "main_image_rect": main_image_rect,
        "evo_hits": evolution_hits,
        "play_rect": play_hit_rect,
        "tts_play_rect": text_to_speech_play_hit_rect,
    }


def _load_metadata(species: str) -> dict:
    """Load metadata for species. No global caching."""
    try:
        base = str(_images_root())
        species_directory = os.path.join(base, species)
        metadata_path = os.path.join(species_directory, "metadata.json")
        if not os.path.exists(metadata_path):
            return {}
        with open(metadata_path, encoding="utf-8") as f:
            metadata = json.load(f)
        return metadata
    except Exception:
        return {}


def _compute_effect_sets(types: list[str]) -> tuple[list[str], list[str]]:
    types_normalized = [pokemon_type.lower() for pokemon_type in types]
    strong: set[str] = set()
    weak: set[str] = set()
    for pokemon_type in types_normalized:
        try:
            type_enum = PokemonType(pokemon_type)
            strong |= {enum_type.value for enum_type in TYPE_STRONG_AGAINST.get(type_enum, set())}
            weak |= {enum_type.value for enum_type in TYPE_WEAK_TO.get(type_enum, set())}
        except ValueError:
            continue
    return (sorted(strong), sorted(weak))


def _choose_text_color_for_background(
    top: tuple[int, int, int], bottom: tuple[int, int, int]
) -> tuple[int, int, int]:
    average = ((top[0] + bottom[0]) // 2, (top[1] + bottom[1]) // 2, (top[2] + bottom[2]) // 2)
    luminance = (0.2126 * average[0] + 0.7152 * average[1] + 0.0722 * average[2]) / 255.0
    return (255, 255, 255) if luminance < 0.56 else (20, 22, 24)


def _derive_border_color(
    top: tuple[int, int, int], bottom: tuple[int, int, int]
) -> tuple[int, int, int]:
    average = ((top[0] + bottom[0]) // 2, (top[1] + bottom[1]) // 2, (top[2] + bottom[2]) // 2)
    return (max(0, average[0] - 30), max(0, average[1] - 30), max(0, average[2] - 30))


def _get_primary_type_colors_for_key(key: str) -> tuple[tuple[int, int, int], tuple[int, int, int]]:
    directory_name = _map_key_to_dirname(key)
    top = (180, 180, 180)
    bottom = (180, 180, 180)
    if directory_name:
        metadata = _load_metadata(directory_name)
        type_list = metadata.get("types") or []
        if type_list:
            try:
                type_enum = PokemonType(str(type_list[0]).lower())
                colors = TYPE_COLOR_MAP.get(type_enum)
            except ValueError:
                colors = None
            if colors:
                top, bottom = colors
    return top, bottom


def _choose_pokedex_entry(species: str, metadata: dict, *, pokedex_entry_cache: dict | None = None) -> str:
    """Choose a random pokedex entry for species, cached per species."""
    if pokedex_entry_cache is None:
        pokedex_entry_cache = {}
    
    # Use cached entry if available
    if species in pokedex_entry_cache:
        return pokedex_entry_cache[species]
    
    # Choose and cache a random entry
    entries = metadata.get("pokedex_entries") or []
    choice = random.choice(entries).strip() if entries else ""
    pokedex_entry_cache[species] = choice
    return choice


def _draw_right_panel(
    screen: pygame.Surface,
    area: pygame.Rect,
    species: str,
    metadata: dict,
    *,
    sprite_gray_cache: dict | None = None,
    text_to_speech_play_buttons: dict | None = None,
    pokedex_entry_cache: dict | None = None,
) -> tuple[list[tuple[str, pygame.Rect]], pygame.Rect | None]:
    if sprite_gray_cache is None:
        sprite_gray_cache = {}
    if text_to_speech_play_buttons is None:
        text_to_speech_play_buttons = {}
    if pokedex_entry_cache is None:
        pokedex_entry_cache = {}
    if area.width <= 0 or area.height <= 0:
        return [], None
    x = area.left
    y = area.top
    width = area.width
    header_font = pygame.font.Font(None, 28)
    body_font = pygame.font.Font(None, 24)
    label_color = (170, 200, 255)
    text_color = (230, 230, 235)
    generation_value = metadata.get("generation")
    pokedex_number_value = metadata.get("pokedex_number")
    row_height = 0
    current_x = x
    gap_x = 10
    if pokedex_number_value is not None or generation_value is not None:
        if isinstance(generation_value, int) and 1 <= generation_value <= 9:
            generation_color = GEN_COLOR_MAP.get(generation_value, (160, 160, 160))
            generation_label = f"GENERATION {generation_value}"
            pill_height = 28
            padding_x = 12
            pill_font = pygame.font.Font(None, 22)
            text_surface = pill_font.render(
                generation_label,
                True,
                _choose_text_color_for_background(generation_color, generation_color),
            )
            pill_width = text_surface.get_width() + padding_x * 2
            pill_rect = pygame.Rect(current_x, y, pill_width, pill_height)
            draw_pill(
                screen, pill_rect, generation_color, generation_color, generation_label, pill_font
            )
            current_x = pill_rect.right + gap_x
            row_height = max(row_height, pill_height)
        if pokedex_number_value is not None:
            if isinstance(generation_value, int):
                base_color = GEN_COLOR_MAP.get(int(generation_value), (160, 160, 160))
                pill_color = _darken_color(base_color, 0.75)
            else:
                pill_color = text_color
            try:
                number_without_zeroes = str(int(pokedex_number_value))
            except (ValueError, TypeError):
                number_without_zeroes = str(pokedex_number_value).lstrip("0") or "0"
            pill_height = 28
            padding_x = 12
            pill_font = pygame.font.Font(None, 22)
            text_surface = pill_font.render(
                number_without_zeroes,
                True,
                _choose_text_color_for_background(pill_color, pill_color),
            )
            pill_width = text_surface.get_width() + padding_x * 2
            pill_rect = pygame.Rect(current_x, y, pill_width, pill_height)
            draw_pill(screen, pill_rect, pill_color, pill_color, number_without_zeroes, pill_font)
            current_x = pill_rect.right + gap_x
            row_height = max(row_height, pill_height)
    text_to_speech_play_rect: pygame.Rect | None = None
    if pokedex_number_value is not None or generation_value is not None:
        try:
            if species not in text_to_speech_play_buttons:
                description = str(metadata.get("description", "")).strip()
                entry = _choose_pokedex_entry(species, metadata, pokedex_entry_cache=pokedex_entry_cache)
                
                def play_description() -> None:
                    _tts_state.is_pending = True
                    speak_pokemon_description(description, entry, metadata)
                
                text_to_speech_play_buttons[species] = PlayButton(
                    play_description, is_audio_playing=is_speaking
                )
            text_to_speech_button = text_to_speech_play_buttons[species]
            target_height = max(24, int(row_height * 0.9)) if row_height > 0 else 28
            button_rect = pygame.Rect(0, 0, target_height, target_height)
            button_rect.centery = (
                y + (row_height // 2) if row_height > 0 else y + target_height // 2
            )
            button_rect.left = current_x + 8
            if button_rect.right > x + width - 6:
                button_rect.right = x + width - 6
                button_rect.left = button_rect.right - target_height
            text_to_speech_button.draw(screen, button_rect, target_height=target_height)
            if not text_to_speech_button.is_disabled():
                text_to_speech_play_rect = button_rect.copy()
        except Exception:
            pass
    if row_height:
        y += row_height + 10
    description = str(metadata.get("description", "")).strip()
    entry = _choose_pokedex_entry(species, metadata, pokedex_entry_cache=pokedex_entry_cache)
    combined = (description + (" " + entry if entry else "")).strip()
    line_height = body_font.get_height() + 4
    max_lines = 7
    if combined:
        lines = wrap_text(body_font, combined, width)
        for index, line in enumerate(lines[:max_lines]):
            surface = body_font.render(line, True, text_color)
            screen.blit(surface, (x, y + index * line_height))
    y += max_lines * line_height
    y += 6
    evolution_hits: list[tuple[str, pygame.Rect]] = []
    graph_edges = metadata.get("evolution_graph") or []
    chain = metadata.get("evolution_chain") or []
    if graph_edges or chain:
        label = header_font.render("Evolution:", True, label_color)
        screen.blit(label, (x, y))
        y += label.get_height() + 8

        def render_node(key: str, center: tuple[int, int]) -> pygame.Rect:
            title = key.replace("-", " ").title()
            circle_diameter = CIRCLE_DIAMETER
            circle_rect = pygame.Rect(0, 0, circle_diameter, circle_diameter)
            circle_rect.center = center
            is_current = (key == species.lower()) or (key == species.replace("_", "-").lower())
            if is_current:
                fill = (80, 160, 240)
                border = (45, 110, 190)
            else:
                fill = (200, 200, 205)
                border = (120, 120, 125)
            pygame.draw.ellipse(screen, fill, circle_rect)
            pygame.draw.ellipse(screen, border, circle_rect, width=3)
            sprite = _load_sprite_for_key(
                key, max_inner=(int(circle_diameter * 0.92), int(circle_diameter * 0.92))
            )
            if sprite is not None and not is_current:
                    gray = sprite_gray_cache.get(key)
                    if gray is None:
                        gray = grayscale_surface(sprite)
                        sprite_gray_cache[key] = gray
                    sprite = gray
            if sprite is not None:
                sprite_rect = sprite.get_rect(center=circle_rect.center)
                screen.blit(sprite, sprite_rect)
            name_overlay_rect: pygame.Rect | None = None
            if _map_key_to_dirname(key):
                _, name_logo = load_card_images(_map_key_to_dirname(key))
                if name_logo is not None:
                    name_box = (
                        circle_diameter,
                        int(circle_diameter * NAME_OVERLAY_HEIGHT_FRACTION),
                    )
                    name_scaled = scale_surface_to_fit(name_logo, name_box)
                    if not is_current:
                        name_scaled = grayscale_surface(name_scaled)
                    name_rect = name_scaled.get_rect(centerx=circle_rect.centerx)
                    name_rect.bottom = circle_rect.top + NAME_OVERLAY_BOTTOM_OFFSET
                    screen.blit(name_scaled, name_rect)
                    name_overlay_rect = name_rect
            if name_overlay_rect is None:
                pill_height = PILL_HEIGHT
                pill_width = int(circle_diameter * 0.9)
                pill_rect = pygame.Rect(0, 0, pill_width, pill_height)
                pill_rect.centerx = circle_rect.centerx
                pill_rect.top = circle_rect.bottom + 4
                type_top, type_bottom = _get_primary_type_colors_for_key(key)
                max_text_width = pill_rect.width - 2
                max_text_height = pill_rect.height - 2
                optimal_size = _best_font_size_for_rect(
                    title.upper(), max_text_width, max_text_height, min_size=10, max_size=48
                )
                font_for_draw = pygame.font.Font(None, optimal_size)
                draw_pill(screen, pill_rect, type_top, type_bottom, title.upper(), font_for_draw)
                name_overlay_rect = pill_rect
            union_left = min(circle_rect.left, name_overlay_rect.left)
            union_right = max(circle_rect.right, name_overlay_rect.right)
            union_top = min(circle_rect.top, name_overlay_rect.top)
            union_bottom = max(circle_rect.bottom, name_overlay_rect.bottom)
            hit_rect = pygame.Rect(
                union_left, union_top, union_right - union_left, union_bottom - union_top
            )
            evolution_hits.append((key, hit_rect))
            return circle_rect

        if graph_edges:
            edges = [
                (str(evolution.get("from")), str(evolution.get("to")))
                for evolution in graph_edges
                if evolution.get("from") and evolution.get("to")
            ]
            nodes = list(dict.fromkeys([node for edge in edges for node in edge]))
            incoming: dict[str, int] = dict.fromkeys(nodes, 0)
            adjacency: dict[str, list[str]] = {node: [] for node in nodes}
            for from_node, to_node in edges:
                adjacency[from_node].append(to_node)
                incoming[to_node] = incoming.get(to_node, 0) + 1
            root = None
            for node in chain:
                if node in nodes and incoming.get(node, 0) == 0:
                    root = node
                    break
            if root is None:
                roots = [node for node in nodes if incoming.get(node, 0) == 0]
                root = roots[0] if roots else (nodes[0] if nodes else None)
            inline_keys: list[str] = []
            branch_children: list[str] = []
            if root is not None:
                current = root
                while True:
                    inline_keys.append(current)
                    children = adjacency.get(current, [])
                    if len(children) <= 1:
                        if children:
                            current = children[0]
                            continue
                        break
                    order_index = {key: index for index, key in enumerate(chain)}
                    branch_children = sorted(
                        children, key=lambda key: order_index.get(key, 1_000_000)
                    )
                    break
            circle_diameter = CIRCLE_DIAMETER
            gap_x = EVOLUTION_GAP_X
            current_y = y
            current_x = x
            eevee_center_y = None
            for index, key in enumerate(inline_keys):
                circle_rect = render_node(
                    key, (current_x + circle_diameter // 2, current_y + circle_diameter // 2)
                )
                if index == 0:
                    eevee_center_y = circle_rect.centery
                current_x = circle_rect.right
                if index < len(inline_keys) - 1:
                    arrow_height = int(circle_diameter * 0.5)
                    icon = _get_arrow_icon(arrow_height)
                    if icon is not None:
                        arrow_rect = icon.get_rect(
                            midleft=(current_x + gap_x // 2, circle_rect.centery)
                        )
                        screen.blit(icon, arrow_rect)
                        current_x = arrow_rect.right + gap_x // 2
                    else:
                        arrow_surface = body_font.render(">", True, (220, 220, 225))
                        arrow_rect = arrow_surface.get_rect(
                            midleft=(current_x + gap_x // 2, circle_rect.centery)
                        )
                        screen.blit(arrow_surface, arrow_rect)
                        current_x = arrow_rect.right + gap_x // 2
            if branch_children:
                order_index = {key: index for index, key in enumerate(chain)}
                extra = [key for key in chain if key not in inline_keys]
                merged_children = list(dict.fromkeys(list(branch_children) + extra))
                branch_children = sorted(
                    merged_children, key=lambda key: order_index.get(key, 1_000_000)
                )
                approximate_arrow_width = int(circle_diameter * 0.5)
                approximate_usable_width = max(
                    0, width - (circle_diameter + gap_x + approximate_arrow_width)
                )
                cell_width_estimate = circle_diameter + gap_x
                approximate_columns = max(1, approximate_usable_width // cell_width_estimate)
                approximate_rows = (
                    len(branch_children) + approximate_columns - 1
                ) // approximate_columns
                row_height = circle_diameter + 18
                left_center_y = (
                    y + int(((approximate_rows - 1) * row_height) / 2) + circle_diameter // 2
                )
                current_y = int(left_center_y - circle_diameter // 2)
                last_center_y = (
                    eevee_center_y
                    if eevee_center_y is not None
                    else (current_y + circle_diameter // 2)
                )
                last_right = current_x
                arrow_height = int(circle_diameter * 0.5)
                icon = _get_arrow_icon(arrow_height)
                if icon is not None:
                    arrow_rect = icon.get_rect(midleft=(last_right + gap_x // 2, last_center_y))
                    screen.blit(icon, arrow_rect)
                    current_x = arrow_rect.right + gap_x // 2
                else:
                    arrow_surface = body_font.render(">", True, (220, 220, 225))
                    arrow_rect = arrow_surface.get_rect(
                        midleft=(last_right + gap_x // 2, last_center_y)
                    )
                    screen.blit(arrow_surface, arrow_rect)
                    current_x = arrow_rect.right + gap_x // 2
                max_right = x + width
                wrap_start_x = current_x
                cell_width = circle_diameter + gap_x
                usable_width = max(0, max_right - wrap_start_x)
                columns = max(1, usable_width // cell_width)
                rows = (len(branch_children) + columns - 1) // columns
                row_height = circle_diameter + 18
                row_center_y0 = last_center_y
                index = 0
                for row in range(rows):
                    current_x_row = wrap_start_x
                    for _column in range(columns):
                        if index >= len(branch_children):
                            break
                        child = branch_children[index]
                        center_y = row_center_y0 + row * row_height
                        pos = (current_x_row + circle_diameter // 2, center_y)
                        circle_rect = render_node(child, pos)
                        current_x_row = circle_rect.right + gap_x
                        index += 1
                y = (
                    row_center_y0
                    + (rows - 1) * row_height
                    + circle_diameter // 2
                    + EVOLUTION_ROW_BOTTOM_SPACING
                )
            else:
                y = current_y + circle_diameter + EVOLUTION_ROW_BOTTOM_SPACING
        else:
            start_x = x
            current_x = start_x
            current_y = y
            gap_x = EVOLUTION_GAP_X
            circle_diameter = CIRCLE_DIAMETER
            for index, key in enumerate(chain):
                circle_rect = render_node(
                    key, (current_x + circle_diameter // 2, current_y + circle_diameter // 2)
                )
                current_x = circle_rect.right
                if index < len(chain) - 1:
                    arrow_height = int(circle_diameter * 0.5)
                    icon = _get_arrow_icon(arrow_height)
                    if icon is not None:
                        arrow_rect = icon.get_rect(
                            midleft=(current_x + gap_x // 2, circle_rect.centery)
                        )
                        screen.blit(icon, arrow_rect)
                        current_x = arrow_rect.right + gap_x // 2
                    else:
                        arrow_surface = body_font.render(">", True, (220, 220, 225))
                        arrow_rect = arrow_surface.get_rect(
                            midleft=(current_x + gap_x // 2, circle_rect.centery)
                        )
                        screen.blit(arrow_surface, arrow_rect)
                        current_x = arrow_rect.right + gap_x // 2
            y = current_y + circle_diameter + EVOLUTION_ROW_BOTTOM_SPACING
    strong_list, weak_list = _compute_effect_sets(metadata.get("types") or [])
    strong_labels = [pokemon_type.title() for pokemon_type in strong_list]
    weak_labels = [pokemon_type.title() for pokemon_type in weak_list]
    if strong_labels or weak_labels:
        column_gap = 16
        column_width = (width - column_gap) // 2
        title_font = header_font
        strong_title = title_font.render("Strengths", True, label_color)
        weak_title = title_font.render("Weaknesses", True, label_color)
        screen.blit(strong_title, (x, y))
        screen.blit(weak_title, (x + column_width + column_gap, y))
        y += strong_title.get_height() + 6

        def draw_adaptive_pill_grid(start_x: int, labels: list[str]) -> int:
            """Draw pills that automatically shrink to fit within available space."""
            if not labels:
                return y

            available_height = area.bottom - y
            max_pills_per_row = 2
            estimated_rows = (len(labels) + max_pills_per_row - 1) // max_pills_per_row

            # Try different font sizes, starting large and going smaller
            for font_size in range(24, 14, -2):  # 24, 22, 20, 18, 16, 14
                test_font = pygame.font.Font(None, font_size)
                pill_height = max(20, font_size + 4)
                padding_x = max(8, font_size // 3)
                row_gap = 6

                # Estimate total height needed
                estimated_height = estimated_rows * (pill_height + row_gap)

                if estimated_height <= available_height:
                    # This font size should work, let's use it
                    return draw_pill_grid_with_font(
                        start_x, labels, test_font, pill_height, padding_x, row_gap
                    )

            # If we get here, use minimum font and truncate if needed
            min_font = pygame.font.Font(None, 14)
            min_pill_height = 18
            min_padding_x = 6
            min_row_gap = 4
            return draw_pill_grid_with_font(
                start_x, labels, min_font, min_pill_height, min_padding_x, min_row_gap
            )

        def draw_pill_grid_with_font(
            start_x: int,
            labels: list[str],
            font: pygame.font.Font,
            pill_height: int,
            padding_x: int,
            row_gap: int,
        ) -> int:
            grid_x = start_x
            grid_y = y
            current_x = grid_x
            current_y = grid_y
            index = 0

            while index < len(labels):
                # Check if we're running out of space
                if current_y + pill_height > area.bottom - 10:  # Leave some margin
                    break

                row_labels = labels[index : index + 2]
                row_x = current_x
                max_row_height = 0

                for label in row_labels:
                    surface = font.render(label.upper(), True, (0, 0, 0))
                    pill_width = min(column_width, surface.get_width() + padding_x * 2)

                    if row_x + pill_width > start_x + column_width and row_x > start_x:
                        row_x = start_x
                        current_y += max_row_height + row_gap
                        max_row_height = 0

                        # Check height again after wrapping
                        if current_y + pill_height > area.bottom - 10:
                            break

                    pill_rect = pygame.Rect(row_x, current_y, pill_width, pill_height)
                    try:
                        type_enum = PokemonType(label.lower())
                        top_color, bottom_color = TYPE_COLOR_MAP.get(
                            type_enum, ((180, 180, 180), (180, 180, 180))
                        )
                    except ValueError:
                        top_color, bottom_color = ((180, 180, 180), (180, 180, 180))

                    draw_pill(screen, pill_rect, top_color, bottom_color, label.upper(), font)
                    row_x += pill_width + 8
                    max_row_height = max(max_row_height, pill_height)

                current_y += max_row_height + row_gap
                index += 2

            return current_y

        y_left_end = draw_adaptive_pill_grid(x, strong_labels)
        y_right_end = draw_adaptive_pill_grid(x + column_width + column_gap, weak_labels)
        y = max(y_left_end, y_right_end)
    return evolution_hits, text_to_speech_play_rect


def _best_font_size_for_rect(
    text: str,
    max_width: int,
    max_height: int,
    *,
    min_size: int = 8,
    max_size: int = 72,
) -> int:
    best = min_size
    low, high = min_size, max_size
    while low <= high:
        middle = (low + high) // 2
        font = pygame.font.Font(None, middle)
        surface = font.render(text, True, (0, 0, 0))
        if surface.get_width() <= max_width and surface.get_height() <= max_height:
            best = middle
            low = middle + 1
        else:
            high = middle - 1

    return best


def _build_directory_index() -> dict[str, str]:
    """Build directory index. No global caching."""
    base = _images_root()
    index: dict[str, str] = {}
    try:
        for path in base.iterdir():
            if not path.is_dir():
                continue
            key = _canonical_key(path.name)
            index.setdefault(key, path.name)
    except Exception:
        pass
    return index


def _canonical_key(name: str) -> str:
    string = name.lower().replace("_", "-")
    string = string.replace("♀", "-f").replace("♂", "-m")
    string = re.sub(r"[^a-z0-9-]", "-", string).strip("-")
    return string


def _map_key_to_dirname(key: str) -> str | None:
    base = _images_root()
    for candidate in (key, key.replace("-", "_"), key.replace("_", "-"), key.replace("-", "")):
        if (base / candidate).is_dir():
            return candidate
    index = _build_directory_index()
    return index.get(_canonical_key(key))


def _load_sprite_for_key(key: str, *, max_inner: tuple[int, int]) -> pygame.Surface | None:
    """Load sprite for key. No global caching."""
    dirname = _map_key_to_dirname(key)
    if not dirname:
        return None
    sprite_path = os.path.join(str(_images_root()), dirname, "sprite.png")
    try:
        if os.path.exists(sprite_path):
            sprite = pygame.image.load(sprite_path).convert_alpha()
            image_width, image_height = sprite.get_size()
            scale = (
                min(max_inner[0] / image_width, max_inner[1] / image_height)
                if image_width and image_height
                else 1.0
            )
            new_size = (max(1, int(image_width * scale)), max(1, int(image_height * scale)))
            return pygame.transform.smoothscale(sprite, new_size)
    except Exception:
        pass
    return None


def _load_arrow_base() -> pygame.Surface | None:
    """Load arrow base image. No global caching."""
    surface = load_image_from_resources("src.utils.media", "arrow.png")
    if surface is not None:
        return pygame.transform.rotate(surface, -90)
    return None


def _get_arrow_icon(target_height: int) -> pygame.Surface | None:
    """Get arrow icon at target height. No global caching."""
    base = _load_arrow_base()
    if base is None or target_height <= 0:
        return None
    base_width, base_height = base.get_size()
    scale = target_height / max(1, base_height)
    new_size = (max(1, int(base_width * scale)), max(1, int(base_height * scale)))
    icon = pygame.transform.smoothscale(base, new_size)
    return icon


# handle_card_overlay_events function removed - no longer needed since PokemonCard
# class handles its own events and doesn't use global caches


class PokemonCardFocusManager(FocusManager):
    def __init__(self, pokemon_card: PokemonCard) -> None:
        super().__init__()
        self.pokemon_card = pokemon_card
        self.cry_button_element: FocusableElement | None = None
        self.text_to_speech_button_element: FocusableElement | None = None
        self.asset_elements: list[FocusableElement] = []
        self.evolution_elements: list[FocusableElement] = []

    def set_elements(
        self,
        cry_button: FocusableElement | None,
        text_to_speech_button: FocusableElement | None,
        asset_elements: list[FocusableElement],
        evolution_elements: list[FocusableElement],
    ) -> None:
        self.cry_button_element = cry_button
        self.text_to_speech_button_element = text_to_speech_button
        self.asset_elements = asset_elements
        self.evolution_elements = evolution_elements
        rows = []
        if cry_button:
            rows.append([cry_button])
        if text_to_speech_button:
            rows.append([text_to_speech_button])
        if asset_elements:
            rows.append(asset_elements)
        if evolution_elements:
            rows.append(evolution_elements)
        self.update_elements(rows)

    def handle_key_event(self, event: pygame.event.Event) -> NavigationResult:
        if event.type != pygame.KEYDOWN:
            return NavigationResult(NavigationAction.NONE)
        if event.key == pygame.K_ESCAPE:
            return NavigationResult(NavigationAction.EXIT_TO_LAUNCHER)
        elif event.key == pygame.K_BACKSPACE:
            return NavigationResult(NavigationAction.EXIT_TO_PARENT)
        else:
            # Use standard FocusManager navigation - just move cursor with arrows, activate with ENTER
            return super().handle_key_event(event)

    def _handle_navigation_key(self, key: int) -> None:
        current_element = self.get_focused_element()
        if current_element == self.cry_button_element:
            self._handle_cry_button_navigation(key)
        elif current_element == self.text_to_speech_button_element:
            self._handle_text_to_speech_button_navigation(key)
        elif current_element in self.asset_elements:
            self._handle_asset_navigation(key, current_element)
        elif current_element in self.evolution_elements:
            self._handle_evolution_navigation(key, current_element)

    def _handle_cry_button_navigation(self, key: int) -> None:
        if key == pygame.K_UP:
            self._try_fallback_sequence([self._last_evolution, self._text_to_speech_button])
        elif key == pygame.K_DOWN:
            self._try_fallback_sequence([self._text_to_speech_button])
        elif key == pygame.K_LEFT:
            self._try_fallback_sequence([self._last_evolution, self._text_to_speech_button])
        elif key == pygame.K_RIGHT:
            self._try_fallback_sequence([self._text_to_speech_button])

    def _handle_text_to_speech_button_navigation(self, key: int) -> None:
        if key == pygame.K_UP:
            self._try_fallback_sequence([self._cry_button, self._last_evolution])
        elif key == pygame.K_DOWN:
            self._try_fallback_sequence(
                [self._first_asset, self._first_evolution, self._cry_button]
            )
        elif key == pygame.K_LEFT:
            self._try_fallback_sequence([self._cry_button, self._last_evolution])
        elif key == pygame.K_RIGHT:
            self._try_fallback_sequence(
                [self._first_asset, self._first_evolution, self._cry_button]
            )

    def _handle_asset_navigation(self, key: int, current_element: FocusableElement) -> None:
        if key == pygame.K_UP:
            self._try_fallback_sequence([self._text_to_speech_button, self._cry_button])
        elif key == pygame.K_DOWN:
            self._try_fallback_sequence(
                [self._first_evolution, self._cry_button, self._text_to_speech_button]
            )
        elif key == pygame.K_LEFT:
            current_index = self.asset_elements.index(current_element)
            if current_index == 0:
                # At beginning of current page - try to go to previous page
                if self.pokemon_card.get_total_pages() > 1:
                    self.pokemon_card.previous_pill_page()
                    # Update focus elements and go to last element of new page
                    self.pokemon_card.update_focus_elements()
                    if self.asset_elements:
                        last_element = self.asset_elements[-1]
                        self._move_to_element(last_element)
                else:
                    self._try_fallback_sequence([self._text_to_speech_button, self._cry_button])
            else:
                # Normal left navigation within page
                super()._handle_arrow_navigation(key)
        elif key == pygame.K_RIGHT:
            current_index = self.asset_elements.index(current_element)
            if current_index == len(self.asset_elements) - 1:
                # At end of current page - try to go to next page
                if self.pokemon_card.get_total_pages() > 1:
                    self.pokemon_card.next_pill_page()
                    # Update focus elements and go to first element of new page
                    self.pokemon_card.update_focus_elements()
                    if self.asset_elements:
                        first_element = self.asset_elements[0]
                        self._move_to_element(first_element)
                else:
                    self._try_fallback_sequence(
                        [self._first_evolution, self._cry_button, self._text_to_speech_button]
                    )
            else:
                # Normal right navigation within page
                super()._handle_arrow_navigation(key)

    def _handle_evolution_navigation(self, key: int, current_element: FocusableElement) -> None:
        if key == pygame.K_UP:
            self._try_fallback_sequence(
                [self._last_asset, self._text_to_speech_button, self._cry_button]
            )
        elif key == pygame.K_DOWN:
            self._try_fallback_sequence([self._cry_button, self._text_to_speech_button])
        elif key == pygame.K_LEFT:
            current_index = self.evolution_elements.index(current_element)
            if current_index == 0:
                self._try_fallback_sequence(
                    [self._last_asset, self._text_to_speech_button, self._cry_button]
                )
            else:
                previous_element = self.evolution_elements[current_index - 1]
                self._move_to_element(previous_element)
        elif key == pygame.K_RIGHT:
            current_index = self.evolution_elements.index(current_element)
            if current_index == len(self.evolution_elements) - 1:
                self._try_fallback_sequence([self._cry_button, self._text_to_speech_button])
            else:
                next_element = self.evolution_elements[current_index + 1]
                self._move_to_element(next_element)

    def _try_fallback_sequence(self, fallback_functions: list[callable]) -> None:
        for fallback_function in fallback_functions:
            element = fallback_function()
            if element:
                self._move_to_element(element)
                return

    def _cry_button(self) -> FocusableElement | None:
        return self.cry_button_element

    def _text_to_speech_button(self) -> FocusableElement | None:
        return self.text_to_speech_button_element

    def _first_evolution(self) -> FocusableElement | None:
        return self.evolution_elements[0] if self.evolution_elements else None

    def _last_evolution(self) -> FocusableElement | None:
        return self.evolution_elements[-1] if self.evolution_elements else None

    def _first_asset(self) -> FocusableElement | None:
        return self.asset_elements[0] if self.asset_elements else None

    def _last_asset(self) -> FocusableElement | None:
        return self.asset_elements[-1] if self.asset_elements else None

    def _move_to_element(self, target_element: FocusableElement) -> None:
        for row_index, row in enumerate(self._elements):
            for column_index, element in enumerate(row):
                if element == target_element:
                    self.current_row = row_index
                    self.current_column = column_index
                    return


class PokemonCard(FocusIntegrationMixin):
    def __init__(self, screen: pygame.Surface, species: str) -> None:
        self.screen = screen
        self.species = species
        
        # UI state
        self.cry_play_rect: pygame.Rect | None = None
        self.text_to_speech_play_rect: pygame.Rect | None = None
        self.evolution_hits: list[tuple[str, pygame.Rect]] = []
        self.card_user_interface: dict[str, Any] = {}
        self.exit_action: NavigationAction | None = None
        self.species_changed_callback: callable | None = None
        
        # Cache state (previously in global _card_state)
        self.image_cache: dict[str, tuple[pygame.Surface | None, pygame.Surface | None]] = {}
        self.entry_choice_cache: dict[str, str] = {}
        self.metadata_cache: dict[str, dict] = {}
        self.sprite_cache: dict[str, pygame.Surface | None] = {}
        self.sprite_gray_cache: dict[str, pygame.Surface | None] = {}
        self.directory_index: dict[str, str] | None = None
        self.arrow_base: pygame.Surface | None = None
        self.arrow_cache: dict[int, pygame.Surface] = {}
        self.last_spoken_species: str | None = None
        self.overlay_cache: dict[tuple[int, int], pygame.Surface] = {}
        self.scaled_image_cache: dict[tuple[str, str, int, int], pygame.Surface] = {}
        self.cry_play_buttons: dict[str, object] = {}
        self.text_to_speech_play_buttons: dict[str, object] = {}

        # Hunt assets feature
        self.hunt_assets: list[str] = []
        self.current_asset_index: int = 0  # 0 = main.png, 1+ = hunt assets
        self.hunt_assets_cache: dict[str, pygame.Surface | AnimatedGif | None] = {}
        self.asset_pills: list[tuple[str, pygame.Rect]] = []
        
        # Pill pagination
        self.pills_per_page: int = 4
        self.current_pill_page: int = 0

        # Arrow-based variant navigation
        self.current_variant_index: int = 0  # 0 = main, 1+ = hunt assets index
        self.variant_left_arrow_rect: pygame.Rect | None = None
        self.variant_right_arrow_rect: pygame.Rect | None = None
        self.variant_display_rect: pygame.Rect | None = None
        
        # Initialize focus system
        renderer = FocusRenderer(thickness=3, corner_size_factor=0.2, padding=8)
        self.init_focus_system(renderer=renderer, auto_update=False)
        self.focus_manager = PokemonCardFocusManager(self)

        # Load hunt assets for this species
        self.hunt_assets = self.load_hunt_assets()

    def set_species_change_callback(self, callback: callable) -> None:
        self.species_changed_callback = callback

    def get_focusable_elements(self) -> list[list[FocusableElement]]:
        rows = []
        if self.cry_play_rect:
            cry_element = FocusableElement(
                rect=self.cry_play_rect,
                callback=self._play_cry,
                enabled=True,
                metadata={"name": "cry_button"},
            )
            rows.append([cry_element])
        if self.text_to_speech_play_rect:
            text_to_speech_element = FocusableElement(
                rect=self.text_to_speech_play_rect,
                callback=self._play_text_to_speech,
                enabled=True,
                metadata={"name": "tts_button"},
            )
            rows.append([text_to_speech_element])
        
        # Evolution circles (row 3)
        if self.evolution_hits:
            evolution_row = []
            for evolution_key, evolution_rect in self.evolution_hits:

                def make_evolution_callback(evolution_key: str) -> callable:
                    def callback() -> None:
                        self._select_evolution(evolution_key)

                    return callback

                evolution_row.append(
                    FocusableElement(
                        rect=evolution_rect,
                        callback=make_evolution_callback(evolution_key),
                        metadata={"name": "evolution_circle", "evolution_key": evolution_key},
                    )
                )
            rows.append(evolution_row)
        
        # Asset selection pills (row 4)
        if self.asset_pills:
            asset_row = []
            for asset_name, asset_rect in self.asset_pills:
                # Create callback with closure to capture asset_name
                callback = lambda name=asset_name: self._select_asset(name)
                
                asset_row.append(
                    FocusableElement(
                        rect=asset_rect,
                        callback=callback,
                        metadata={"name": "asset_pill", "asset_name": asset_name},
                    )
                )
            rows.append(asset_row)
        

        return rows

    def _play_cry(self) -> None:
        if self.species in self.cry_play_buttons:
            cry_button = self.cry_play_buttons[self.species]
            cry_button.handle_click()

    def _play_text_to_speech(self) -> None:
        if self.species in self.text_to_speech_play_buttons:
            text_to_speech_button = self.text_to_speech_play_buttons[self.species]
            text_to_speech_button.handle_click()

    def _select_evolution(self, evolution_key: str) -> None:
        mapped_species = self._map_key_to_dirname(evolution_key)
        if mapped_species and mapped_species != self.species:
            self._cleanup()
            self.species = mapped_species
            
            # Reload hunt assets for the new species
            self.hunt_assets = self.load_hunt_assets()
            self.current_asset_index = 0  # Reset to main.png
            
            if self.species_changed_callback:
                self.species_changed_callback(self.species)

    def handle_navigation_result(self, result: NavigationResult) -> bool:
        if result.action == NavigationAction.EXIT_TO_PARENT:
            self.exit_action = NavigationAction.EXIT_TO_PARENT
            return True
        elif result.action == NavigationAction.EXIT_TO_LAUNCHER:
            self.exit_action = NavigationAction.EXIT_TO_LAUNCHER
            return True
        return False

    def update_user_interface_elements(self, card_user_interface: dict[str, Any]) -> None:
        old_cry_rect = self.cry_play_rect
        old_text_to_speech_rect = self.text_to_speech_play_rect
        old_evolution_hits = self.evolution_hits
        old_asset_pills = self.asset_pills
        self.card_user_interface = card_user_interface
        self.cry_play_rect = card_user_interface.get("play_rect")
        self.text_to_speech_play_rect = card_user_interface.get("tts_play_rect")
        self.evolution_hits = card_user_interface.get("evo_hits", [])
        self.asset_pills = card_user_interface.get("asset_pills", [])
        if (
            self.cry_play_rect != old_cry_rect
            or self.text_to_speech_play_rect != old_text_to_speech_rect
            or self.evolution_hits != old_evolution_hits
            or self.asset_pills != old_asset_pills
        ):
            self.update_focus_elements()

    def run_modal(self) -> NavigationAction:
        background = self.screen.copy()
        screen_rect = self.screen.get_rect()
        clock = pygame.time.Clock()

        def on_species_changed(new_species: str) -> None:
            self.species = new_species
            nonlocal first_frame
            first_frame = True

        self.set_species_change_callback(on_species_changed)
        first_frame = True
        while True:
            self.screen.blit(background, (0, 0))
            # Always use standardized behavior (no flags)
            card_user_interface = self.render_card_overlay(screen_rect)
            self.update_user_interface_elements(card_user_interface)
            if first_frame:
                self.update_focus_elements()
                first_frame = False
            self.draw_focus_indicator(self.screen)
            pygame.display.flip()
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return NavigationAction.EXIT_TO_LAUNCHER
                if event.type == pygame.KEYDOWN:
                    result = self.focus_manager.handle_key_event(event)
                    if result.action in (
                        NavigationAction.EXIT_TO_PARENT,
                        NavigationAction.EXIT_TO_LAUNCHER,
                    ):
                        self._cleanup()
                        return result.action
            clock.tick(60)

    def draw_focus_indicator(self, screen: pygame.Surface) -> None:
        if is_any_audio_playing():
            return
        super().draw_focus_indicator(screen)

    def render_card_overlay(self, screen_rect: pygame.Rect) -> dict[str, object]:
        """Render the Pokemon card overlay."""
        # Get the currently selected main image
        current_main_image = self.get_current_main_image()

        # Get the base card UI, passing our own caches instead of using globals
        card_ui = render_pokemon_card_overlay(
            self.screen,
            screen_rect,
            self.species,
            custom_main_image=current_main_image,
            overlay_cache=self.overlay_cache,
            scaled_image_cache=self.scaled_image_cache,
            cry_play_buttons=self.cry_play_buttons,
            text_to_speech_play_buttons=self.text_to_speech_play_buttons,
            sprite_gray_cache=self.sprite_gray_cache,
            pokedex_entry_cache=self.entry_choice_cache,
        )
        
        # Render asset pills if hunt assets are available
        if self.hunt_assets:
            main_image_rect = card_ui.get("main_image_rect")
            if main_image_rect:
                # Create area for asset pills below Pokemon image on left side
                pills_area = pygame.Rect(
                    main_image_rect.left, main_image_rect.bottom + 8, main_image_rect.width, 30
                )
                self.asset_pills = self.render_asset_selection_pills(self.screen, pills_area)
                card_ui["asset_pills"] = self.asset_pills

        return card_ui

    def _map_key_to_dirname(self, key: str) -> str | None:
        """Map evolution key to species directory name."""
        base = _images_root()
        for candidate in (key, key.replace("-", "_"), key.replace("_", "-"), key.replace("-", "")):
            if (base / candidate).is_dir():
                return candidate
        index = self._build_directory_index()
        return index.get(self._canonical_key(key))

    def _build_directory_index(self) -> dict[str, str]:
        """Build index of directory names for species lookup."""
        if self.directory_index is not None:
            return self.directory_index
        base = _images_root()
        index: dict[str, str] = {}
        try:
            for path in base.iterdir():
                if not path.is_dir():
                    continue
                key = self._canonical_key(path.name)
                index.setdefault(key, path.name)
        except Exception:
            pass
        self.directory_index = index
        return index

    def _canonical_key(self, name: str) -> str:
        """Convert name to canonical key format."""
        string = name.lower().replace("_", "-")
        string = string.replace("♀", "-f").replace("♂", "-m")
        string = re.sub(r"[^a-z0-9-]", "-", string).strip("-")
        return string

    def load_hunt_assets(self) -> list[str]:
        """Load available hunt assets for the current species."""
        hunt_assets_path = os.path.join(str(_images_root()), self.species, "hunt_assets")
        if not os.path.exists(hunt_assets_path):
            return []

        # Filter for image files only
        assets = []
        for filename in os.listdir(hunt_assets_path):
            if filename.lower().endswith((".png", ".gif", ".jpg", ".jpeg")):
                assets.append(filename)

        return sorted(assets)  # Sort for consistent order

    def render_asset_selection_pills(
        self, screen: pygame.Surface, area: pygame.Rect
    ) -> list[tuple[str, pygame.Rect]]:
        """Render pills for selecting different asset images (paginated)."""
        if not self.hunt_assets:
            return []

        pills = []
        pill_height = 24
        padding_x = 8
        gap_x = 6
        font = pygame.font.Font(None, 18)
        
        # Get assets for current page
        page_assets = self.get_current_page_assets()
        
        # Calculate pill layout
        current_x = area.left
        pill_y = area.top + (area.height - pill_height) // 2

        # Render pills for current page only
        for asset_name in page_assets:
            if asset_name == "main":
                label = "MAIN"
                is_selected = self.current_asset_index == 0
            else:
                label = self._create_asset_label(asset_name)
                is_selected = (
                    self.current_asset_index > 0 and 
                    self.current_asset_index - 1 < len(self.hunt_assets) and
                    self.hunt_assets[self.current_asset_index - 1] == asset_name
                )

            label_width = font.size(label)[0] + padding_x * 2

            # Check if pill fits in area
            if current_x + label_width > area.right:
                break

            pill_rect = pygame.Rect(current_x, pill_y, label_width, pill_height)

            # Color based on selection
            color = (80, 160, 240) if is_selected else (120, 120, 125)

            draw_pill(screen, pill_rect, color, color, label, font)
            pills.append((asset_name, pill_rect))
            current_x = pill_rect.right + gap_x

        # Show page indicator if multiple pages
        if self.get_total_pages() > 1:
            page_text = f"Page {self.current_pill_page + 1}/{self.get_total_pages()}"
            page_font = pygame.font.Font(None, 16)
            page_color = (180, 180, 180)
            page_surface = page_font.render(page_text, True, page_color)
            page_rect = page_surface.get_rect()
            page_rect.right = area.right
            page_rect.centery = pill_y + pill_height // 2
            screen.blit(page_surface, page_rect)

        return pills

    def _create_asset_label(self, filename: str) -> str:
        """Create a short label from asset filename."""
        import os
        # Remove extension and species name prefix
        name = os.path.splitext(filename)[0]
        name = name.replace(f"{self.species}_", "").replace(self.species, "")
        
        # Clean up common suffixes/prefixes
        name = name.lstrip("_").rstrip("_")
        
        if not name:
            return "ALT"
        
        # Split by underscores to get components
        parts = name.split("_")
        
        # Strategy: Create more specific labels by including more context
        if len(parts) == 1:
            # Single part - use first 6 chars
            return parts[0].upper()[:6]
        elif len(parts) == 2:
            # Two parts - prioritize meaningful combinations
            first, second = parts[0], parts[1]
            if second.lower() == "shiny":
                # For shiny variants, include first part for context
                return (first[:4] + "SH").upper()
            else:
                # Use first 3 chars of each
                return (first[:3] + second[:3]).upper()
        else:
            # Multiple parts - prioritize meaningful combinations
            # Check if last part is "shiny" - if so, combine with previous parts
            if parts[-1].lower() == "shiny":
                # Shiny variant - combine other parts + "SH"
                other_parts = parts[:-1]
                if len(other_parts) == 1:
                    return (other_parts[0][:4] + "SH").upper()
                else:
                    # Multiple other parts - take 2 chars from each
                    combined = "".join(part[:2] for part in other_parts[:2])
                    return (combined + "SH").upper()[:6]
            else:
                # Non-shiny variant - use first 2 chars of each part
                result_parts = []
                for part in parts:
                    result_parts.append(part[:2].upper())
                
                # Join and limit to 6 chars
                return "".join(result_parts)[:6]

    def _select_asset(self, asset_name: str) -> None:
        """Switch to the selected asset."""
        if asset_name == "main":
            self.current_asset_index = 0
        else:
            import contextlib
            with contextlib.suppress(ValueError):
                self.current_asset_index = self.hunt_assets.index(asset_name) + 1

    def get_current_page_assets(self) -> list[str]:
        """Get the assets for the current page."""
        start_index = self.current_pill_page * self.pills_per_page
        end_index = start_index + self.pills_per_page
        
        # Always include main asset + hunt assets for this page
        page_assets = ["main"]
        
        # Add hunt assets for this page
        if start_index < len(self.hunt_assets):
            page_hunt_assets = self.hunt_assets[start_index:end_index]
            page_assets.extend(page_hunt_assets)
        
        return page_assets

    def get_total_pages(self) -> int:
        """Get total number of pages needed for all hunt assets."""
        if not self.hunt_assets:
            return 1
        return (len(self.hunt_assets) + self.pills_per_page - 1) // self.pills_per_page

    def next_pill_page(self) -> None:
        """Move to next page of pills."""
        total_pages = self.get_total_pages()
        self.current_pill_page = (self.current_pill_page + 1) % total_pages

    def previous_pill_page(self) -> None:
        """Move to previous page of pills."""
        total_pages = self.get_total_pages()
        self.current_pill_page = (self.current_pill_page - 1) % total_pages

    def render_variant_navigation(
        self, screen: pygame.Surface, area: pygame.Rect
    ) -> tuple[pygame.Rect | None, pygame.Rect | None, pygame.Rect | None]:
        """Render arrow-based variant navigation UI similar to ID card voice selector."""
        if not self.hunt_assets:
            return None, None, None
            
        # UI metrics
        arrow_height = int(area.height * 0.8)
        gap = 8
        
        # Get arrow icons
        right_arrow = _get_variant_arrow_icon(arrow_height)
        left_arrow = (
            pygame.transform.flip(right_arrow, True, False) if right_arrow is not None else None
        )
        
        # Position arrows
        arrow_y = area.top + (area.height - arrow_height) // 2
        left_rect = pygame.Rect(area.left, arrow_y, arrow_height, arrow_height)
        right_rect = pygame.Rect(area.right - arrow_height, arrow_y, arrow_height, arrow_height)
        
        # Draw arrows or fallback glyphs
        if left_arrow is not None and right_arrow is not None:
            screen.blit(left_arrow, left_rect)
            screen.blit(right_arrow, right_rect)
        else:
            # Fallback to text glyphs
            glyph_font = pygame.font.Font(None, arrow_height)
            screen.blit(glyph_font.render("<", True, (40, 90, 180)), left_rect.topleft)
            screen.blit(glyph_font.render(">", True, (40, 90, 180)), right_rect.topleft)
        
        # Display current variant name in the center
        text_left = left_rect.right + gap
        text_right = right_rect.left - gap
        display_rect = pygame.Rect(text_left, area.top, text_right - text_left, area.height)
        
        # Get current variant name
        current_variant_name = self.get_current_variant_name()
        
        # Render variant name
        font = pygame.font.Font(None, 24)
        text_color = (255, 255, 255)
        text_surface = font.render(current_variant_name, True, text_color)
        text_rect = text_surface.get_rect(center=display_rect.center)
        screen.blit(text_surface, text_rect)
        
        return left_rect, right_rect, display_rect
    
    def get_current_variant_name(self) -> str:
        """Get the display name for the current variant."""
        if self.current_variant_index == 0:
            return "MAIN"
        elif self.current_variant_index - 1 < len(self.hunt_assets):
            asset_filename = self.hunt_assets[self.current_variant_index - 1]
            return self._create_asset_label(asset_filename)
        else:
            return "UNKNOWN"
    
    def next_variant(self) -> None:
        """Navigate to the next variant."""
        total_variants = len(self.hunt_assets) + 1  # +1 for main
        if total_variants > 1:
            self.current_variant_index = (self.current_variant_index + 1) % total_variants
            self.current_asset_index = self.current_variant_index  # Keep in sync
    
    def previous_variant(self) -> None:
        """Navigate to the previous variant."""
        total_variants = len(self.hunt_assets) + 1  # +1 for main
        if total_variants > 1:
            self.current_variant_index = (self.current_variant_index - 1) % total_variants
            self.current_asset_index = self.current_variant_index  # Keep in sync

    def get_current_main_image(self) -> pygame.Surface | None:
        """Get the currently selected main image (main.png or hunt asset)."""
        if self.current_asset_index == 0:
            # Use main.png
            main_image, _ = load_card_images(self.species)
            return main_image
        else:
            # Use hunt asset
            if self.current_asset_index - 1 < len(self.hunt_assets):
                asset_filename = self.hunt_assets[self.current_asset_index - 1]

                # Check cache first
                if asset_filename in self.hunt_assets_cache:
                    cached_data = self.hunt_assets_cache[asset_filename]
                    if isinstance(cached_data, AnimatedGif):
                        # Return current frame for animated GIF
                        return cached_data.get_current_frame()
                    else:
                        # Return static surface
                        return cached_data

                asset_path = os.path.join(
                    str(_images_root()), self.species, "hunt_assets", asset_filename
                )
                try:
                    # Use centralized GIF loading from image_util
                    loaded_data = load_animated_gif(asset_path)
                    self.hunt_assets_cache[asset_filename] = loaded_data
                    
                    if isinstance(loaded_data, AnimatedGif):
                        return loaded_data.get_current_frame()
                    elif isinstance(loaded_data, pygame.Surface):
                        return loaded_data
                    else:
                        return None
                except Exception:
                    self.hunt_assets_cache[asset_filename] = None
        return None





    def _select_asset(self, asset_name: str) -> None:
        """Switch to the selected asset."""
        if asset_name == "main":
            self.current_asset_index = 0
        else:
            with contextlib.suppress(ValueError):
                self.current_asset_index = self.hunt_assets.index(asset_name) + 1
                
        # Reset GIF animation if switching to a GIF
        if asset_name != "main" and asset_name in self.hunt_assets_cache:
            cached_data = self.hunt_assets_cache[asset_name]
            if isinstance(cached_data, AnimatedGif):
                cached_data.reset()

    def _cleanup(self) -> None:
        """Clean up resources when card is closed."""
        self.last_spoken_species = None
        with contextlib.suppress(Exception):
            stop_speech(0)
        stop_named_channel("cry")

        # Clear our instance caches
        self.cry_play_buttons.clear()
        self.text_to_speech_play_buttons.clear()
        self.hunt_assets_cache.clear()
        self.image_cache.clear()
        self.sprite_cache.clear()
        self.sprite_gray_cache.clear()
        self.overlay_cache.clear()
        self.scaled_image_cache.clear()
        self.arrow_cache.clear()
