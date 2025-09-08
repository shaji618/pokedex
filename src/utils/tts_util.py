from __future__ import annotations

import array
import contextlib
import io
import json
import os
import subprocess
import tempfile
import threading
import wave
from pathlib import Path

import pygame

from src.utils.audio_util import init_mixer_if_needed
from src.utils.path_util import project_root
from src.utils.user_config import NAME


def _ensure_mixer() -> None:
    init_mixer_if_needed()


class TTSState:
    def __init__(self) -> None:
        self.playback_channel: pygame.mixer.Channel | None = None
        self.voice = None
        self.voice_sample_rate: int | None = None
        self.selected_voice_name: str | None = None
        self.selected_voice_directory: Path | None = None
        self.sample_audio_cache: dict[str, bytes] = {}
        self.is_pending: bool = False
        # Performance optimization: cache voice models and directory scan
        self.voice_model_cache: dict[
            str, tuple[object, int]
        ] = {}  # voice_name -> (model, sample_rate)
        self.voice_directories_cache: dict[str, Path] | None = None


_tts_state = TTSState()
FADE_IN_MS_DEFAULT: int = 120
PRE_SILENCE_MS_DEFAULT: int = 0


def _play_wav_bytes(data: bytes) -> None:
    _ensure_mixer()
    sound = pygame.mixer.Sound(file=io.BytesIO(data))
    _tts_state.playback_channel = pygame.mixer.find_channel(True)
    _tts_state.playback_channel.play(sound)
    _tts_state.is_pending = False


def _discover_voice_directories() -> list[tuple[str, Path]]:
    # Use cached result if available
    if _tts_state.voice_directories_cache is not None:
        return list(_tts_state.voice_directories_cache.items())

    try:
        root = Path(str(project_root()))
        voices_directory = root / "voices"
        results: list[tuple[str, Path]] = []
        if not voices_directory.exists():
            _tts_state.voice_directories_cache = {}
            return results
        for child in voices_directory.iterdir():
            if not child.is_dir():
                continue
            try:
                if any(p.is_file() and p.suffix == ".onnx" for p in child.iterdir()):
                    results.append((child.name, child))
                    continue
            except Exception:
                pass
            try:
                for sub in child.iterdir():
                    if sub.is_dir():
                        try:
                            if any(p.is_file() and p.suffix == ".onnx" for p in sub.iterdir()):
                                voice_name = f"{child.name}/{sub.name}"
                                results.append((voice_name, sub))
                        except Exception:
                            continue
            except Exception:
                continue
        seen: set[str] = set()
        deduped: list[tuple[str, Path]] = []
        for name, path in results:
            if name in seen:
                continue
            seen.add(name)
            deduped.append((name, path))
        deduped.sort(key=lambda t: t[0].split("/")[-1].lower())

        # Cache the results
        _tts_state.voice_directories_cache = dict(deduped)
        return deduped
    except Exception:
        _tts_state.voice_directories_cache = {}
        return []


def list_available_voices() -> list[str]:
    try:
        return [name for name, _ in _discover_voice_directories()]
    except Exception:
        return []


def get_selected_voice() -> str | None:
    return _tts_state.selected_voice_name


def set_selected_voice(name: str | None) -> bool:
    if name is None:
        _tts_state.selected_voice_name = None
        _tts_state.selected_voice_directory = None
        _tts_state.voice = None
        _tts_state.voice_sample_rate = None
    else:
        mapping = dict(_discover_voice_directories())
        if name not in mapping:
            return False

        # If voice is already selected, don't reload
        if _tts_state.selected_voice_name == name:
            return True

        _tts_state.selected_voice_name = name
        _tts_state.selected_voice_directory = mapping[name]

        # Check if voice model is cached
        if name in _tts_state.voice_model_cache:
            _tts_state.voice, _tts_state.voice_sample_rate = _tts_state.voice_model_cache[name]
            if hasattr(_tts_state.voice, "_loaded_for_voice"):
                _tts_state.voice._loaded_for_voice = name
        else:
            # Only load voice model when actually needed, not during voice browsing
            _tts_state.voice = None
            _tts_state.voice_sample_rate = None

        # Only presynthesize if we have a cached voice or if explicitly requested
        if _tts_state.voice is not None:
            with contextlib.suppress(Exception):
                _presynthesize_sample_audio()
    return True


def _presynthesize_sample_audio() -> None:
    if _tts_state.voice is None or _tts_state.selected_voice_name is None:
        return

    sample_text = f"Hello, {NAME}! Welcome to your Pokédex!"
    try:
        audio_bytes: bytes = _tts_state.voice.synthesize(sample_text)
        if _tts_state.voice_sample_rate:
            audio_bytes = _apply_fade_in(audio_bytes, _tts_state.voice_sample_rate)
        _tts_state.sample_audio_cache[_tts_state.selected_voice_name] = audio_bytes
    except Exception:
        pass


