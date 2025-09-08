from __future__ import annotations

import contextlib
import os
import sys
import tempfile
from typing import Self

import cv2
import numpy as np
import pygame


class CameraCapture:
    """Shared camera capture utility for apps that need camera functionality.

    Supports both photo capture mode (scanner) and live feed mode (AR catcher).
    """

    def __init__(self) -> None:
        self.cap: cv2.VideoCapture | None = None
        self.is_initialized = False

    def initialize(self) -> None:
        """Initialize camera with platform-specific backends and optimal settings."""
        if self.is_initialized:
            return

        # Platform-specific backend candidates
        backend_candidates: list[int] = []
        try:
            if sys.platform == "darwin":
                backend_candidates = [
                    getattr(cv2, "CAP_AVFOUNDATION", 0),
                    getattr(cv2, "CAP_ANY", 0),
                ]
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

        # Try backends until one works
        self.cap = None
        for backend in backend_candidates:
            try:
                self.cap = cv2.VideoCapture(0, backend) if backend else cv2.VideoCapture(0)
                if self.cap is not None and self.cap.isOpened():
                    break
            except Exception:
                pass

        if self.cap is None or not self.cap.isOpened():
            raise RuntimeError("Could not open default camera (index 0)")

        # Set codec for better performance
        try:
            fourcc = cv2.VideoWriter_fourcc(*"MJPG")
            self.cap.set(cv2.CAP_PROP_FOURCC, fourcc)
        except Exception:
            pass

        # Try to set optimal resolution
        self._set_optimal_resolution()

        # Set FPS
        with contextlib.suppress(Exception):
            self.cap.set(cv2.CAP_PROP_FPS, 30)

        self.is_initialized = True

    def _set_optimal_resolution(self) -> None:
        """Set the best available resolution from preferred list."""
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
            ok_w = self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, float(width))
            ok_h = self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, float(height))
            actual_w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            actual_h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            close_enough = abs(actual_w - width) <= 16 and abs(actual_h - height) <= 16
            return (ok_w and ok_h) and close_enough

        applied = False
        for w, h in preferred_resolutions:
            if _try_set_resolution(w, h):
                applied = True
                break

        if not applied:
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    def get_frame(self) -> pygame.Surface | None:
        """Get the current camera frame as a pygame surface.

        Returns None if no frame is available.
        """
        if not self.is_initialized or self.cap is None:
            return None

        ret, frame = self.cap.read()
        if not ret:
            return None

        # Convert BGR to RGB
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]

        # Create pygame surface from frame
        surface = pygame.image.frombuffer(rgb.tobytes(), (w, h), "RGB")
        return surface

    def get_scaled_frame(self, screen_rect: pygame.Rect) -> pygame.Surface | None:
        """Get camera frame scaled to fit the screen while maintaining aspect ratio."""
        frame = self.get_frame()
        if frame is None:
            return None

        # Scale to fit screen
        w, h = frame.get_size()
        scale = max(screen_rect.width / w, screen_rect.height / h)
        new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
        scaled = pygame.transform.smoothscale(frame, new_size)

        return scaled

    def capture_photo_mode(
        self, screen: pygame.Surface, *, preview_label: str = "Preview"
    ) -> str | None:
        """Photo capture mode - displays live feed, lets user take and confirm photo.

        Returns path to captured photo file, or None if cancelled.
        """
        from src.utils.audio_util import play_sfx

        if not self.is_initialized:
            self.initialize()

        screen_rect = screen.get_rect()
        clock = pygame.time.Clock()
        captured_frame_bgr: np.ndarray | None = None
        FLASH_TOTAL_MS = 260
        flash_ms_remaining = 0
        confirm_mode = False
        result_path: str | None = None

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

            # Get current frame
            if not confirm_mode:
                ret, frame = self.cap.read()
                if not ret:
                    continue
                show_bgr = frame
            else:
                show_bgr = captured_frame_bgr
                if show_bgr is None:
                    confirm_mode = False
                    continue

            # Convert and scale frame for display
            rgb = cv2.cvtColor(show_bgr, cv2.COLOR_BGR2RGB)
            h, w = rgb.shape[:2]
            surf = pygame.image.frombuffer(rgb.tobytes(), (w, h), "RGB")
            scale = max(screen_rect.width / w, screen_rect.height / h)
            new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
            scaled = pygame.transform.smoothscale(surf, new_size)

            # Draw frame
            screen.fill((0, 0, 0))
            scaled_rect = scaled.get_rect(center=screen_rect.center)
            screen.blit(scaled, scaled_rect)

            # Draw preview label in confirm mode
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

            # Handle photo capture
            if capture_requested and not confirm_mode:
                ret, frame = self.cap.read()
                if ret:
                    captured_frame_bgr = frame.copy()
                    confirm_mode = True
                    flash_ms_remaining = FLASH_TOTAL_MS
                    with contextlib.suppress(Exception):
                        play_sfx(
                            os.path.join(os.path.dirname(__file__), "media", "shutter.mp3"),
                            channel_name="shutter",
                        )

            # Draw flash effect
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

        return result_path

    def cleanup(self) -> None:
        """Release camera resources."""
        if self.cap is not None:
            self.cap.release()
            self.cap = None
        self.is_initialized = False

    def __enter__(self) -> Self:
        """Context manager entry."""
        self.initialize()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Context manager exit."""
        self.cleanup()


# Convenience function that maintains backwards compatibility with ui_util.py
def open_camera_capture(screen: pygame.Surface, *, preview_label: str = "Preview") -> str | None:
    """Backwards compatible function for photo capture mode.

    This maintains compatibility with existing scanner code.
    """
    with CameraCapture() as camera:
        return camera.capture_photo_mode(screen, preview_label=preview_label)
