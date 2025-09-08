from __future__ import annotations

import contextlib
import os
import sys
import tempfile
import threading
from collections.abc import Callable
from typing import Any

import cv2
import numpy as np
import pygame
from PIL import Image, ImageSequence

from src.utils.audio_util import fadeout_music, play_music_loop, play_sfx


def draw_hint_footer(screen: pygame.Surface, text: str) -> None:
    screen_width, screen_height = screen.get_size()
    hint_font = pygame.font.Font(None, 36)
    hint_surface = hint_font.render(text, True, (250, 250, 255))
    hint_rectangle = hint_surface.get_rect(midbottom=(screen_width // 2, screen_height - 26))
    screen.blit(hint_surface, hint_rectangle)


def handle_basic_events(exit_on_escape: bool = True, exit_on_interaction: bool = False) -> bool:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            return True
        if event.type == pygame.KEYDOWN and exit_on_escape and event.key == pygame.K_ESCAPE:
            return True
        if event.type in (pygame.KEYDOWN, pygame.MOUSEBUTTONDOWN):
            return exit_on_interaction
    return False


class LoadingCanceledError(Exception):
    pass


def _load_gif_surfaces(
    path: str, max_size: tuple[int, int]
) -> tuple[list[pygame.Surface], list[int]]:
    try:
        image = Image.open(path)
        frames: list[pygame.Surface] = []
        durations: list[int] = []
        for frame in ImageSequence.Iterator(image):
            frame_converted = frame.convert("RGBA")
            frame_converted.thumbnail(max_size, Image.LANCZOS)
            surface = pygame.image.frombuffer(
                frame_converted.tobytes(), frame_converted.size, frame_converted.mode
            )
            frames.append(surface.copy())
            durations.append(int(frame.info.get("duration", 80)))
        if not frames:
            raise RuntimeError("Empty GIF")
        return frames, durations
    except Exception:
        return [], []


def run_with_loading(
    screen: pygame.Surface,
    status_text: str,
    function: Callable[[], Any],
    *,
    gif_path: str | None = None,
    background_color: tuple[int, int, int] = (255, 255, 255),
    text_color: tuple[int, int, int] = (30, 30, 34),
    gif_max_size: tuple[int, int] = (220, 220),
    sfx_path: str | None = None,
) -> Any:
    screen_rect = screen.get_rect()
    frames: list[pygame.Surface] = []
    durations: list[int] = []
    if gif_path and os.path.exists(gif_path):
        frames, durations = _load_gif_surfaces(gif_path, gif_max_size)
    result_container: dict = {}
    error_container: dict = {}

    def worker() -> None:
        try:
            result_container["value"] = function()
        except Exception as e:
            error_container["error"] = e

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    clock = pygame.time.Clock()
    idx = 0
    elapsed = 0
    font = pygame.font.Font(None, 36)
    if sfx_path and os.path.exists(sfx_path):
        with contextlib.suppress(Exception):
            play_music_loop(sfx_path, volume=0.6)
    while thread.is_alive():
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                with contextlib.suppress(Exception):
                    fadeout_music(200)
                raise LoadingCanceledError
        screen.fill(background_color)
        if frames:
            surf = frames[idx]
            rect = surf.get_rect(center=(screen_rect.centerx, screen_rect.centery - 20))
            screen.blit(surf, rect)
            elapsed += clock.get_time()
            if elapsed >= max(40, durations[idx]):
                idx = (idx + 1) % len(frames)
                elapsed = 0
        text = font.render(status_text, True, text_color)
        screen.blit(text, text.get_rect(midtop=(screen_rect.centerx, screen_rect.centery + 120)))
        pygame.display.flip()
        clock.tick(60)
    with contextlib.suppress(Exception):
        fadeout_music(250)
    if "error" in error_container:
        raise error_container["error"]
    return result_container.get("value")


def open_camera_capture(screen: pygame.Surface, *, preview_label: str = "Preview") -> str | None:
    screen_rect = screen.get_rect()

    backend_candidates: list[int] = []
    try:
        if sys.platform == "darwin":
            backend_candidates = [getattr(cv2, "CAP_AVFOUNDATION", 0), getattr(cv2, "CAP_ANY", 0)]
        elif os.name == "nt":
            backend_candidates = [
                getattr(cv2, "CAP_DSHOW", 0),
                getattr(cv2, "CAP_MSMF", 0),
                getattr(cv2, "CAP_ANY", 0),
            ]
        else:
            backend_candidates = [getattr(cv2, "CAP_V4L2", 0), getattr(cv2, "CAP_ANY", 0)]
    except Exception:
        backend_candidates = [0]
    cap = None
    for backend in backend_candidates:
        try:
            cap = cv2.VideoCapture(0, backend) if backend else cv2.VideoCapture(0)
            if cap is not None and cap.isOpened():
                break
        except Exception:
            pass
    if cap is None or not cap.isOpened():
        raise RuntimeError("Could not open default camera (index 0)")
    try:
        fourcc = cv2.VideoWriter_fourcc(*"MJPG")
        cap.set(cv2.CAP_PROP_FOURCC, fourcc)
    except Exception:
        pass
    preferred_resolutions: list[tuple[int, int]] = [
        (1920, 1080),
        (1600, 1200),
        (1280, 960),
        (1280, 720),
        (1024, 768),
        (800, 600),
        (640, 480),
    ]

    def _try_set_resolution(width: int, height: int) -> bool:
        ok_w = cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(width))
        ok_h = cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(height))
        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        close_enough = abs(actual_w - width) <= 16 and abs(actual_h - height) <= 16
        return (ok_w and ok_h) and close_enough

    applied = False
    for w, h in preferred_resolutions:
        if _try_set_resolution(w, h):
            applied = True
            break
    if not applied:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    with contextlib.suppress(Exception):
        cap.set(cv2.CAP_PROP_FPS, 30)
    clock = pygame.time.Clock()
    captured_frame_bgr: np.ndarray | None = None
    FLASH_TOTAL_MS = 260
    flash_ms_remaining = 0

    def draw_text_prompts() -> None:
        if not confirm_mode:
            return
        footer_h = 100
        footer = pygame.Surface((screen_rect.width, footer_h), pygame.SRCALPHA)
        footer.fill((0, 0, 0, 130))
        screen.blit(footer, (0, screen_rect.height - footer_h))
        instruction_font = pygame.font.Font(None, 28)
        instructions = ["ENTER: Keep photo", "BACKSPACE: Retake", "ESC: Cancel"]
        y_start = screen_rect.height - 80
        for i, instruction in enumerate(instructions):
            color = (255, 255, 255) if i < 2 else (200, 200, 200)
            text = instruction_font.render(instruction, True, color)
            text_rect = text.get_rect(center=(screen_rect.centerx, y_start + i * 25))
            screen.blit(text, text_rect)

    running = True
    confirm_mode = False
    result_path: str | None = None
    while running:
        capture_requested = False
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (
                event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE
            ):
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN:
                    if not confirm_mode:
                        capture_requested = True
                    else:
                        if captured_frame_bgr is not None:
                            temp_fd, temp_path = tempfile.mkstemp(suffix=".jpg")
                            os.close(temp_fd)
                            cv2.imwrite(
                                temp_path, captured_frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 95]
                            )
                            result_path = temp_path
                            with contextlib.suppress(Exception):
                                play_sfx(
                                    os.path.join(
                                        os.path.dirname(__file__), "media", "accepted.mp3"
                                    ),
                                    channel_name="accepted",
                                )
                        running = False
                elif event.key == pygame.K_BACKSPACE and confirm_mode:
                    confirm_mode = False
                    captured_frame_bgr = None
                    with contextlib.suppress(Exception):
                        play_sfx(
                            os.path.join(os.path.dirname(__file__), "media", "release.mp3"),
                            channel_name="release",
                        )
        if not confirm_mode:
            ret, frame = cap.read()
            if not ret:
                continue
            show_bgr = frame
        else:
            show_bgr = captured_frame_bgr
            if show_bgr is None:
                confirm_mode = False
                continue
        rgb = cv2.cvtColor(show_bgr, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        surf = pygame.image.frombuffer(rgb.tobytes(), (w, h), "RGB")
        scale = max(screen_rect.width / w, screen_rect.height / h)
        new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
        scaled = pygame.transform.smoothscale(surf, new_size)
        screen.fill((0, 0, 0))
        scaled_rect = scaled.get_rect(center=screen_rect.center)
        screen.blit(scaled, scaled_rect)
        if confirm_mode:
            label_font = pygame.font.Font(None, 40)
            lbl = label_font.render(preview_label, True, (255, 255, 255))
            pad_x, pad_y = 12, 10
            bg = pygame.Surface(
                (lbl.get_width() + pad_x * 2, lbl.get_height() + pad_y * 2), pygame.SRCALPHA
            )
            bg.fill((0, 0, 0, 130))
            screen.blit(bg, (18, 18))
            screen.blit(lbl, (18 + pad_x, 18 + pad_y))
        draw_text_prompts()
        if capture_requested and not confirm_mode:
            ret, frame = cap.read()
            if ret:
                captured_frame_bgr = frame.copy()
                confirm_mode = True
                flash_ms_remaining = FLASH_TOTAL_MS
                with contextlib.suppress(Exception):
                    play_sfx(
                        os.path.join(os.path.dirname(__file__), "media", "shutter.mp3"),
                        channel_name="shutter",
                    )
        dt = clock.get_time()
        if flash_ms_remaining > 0:
            alpha = int(255 * (flash_ms_remaining / FLASH_TOTAL_MS))
            alpha = max(0, min(255, alpha))
            flash = pygame.Surface(screen_rect.size, pygame.SRCALPHA)
            flash.fill((255, 255, 255, alpha))
            screen.blit(flash, (0, 0))
            flash_ms_remaining = max(0, flash_ms_remaining - dt)
        pygame.display.flip()
        clock.tick(30)
    cap.release()

    return result_path