def play_cached_sample_audio() -> bool:
    if _tts_state.selected_voice_name is None:
        return False
    cached_audio = _tts_state.sample_audio_cache.get(_tts_state.selected_voice_name)
    if cached_audio:
        try:
            _play_wav_bytes(cached_audio)
            return True
        except Exception:
            _tts_state.sample_audio_cache.pop(_tts_state.selected_voice_name, None)
    return False


def get_voice_locale(name: str) -> str | None:
    try:
        mapping = dict(_discover_voice_directories())
        path = mapping.get(name)
        if path is None:
            return None
        parent = path.parent
        if parent.name and parent.parent and parent.parent.name == "voices":
            if len(parent.name) == 5 and parent.name[2] == "_":
                return parent.name
        for p in path.iterdir():
            try:
                if p.is_file() and p.suffix == ".onnx":
                    stem = p.stem
                    if stem.startswith("en_GB-"):
                        return "en_GB"
                    if stem.startswith("en_US-"):
                        return "en_US"
            except Exception:
                continue
        return None
    except Exception:
        return None


def _voice_model_paths() -> tuple[Path, Path | None]:
    root = Path(str(project_root()))
    voices_directory = root / "voices"
    if _tts_state.selected_voice_directory is not None:
        base_directory = _tts_state.selected_voice_directory
    else:
        mapping = dict(_discover_voice_directories())
        default_name = "northern_english_male"
        if default_name in mapping:
            base_directory = mapping[default_name]
        elif mapping:
            first_name = sorted(mapping.keys(), key=lambda s: s.lower())[0]
            base_directory = mapping[first_name]
        else:
            base_directory = voices_directory / default_name
    onnx_files = [p for p in base_directory.glob("*.onnx") if p.is_file()]

    def _score(p: Path) -> int:
        n = p.name.lower()
        if "high" in n:
            return 3
        if "medium" in n:
            return 2
        if "low" in n:
            return 1
        return 0

    onnx_files.sort(key=_score, reverse=True)
    onnx = onnx_files[0] if onnx_files else base_directory / "missing.onnx"
    cfg: Path | None = None
    stem_cfg = onnx.with_suffix(".onnx.json")
    if stem_cfg.exists():
        cfg = stem_cfg
    else:
        any_cfg = [p for p in base_directory.glob("*.json") if p.is_file()]
        if any_cfg:
            cfg = any_cfg[0]
    return onnx, cfg


def _ensure_piper_voice() -> None:
    current_voice_name = _tts_state.selected_voice_name
    if current_voice_name is None:
        return

    # Check if voice is already loaded and correct
    if _tts_state.voice is not None and hasattr(_tts_state.voice, "_loaded_for_voice"):
        if _tts_state.voice._loaded_for_voice == current_voice_name:
            return

    # Check cache first
    if current_voice_name in _tts_state.voice_model_cache:
        _tts_state.voice, _tts_state.voice_sample_rate = _tts_state.voice_model_cache[
            current_voice_name
        ]
        if hasattr(_tts_state.voice, "_loaded_for_voice"):
            _tts_state.voice._loaded_for_voice = current_voice_name
        return

    # Load voice model (only if not cached)
    _tts_state.voice = None
    _tts_state.voice_sample_rate = None
    try:
        from piper.voice import PiperVoice
    except Exception as e:
        raise RuntimeError("piper-tts is not installed. Run `pip install piper-tts`. ") from e
    model_path, cfg_path = _voice_model_paths()
    if not model_path.exists():
        return

    voice = PiperVoice.load(str(model_path), config_path=str(cfg_path) if cfg_path else None)
    voice._loaded_for_voice = current_voice_name

    sr: int | None = None
    try:
        if cfg_path and cfg_path.exists():
            with open(cfg_path, encoding="utf-8") as jf:
                cfg = json.load(jf)
                val = cfg.get("sample_rate") or cfg.get("sampleRate")
                if isinstance(val, int | float):
                    sr = int(val)
    except Exception:
        sr = None
    if sr is None:
        try:
            sr_attr = getattr(voice, "sample_rate", None)
            if isinstance(sr_attr, int | float):
                sr = int(sr_attr)
        except Exception:
            sr = None
    sample_rate = sr or 22050

    # Cache the loaded voice model
    _tts_state.voice_model_cache[current_voice_name] = (voice, sample_rate)
    _tts_state.voice = voice
    _tts_state.voice_sample_rate = sample_rate


