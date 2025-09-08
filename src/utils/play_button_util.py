import time
from collections.abc import Callable

import pygame

from src.utils.audio_util import is_named_channel_busy, play_pokemon_cry
from src.utils.path_util import project_root
from src.utils.surface_util import grayscale_surface
from src.utils.tts_util import (
    _tts_state,
    get_selected_voice,
    is_speaking,
    set_selected_voice,
    speak_pokemon_description,
    speak_text_async,
)


def is_any_audio_playing() -> bool:
    try:
        if is_speaking():
            return True
        if is_named_channel_busy("cry"):
            return True
        return any(is_named_channel_busy(channel) for channel in ["shutter", "voice_sample"])
    except Exception:
        return False


class PlayButton:
    def __init__(
        self,
        audio_callback: Callable[[], None],
        *,
        is_audio_playing: Callable[[], bool] | None = None,
        timeout_seconds: float = 3.0,
    ) -> None:
        self._audio_callback = audio_callback
        self._is_audio_playing = is_audio_playing or is_speaking
        self._timeout_seconds = timeout_seconds
        self._pending = False
        self._pending_timestamp = 0.0
        self._icon_cache: dict[int, pygame.Surface] = {}
        self._base_icon: pygame.Surface | None = None

    def _load_base_icon(self) -> pygame.Surface | None:
        if self._base_icon is not None:
            return self._base_icon
        try:
            import os

            icon_path = os.path.join(
                str(project_root()), "src", "utils", "media", "play_button.png"
            )
            if os.path.exists(icon_path):
                self._base_icon = pygame.image.load(icon_path).convert_alpha()
        except Exception:
            pass
        return self._base_icon

    def _get_scaled_icon(self, target_height: int) -> pygame.Surface | None:
        if target_height <= 0:
            return None
        if target_height in self._icon_cache:
            return self._icon_cache[target_height]
        base = self._load_base_icon()
        if base is None:
            return None
        bw, bh = base.get_size()
        scale = target_height / max(1, bh)
        new_size = (max(1, int(bw * scale)), max(1, int(bh * scale)))
        scaled = pygame.transform.smoothscale(base, new_size)
        self._icon_cache[target_height] = scaled
        return scaled

    def _update_pending_state(self) -> None:
        if self._is_audio_playing() and self._pending:
            self._pending = False
        if self._pending:
            elapsed = time.time() - self._pending_timestamp
            if elapsed > self._timeout_seconds:
                self._pending = False

    def is_disabled(self) -> bool:
        self._update_pending_state()
        return self._pending or self._is_audio_playing() or is_any_audio_playing()

    def handle_click(self) -> bool:
        if self.is_disabled():
            return False
        self._pending = True
        self._pending_timestamp = time.time()
        try:
            self._audio_callback()
            return True
        except Exception:
            self._pending = False
            raise

    def draw(
        self, screen: pygame.Surface, rect: pygame.Rect, *, target_height: int | None = None
    ) -> None:
        if target_height is None:
            target_height = rect.height
        icon = self._get_scaled_icon(target_height)
        if icon is not None:
            disabled = self.is_disabled()
            draw_icon = grayscale_surface(icon) if disabled else icon
            icon_rect = draw_icon.get_rect(center=rect.center)
            screen.blit(draw_icon, icon_rect)
        else:
            disabled = self.is_disabled()
            circle_color = (20, 45, 90) if disabled else (40, 90, 180)
            triangle_color = (128, 128, 128) if disabled else (255, 255, 255)
            radius = min(rect.width, rect.height) // 2
            pygame.draw.circle(screen, circle_color, rect.center, radius)
            triangle_size = radius // 2
            cx, cy = rect.center
            points = [
                (cx - triangle_size // 2, cy - triangle_size // 2),
                (cx - triangle_size // 2, cy + triangle_size // 2),
                (cx + triangle_size // 2, cy),
            ]
            pygame.draw.polygon(screen, triangle_color, points)


def create_tts_play_button(text: str, *, voice: str | None = None) -> PlayButton:
    def play_tts() -> None:
        _tts_state.is_pending = True
        if voice is not None:
            get_selected_voice()
            set_selected_voice(voice)
        try:
            speak_text_async(text)
        finally:
            pass

    return PlayButton(play_tts, is_audio_playing=is_speaking)


def create_pokemon_cry_play_button(species: str) -> PlayButton:
    def play_cry() -> None:
        play_pokemon_cry(species, volume=0.9)

    def is_cry_playing() -> bool:
        try:
            return is_named_channel_busy("cry")
        except Exception:
            return False

    return PlayButton(play_cry, is_audio_playing=is_cry_playing)


def create_pokemon_description_play_button(species: str, meta: dict) -> PlayButton:
    def play_description() -> None:
        import random

        _tts_state.is_pending = True
        description = str(meta.get("description", "")).strip()
        entries = meta.get("pokedex_entries") or []
        entry = random.choice(entries).strip() if entries else ""
        speak_pokemon_description(description, entry, meta)

    return PlayButton(play_description, is_audio_playing=is_speaking)
