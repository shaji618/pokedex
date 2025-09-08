from __future__ import annotations

from typing import Any

import pygame

from src.utils.focus_manager import (
    FocusableElement,
    FocusManager,
    NavigationAction,
    NavigationResult,
)
from src.utils.focus_renderer import DEFAULT_FOCUS_RENDERER, FocusRenderer


class FocusIntegrationMixin:
    def init_focus_system(
        self, renderer: FocusRenderer | None = None, auto_update: bool = True
    ) -> None:
        self.focus_manager = FocusManager()
        self.focus_renderer = renderer or DEFAULT_FOCUS_RENDERER
        self.auto_update_focus = auto_update
        self._focus_enabled = True

    def enable_focus(self) -> None:
        self._focus_enabled = True

    def disable_focus(self) -> None:
        self._focus_enabled = False

    def is_focus_enabled(self) -> bool:
        return getattr(self, "_focus_enabled", False)

    def update_focus_elements(self) -> None:
        if not self.is_focus_enabled():
            return
        try:
            elements = self.get_focusable_elements()
            self.focus_manager.update_elements(elements)
        except AttributeError:
            pass

    def handle_focus_event(self, event: pygame.event.Event) -> bool:
        if not self.is_focus_enabled():
            return False
        if event.type != pygame.KEYDOWN:
            return False
        if self.auto_update_focus:
            self.update_focus_elements()
        result = self.focus_manager.handle_key_event(event)
        if result:
            try:
                return self.handle_navigation_result(result)
            except AttributeError:
                return False
        return False

    def draw_focus_indicator(self, screen: pygame.Surface) -> None:
        if not self.is_focus_enabled():
            return
        focused_element = self.focus_manager.get_focused_element()
        if focused_element:
            self.focus_renderer.draw_focus_indicator(screen, focused_element.rect)

    def get_focused_element(self) -> FocusableElement | None:
        if not self.is_focus_enabled():
            return None
        return self.focus_manager.get_focused_element()

    def reset_focus(self) -> None:
        if self.is_focus_enabled():
            self.focus_manager.reset_focus()


def create_simple_element(
    rect: pygame.Rect, callback: callable | None = None, enabled: bool = True, **metadata: Any
) -> FocusableElement:
    return FocusableElement(
        rect=rect, callback=callback, enabled=enabled, metadata=metadata if metadata else None
    )


def create_button_element(
    rect: pygame.Rect, action: callable, enabled: bool = True, button_type: str = "button"
) -> FocusableElement:
    return FocusableElement(
        rect=rect, callback=action, enabled=enabled, metadata={"type": button_type}
    )


def create_grid_elements(
    rects: list[pygame.Rect],
    callbacks: list[callable | None] | None = None,
    columns: int = 3,
    enabled_mask: list[bool] | None = None,
) -> list[list[FocusableElement]]:
    if callbacks is None:
        callbacks = [None] * len(rects)
    if enabled_mask is None:
        enabled_mask = [True] * len(rects)
    length = len(rects)
    callbacks = callbacks[:length] + [None] * (length - len(callbacks))
    enabled_mask = enabled_mask[:length] + [True] * (length - len(enabled_mask))
    rows: list[list[FocusableElement]] = []
    for i in range(0, length, columns):
        row: list[FocusableElement] = []
        for j in range(columns):
            index = i + j
            if index < length:
                element = FocusableElement(
                    rect=rects[index], callback=callbacks[index], enabled=enabled_mask[index]
                )
                row.append(element)
        if row:
            rows.append(row)
    return rows


def handle_standard_navigation(
    result: NavigationResult,
    quit_callback: callable | None = None,
    back_callback: callable | None = None,
) -> bool:
    if result.action == NavigationAction.EXIT:
        if quit_callback:
            quit_callback()
        return True
    elif result.action == NavigationAction.BACK:
        if back_callback:
            back_callback()
        return True
    elif result.action == NavigationAction.ACTIVATE:
        return True
    return False


def integrate_focus_with_event_loop(
    events: list[pygame.event.Event],
    focus_manager: FocusManager,
    focusable_elements: list[list[FocusableElement]],
    navigation_handler: callable[[NavigationResult], bool],
) -> list[pygame.event.Event]:
    focus_manager.update_elements(focusable_elements)
    unhandled_events = []
    for event in events:
        if event.type == pygame.KEYDOWN:
            result = focus_manager.handle_key_event(event)
            if result and navigation_handler(result):
                continue
        unhandled_events.append(event)
    return unhandled_events
