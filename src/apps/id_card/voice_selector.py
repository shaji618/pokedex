from functools import lru_cache
from pathlib import Path

import pygame

from src.utils.image_util import load_image_from_resources
from src.utils.path_util import project_root
from src.utils.play_button_util import PlayButton
from src.utils.tts_util import (
    get_selected_voice,
    get_voice_locale,
    is_speaking,
    set_selected_voice,
    speak_text_async,
    stop_speech,
)
from src.utils.user_config import NAME


VOICE_SAMPLE_TEXT = f"Hello, {NAME}! Welcome to your Pokédex!"


def _get_voice_play_button(preview_voice: str | None = None) -> PlayButton:
    def play_voice_sample_internal() -> None:
        from src.utils.tts_util import _tts_state

        target_voice = preview_voice if preview_voice is not None else get_selected_voice()
        if target_voice is None:
            return
        _tts_state.is_pending = True
        original_voice = get_selected_voice()
        if target_voice != original_voice:
            set_selected_voice(target_voice)
        try:
            from src.utils.tts_util import play_cached_sample_audio

            if not play_cached_sample_audio():
                speak_text_async(VOICE_SAMPLE_TEXT)
            else:
                _tts_state.is_pending = False
        finally:
            if original_voice != target_voice and original_voice is not None:
                set_selected_voice(original_voice)

    return PlayButton(play_voice_sample_internal, is_audio_playing=is_speaking, timeout_seconds=2.0)


def _format_voice_label(name: str | None) -> str:
    if not name:
        return "-"
    voice_part = name.split("/", 1)[1] if "/" in name else name
    label = voice_part.replace("_", " ")
    return label.title()


@lru_cache(maxsize=1)
def _load_arrow_base() -> pygame.Surface | None:
    surf = load_image_from_resources("src.utils.media", "arrow.png")
    if surf is None:
        return None
    return pygame.transform.rotate(surf, -90)


def _get_arrow_icon(target_height: int) -> pygame.Surface | None:
    if target_height <= 0:
        return None
    base = _load_arrow_base()
    if base is None:
        return None
    bw, bh = base.get_size()
    scale = target_height / max(1, bh)
    new_size = (max(1, int(bw * scale)), max(1, int(bh * scale)))
    return pygame.transform.smoothscale(base, new_size)


@lru_cache(maxsize=1)
def _load_play_button_base() -> pygame.Surface | None:
    surf = load_image_from_resources("utils.media", "play_button.png")
    return surf


def _get_play_button_icon(target_height: int) -> pygame.Surface | None:
    if target_height <= 0:
        return None
    base = _load_play_button_base()
    if base is None:
        return None
    bw, bh = base.get_size()
    scale = target_height / max(1, bh)
    new_size = (max(1, int(bw * scale)), max(1, int(bh * scale)))
    return pygame.transform.smoothscale(base, new_size)


@lru_cache(maxsize=8)
def _load_flag_base(locale: str) -> pygame.Surface | None:
    try:
        locale_str = (locale or "").strip()
        if not locale_str:
            return None
        root = Path(str(project_root()))
        locale_underscore = locale_str.replace("-", "_")
        locale_dash = locale_str.replace("_", "-")
        voice_dirs = [root / "voices" / locale_underscore, root / "voices" / locale_dash]
        for directory in voice_dirs:
            try:
                path = directory / "flag.png"
                if path.exists():
                    from src.utils.image_util import load_image_safe

                    return load_image_safe(str(path))
            except Exception:
                continue
        return None
    except Exception:
        return None


def _get_flag_icon(locale: str | None, target_height: int) -> pygame.Surface | None:
    if not locale or target_height <= 0:
        return None
    base = _load_flag_base(locale)
    if base is None:
        return None
    base_width, base_height = base.get_size()
    scale = target_height / max(1, base_height)
    new_size = (max(1, int(base_width * scale)), max(1, int(base_height * scale)))
    return pygame.transform.smoothscale(base, new_size)


def _render_text_fit_single_line(
    text: str,
    max_width: int,
    max_height: int,
    *,
    base_size: int,
    min_size: int = 10,
    color: tuple[int, int, int] = (10, 10, 20),
) -> pygame.Surface:
    size = base_size
    best = None
    while size >= min_size:
        font = pygame.font.Font(None, size)
        surface = font.render(text, True, color)
        if surface.get_width() <= max_width and surface.get_height() <= max_height:
            return surface
        best = surface
        size -= 1

    return best if best is not None else pygame.font.Font(None, min_size).render(text, True, color)


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


def stop_voice_sample() -> None:
    if is_speaking():
        stop_speech(fade_ms=200)


