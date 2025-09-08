from __future__ import annotations

import contextlib
import os
from enum import Enum

import pygame

from src.utils.pokemon_image_util import images_root


class AudioChannel(Enum):
    SHUTTER = "shutter"
    RELEASE = "release"
    ACCEPTED = "accepted"
    CRY = "cry"


def init_mixer_if_needed() -> bool:
    try:
        if not pygame.mixer.get_init():
            with contextlib.suppress(Exception):
                pygame.mixer.pre_init(22050, -16, 1, 512)
            pygame.mixer.init()
            with contextlib.suppress(Exception):
                pygame.mixer.set_number_channels(16)
        return True
    except Exception:
        return False


def play_music_once(path: str, *, volume: float = 0.6) -> bool:
    if not path or not os.path.exists(path):
        return False
    if not init_mixer_if_needed():
        return False
    try:
        pygame.mixer.music.set_volume(max(0.0, min(1.0, volume)))
        pygame.mixer.music.load(path)
        pygame.mixer.music.play(0)
        return True
    except Exception:
        return False


def play_music_loop(path: str, *, volume: float = 0.6) -> bool:
    if not path or not os.path.exists(path):
        return False
    if not init_mixer_if_needed():
        return False
    try:
        pygame.mixer.music.set_volume(max(0.0, min(1.0, volume)))
        pygame.mixer.music.load(path)
        pygame.mixer.music.play(-1)
        return True
    except Exception:
        return False


def fadeout_music(ms: int = 300) -> None:
    try:
        if pygame.mixer.get_init():
            pygame.mixer.music.fadeout(ms)
    except Exception:
        pass


def stop_music() -> None:
    try:
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()
            pygame.mixer.quit()
    except Exception:
        pass


_sound_cache: dict[str, pygame.mixer.Sound] = {}


def _get_sound(path: str) -> pygame.mixer.Sound | None:
    try:
        if path in _sound_cache:
            return _sound_cache[path]
        if not init_mixer_if_needed() or not os.path.exists(path):
            return None
        snd = pygame.mixer.Sound(path)
        _sound_cache[path] = snd
        return snd
    except Exception:
        return None


_NAMED_CHANNELS = {
    AudioChannel.SHUTTER.value: 1,
    AudioChannel.RELEASE.value: 2,
    AudioChannel.ACCEPTED.value: 3,
    AudioChannel.CRY.value: 4,
}


def play_sfx(
    path: str,
    *,
    volume: float = 0.9,
    channel_name: str | AudioChannel | None = None,
    restart_if_busy: bool = False,
) -> bool:
    snd = _get_sound(path)
    if snd is None:
        return False
    try:
        snd.set_volume(max(0.0, min(1.0, volume)))
        ch = None
        if channel_name:
            channel_key = (
                channel_name.value if isinstance(channel_name, AudioChannel) else channel_name
            )
            if channel_key in _NAMED_CHANNELS:
                ch = pygame.mixer.Channel(_NAMED_CHANNELS[channel_key])
                if ch.get_busy():
                    if restart_if_busy:
                        ch.stop()
                    else:
                        return True
        if ch is None:
            ch = pygame.mixer.find_channel(True)
        ch.play(snd)
        return True
    except Exception:
        return False


def stop_all_sfx() -> None:
    try:
        if pygame.mixer.get_init():
            pygame.mixer.stop()
    except Exception:
        pass


def stop_named_channel(channel_name: str | AudioChannel) -> None:
    try:
        if pygame.mixer.get_init():
            channel_key = (
                channel_name.value if isinstance(channel_name, AudioChannel) else channel_name
            )
            if channel_key in _NAMED_CHANNELS:
                ch = pygame.mixer.Channel(_NAMED_CHANNELS[channel_key])
                ch.stop()
    except Exception:
        pass


def is_named_channel_busy(channel_name: str | AudioChannel) -> bool:
    try:
        if not pygame.mixer.get_init():
            return False
        channel_key = channel_name.value if isinstance(channel_name, AudioChannel) else channel_name
        if channel_key not in _NAMED_CHANNELS:
            return False
        ch = pygame.mixer.Channel(_NAMED_CHANNELS[channel_key])
        return ch.get_busy()
    except Exception:
        return False


def pokemon_cry_exists(species: str) -> bool:
    species_directory = images_root() / species
    return any((species_directory / name).exists() for name in ("anime_cry.wav", "anime_cry.mp3"))


def play_pokemon_cry(species: str, *, volume: float = 0.8) -> bool:
    species_directory = images_root() / species
    for name in ("anime_cry.wav", "anime_cry.mp3"):
        cry_path = species_directory / name
        if cry_path.exists():
            return play_sfx(
                str(cry_path), volume=volume, channel_name=AudioChannel.CRY, restart_if_busy=True
            )
    return False