def _apply_fade_in(pcm: bytes, sample_rate: int, millis: int = FADE_IN_MS_DEFAULT) -> bytes:
    if not pcm or millis <= 0 or sample_rate <= 0:
        return pcm
    number_samples = len(pcm) // 2
    if number_samples == 0:
        return pcm
    fade_samples = max(1, int(sample_rate * millis / 1000))
    fade_samples = min(fade_samples, number_samples)
    arr = array.array("h")
    arr.frombytes(pcm)
    for i in range(fade_samples):
        scale = i / float(fade_samples)
        arr[i] = int(arr[i] * scale)
    return arr.tobytes()


def _prepend_silence(pcm: bytes, sample_rate: int, millis: int = PRE_SILENCE_MS_DEFAULT) -> bytes:
    if millis <= 0 or sample_rate <= 0:
        return pcm
    number_samples = int(sample_rate * millis / 1000)
    if number_samples <= 0:
        return pcm
    silence = b"\x00\x00" * number_samples
    return silence + pcm


def _synthesize_to_wav_bytes(text: str) -> bytes | None:
    try:
        _ensure_piper_voice()
    except Exception:
        return _synthesize_to_wav_bytes_cli(text)
    try:
        if _tts_state.voice is None:
            return _synthesize_to_wav_bytes_cli(text)
        audio_generator = _tts_state.voice.synthesize(text)
        audio_chunks = list(audio_generator)
        audio_bytes = b"".join(chunk.audio_int16_bytes for chunk in audio_chunks)
        sr = _tts_state.voice_sample_rate or 22050
        audio_bytes = _apply_fade_in(audio_bytes, sr, FADE_IN_MS_DEFAULT)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(_tts_state.voice_sample_rate or 22050)
            wf.writeframes(audio_bytes)
        return buf.getvalue()
    except Exception:
        return _synthesize_to_wav_bytes_cli(text)


def _synthesize_to_wav_bytes_cli(text: str) -> bytes | None:
    try:
        from shutil import which

        exe = which("piper")
        if not exe:
            return None
        model_path, cfg_path = _voice_model_paths()
        if not model_path.exists():
            return None
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            wav_path = f.name
        cmd = [
            exe,
            "--model",
            str(model_path),
            "--output_file",
            wav_path,
            "-t",
            text,
        ]
        if cfg_path and cfg_path.exists():
            cmd += ["--config", str(cfg_path)]
        subprocess.run(cmd, check=True)
        with wave.open(wav_path, "rb") as wr:
            params = wr.getparams()
            pcm = wr.readframes(params.nframes)
        if params.nchannels == 1 and params.sampwidth == 2 and params.framerate > 0:
            pcm = _apply_fade_in(pcm, params.framerate, FADE_IN_MS_DEFAULT)
            out = io.BytesIO()
            with wave.open(out, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(params.framerate)
                wf.writeframes(pcm)
            data = out.getvalue()
        else:
            with open(wav_path, "rb") as fh:
                data = fh.read()
        with contextlib.suppress(Exception):
            os.remove(wav_path)
        return data
    except Exception:
        return None


def speak_text(text: str, *, rate: int = 160) -> None:
    data = _synthesize_to_wav_bytes(text)
    if data is not None:
        _play_wav_bytes(data)
    else:
        _tts_state.is_pending = False


def speak_text_async(text: str, *, rate: int = 160) -> None:
    _tts_state.is_pending = True
    try:
        thread = threading.Thread(
            target=speak_text, args=(text,), kwargs={"rate": rate}, daemon=True
        )
        thread.start()
    except Exception:
        speak_text(text, rate=rate)


def stop_speech(fade_ms: int = 200) -> None:
    _tts_state.is_pending = False
    try:
        if pygame.mixer.get_init() and _tts_state.playback_channel is not None:
            if fade_ms <= 0:
                _tts_state.playback_channel.stop()
            else:
                _tts_state.playback_channel.fadeout(max(0, int(fade_ms)))
    except Exception:
        pass


def is_speaking() -> bool:
    try:
        if not pygame.mixer.get_init():
            return False
        if _tts_state.playback_channel is None:
            return False
        return bool(_tts_state.playback_channel.get_busy())
    except Exception:
        return False


def speak_pokemon_description(description: str, entry: str, meta: dict, *, rate: int = 160) -> None:
    _tts_state.is_pending = True
    base = (description or "").strip()
    if not base:
        _tts_state.is_pending = False
        return
    rest = ""
    if " " in base:
        _first, rest = base.split(" ", 1)
    else:
        pass
    tail = (" " + entry.strip()) if entry and entry.strip() else ""
    speak_text_async(base + tail, rate=rate)