def draw_voice_selector(
    screen: pygame.Surface,
    rect: pygame.Rect,
    label_font: pygame.font.Font,
    value_font: pygame.font.Font,
    current_voice: str | None,
    area_height: int,
    show_save_feedback: bool = False,
    is_saved_voice: bool = False,
) -> tuple[pygame.Rect, pygame.Rect, pygame.Rect]:
    inner_margin, gap, rule_thickness, _row_height = _compute_cell_metrics(
        rect.width, area_height, label_font, value_font
    )
    label_color = (20, 20, 30)
    label_surf = label_font.render("VOICE", True, label_color)
    label_x = rect.left + inner_margin
    label_y = rect.top + inner_margin
    play_button_h = int(label_font.get_height() * 0.8)
    label_w = label_surf.get_width()
    play_x = label_x + label_w + gap
    play_y = label_y + (label_font.get_height() - play_button_h) // 2
    play_rect = pygame.Rect(play_x, play_y, play_button_h, play_button_h)
    screen.blit(label_surf, (label_x, label_y))
    play_button = _get_voice_play_button(current_voice)
    play_button.draw(screen, play_rect, target_height=play_button_h)
    value_y = label_y + label_font.get_height() + gap
    baseline_h = value_font.get_height()
    arrow_h = int(baseline_h * 0.9)
    right_arrow = _get_arrow_icon(arrow_h)
    left_arrow = (
        pygame.transform.flip(right_arrow, True, False) if right_arrow is not None else None
    )
    ar_y = value_y + (baseline_h - arrow_h) // 2
    left_rect = pygame.Rect(rect.left + inner_margin, ar_y, arrow_h, arrow_h)
    right_rect = pygame.Rect(rect.right - inner_margin - arrow_h, ar_y, arrow_h, arrow_h)
    if left_arrow is not None:
        screen.blit(left_arrow, left_rect)
        screen.blit(right_arrow, right_rect)
    else:
        glyph_font = pygame.font.Font(None, int(baseline_h))
        screen.blit(glyph_font.render("<", True, (40, 90, 180)), left_rect.topleft)
        screen.blit(glyph_font.render(">", True, (40, 90, 180)), right_rect.topleft)
    text_left = left_rect.right + gap
    text_right = right_rect.left - gap
    max_w_initial = max(10, text_right - text_left)
    voice_label = _format_voice_label(current_voice)
    if is_saved_voice:
        text = voice_label + " ✓" if voice_label else "- ✓"
        text_color = (34, 139, 34)
    else:
        text = voice_label if voice_label else "-"
        text_color = (10, 10, 20)
    fitted = _render_text_fit_single_line(
        text, max_w_initial, baseline_h, base_size=value_font.get_height(), color=text_color
    )
    center_y = value_y + baseline_h // 2
    loc = get_voice_locale(current_voice) if current_voice else None
    flag_icon = _get_flag_icon(loc, baseline_h)
    if flag_icon is not None:
        frect = flag_icon.get_rect()
        frect.left = text_left
        frect.centery = center_y
        screen.blit(flag_icon, frect)
        text_left = frect.right + max(6, gap // 2)
        max_w = max(10, text_right - text_left)
        if fitted.get_width() > max_w:
            fitted = _render_text_fit_single_line(
                text, max_w, baseline_h, base_size=value_font.get_height(), color=text_color
            )
    trect = fitted.get_rect()
    trect.left = text_left
    trect.centery = center_y
    screen.blit(fitted, trect)
    rule_left = rect.left + inner_margin
    rule_right = rect.right - inner_margin
    rule_y = value_y + baseline_h + gap
    pygame.draw.line(
        screen, (40, 90, 180), (rule_left, rule_y), (rule_right, rule_y), width=rule_thickness
    )
    return left_rect, right_rect, play_rect


def handle_voice_selector_click(
    click_pos: tuple[int, int],
    left_rect: pygame.Rect | None,
    right_rect: pygame.Rect | None,
    play_rect: pygame.Rect | None,
    voices: list[str],
    current_index: int,
) -> tuple[int, str | None]:
    if not voices:
        return current_index, None
    mx, my = click_pos
    if play_rect and play_rect.collidepoint(mx, my):
        preview_voice = voices[current_index] if 0 <= current_index < len(voices) else None
        play_button = _get_voice_play_button(preview_voice)
        if play_button.handle_click():
            return current_index, "play"
        else:
            return current_index, "disabled"
    if left_rect and left_rect.collidepoint(mx, my):
        stop_voice_sample()
        new_index = (current_index - 1) % len(voices)
        return new_index, "prev"
    if right_rect and right_rect.collidepoint(mx, my):
        stop_voice_sample()
        new_index = (current_index + 1) % len(voices)
        return new_index, "next"
    return current_index, None


def get_voice_index(voices: list[str], current_voice: str | None) -> int:
    if not voices or current_voice is None:
        return 0
    try:
        return voices.index(current_voice)
    except ValueError:
        return 0
