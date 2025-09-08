from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

import pygame


class NavigationAction(Enum):
    NONE = "none"
    ACTIVATE = "activate"
    EXIT = "exit"
    BACK = "back"
    EXIT_TO_PARENT = "exit_to_parent"
    EXIT_TO_LAUNCHER = "exit_to_launcher"


class NavigationResult:
    def __init__(self, action: NavigationAction, data: Any = None) -> None:
        self.action = action
        self.data = data

    def __bool__(self) -> bool:
        return self.action != NavigationAction.NONE


@dataclass
class FocusableElement:
    rect: pygame.Rect
    callback: Callable[[], Any] | None = None
    enabled: bool = True
    metadata: dict[str, Any] | None = None

    def activate(self) -> Any:
        if self.callback and self.enabled:
            return self.callback()
        return None

    def is_focusable(self) -> bool:
        return self.enabled


class NavigableScreen(Protocol):
    def get_focusable_elements(self) -> list[list[FocusableElement]]: ...
    def handle_navigation_result(self, result: NavigationResult) -> bool: ...


class FocusManager:
    def __init__(self) -> None:
        self.current_row = 0
        self.current_column = 0
        self._elements: list[list[FocusableElement]] = []

    def update_elements(self, elements: list[list[FocusableElement]]) -> None:
        self._elements = elements
        self._clamp_focus()

    def get_focused_element(self) -> FocusableElement | None:
        if not self._elements:
            return None
        if not (0 <= self.current_row < len(self._elements)):
            return None
        row = self._elements[self.current_row]
        if not (0 <= self.current_column < len(row)):
            return None
        element = row[self.current_column]
        return element if element.is_focusable() else None

    def activate_current(self) -> NavigationResult:
        element = self.get_focused_element()
        if element:
            result = element.activate()
            return NavigationResult(NavigationAction.ACTIVATE, result)
        return NavigationResult(NavigationAction.NONE)

    def handle_key_event(self, event: pygame.event.Event) -> NavigationResult:
        if event.type != pygame.KEYDOWN:
            return NavigationResult(NavigationAction.NONE)
        key = event.key
        if key == pygame.K_ESCAPE:
            return NavigationResult(NavigationAction.EXIT_TO_LAUNCHER)
        elif key == pygame.K_BACKSPACE:
            return NavigationResult(NavigationAction.BACK)
        elif key == pygame.K_RETURN:
            element = self.get_focused_element()
            if element:
                result = element.activate()
                return NavigationResult(NavigationAction.ACTIVATE, result)
            return NavigationResult(NavigationAction.NONE)
        elif key in (pygame.K_UP, pygame.K_DOWN, pygame.K_LEFT, pygame.K_RIGHT):
            self._handle_arrow_navigation(key)
            return NavigationResult(NavigationAction.NONE)
        return NavigationResult(NavigationAction.NONE)

    def _handle_arrow_navigation(self, key: int) -> None:
        if not self._elements:
            return
        if key == pygame.K_UP:
            self._move_up()
        elif key == pygame.K_DOWN:
            self._move_down()
        elif key == pygame.K_LEFT:
            self._move_left()
        elif key == pygame.K_RIGHT:
            self._move_right()
        self._clamp_focus()

    def _move_up(self) -> None:
        if len(self._elements) == 0:
            return
        if len(self._elements) == 1:
            self._cycle_within_row(-1)
            return
        start_row = self.current_row
        while True:
            self.current_row = (self.current_row - 1) % len(self._elements)
            if self._current_row_has_focusable_elements():
                break
            if self.current_row == start_row:
                break
        self._clamp_column()

    def _move_down(self) -> None:
        if len(self._elements) == 0:
            return
        if len(self._elements) == 1:
            self._cycle_within_row(1)
            return
        start_row = self.current_row
        while True:
            self.current_row = (self.current_row + 1) % len(self._elements)
            if self._current_row_has_focusable_elements():
                break
            if self.current_row == start_row:
                break
        self._clamp_column()

    def _move_left(self) -> None:
        if not self._elements or not (0 <= self.current_row < len(self._elements)):
            return
        row = self._elements[self.current_row]
        focusable_indices = [i for i, elem in enumerate(row) if elem.is_focusable()]
        if not focusable_indices:
            return
        first_focusable_column = focusable_indices[0]
        if self.current_column == first_focusable_column:
            self._wrap_to_previous_row()
        else:
            self._cycle_within_row(-1)

    def _move_right(self) -> None:
        if not self._elements or not (0 <= self.current_row < len(self._elements)):
            return
        row = self._elements[self.current_row]
        focusable_indices = [i for i, elem in enumerate(row) if elem.is_focusable()]
        if not focusable_indices:
            return
        last_focusable_column = focusable_indices[-1]
        if self.current_column == last_focusable_column:
            self._wrap_to_next_row()
        else:
            self._cycle_within_row(1)

    def _cycle_within_row(self, direction: int) -> None:
        if not self._elements or not (0 <= self.current_row < len(self._elements)):
            return
        row = self._elements[self.current_row]
        focusable_indices = [i for i, elem in enumerate(row) if elem.is_focusable()]
        if not focusable_indices:
            return
        try:
            current_index_in_focusable = focusable_indices.index(self.current_column)
        except ValueError:
            if direction > 0:
                self.current_column = focusable_indices[0]
            else:
                self.current_column = focusable_indices[-1]
            return
        if direction > 0:
            new_index = (current_index_in_focusable + 1) % len(focusable_indices)
        else:
            new_index = (current_index_in_focusable - 1) % len(focusable_indices)
        self.current_column = focusable_indices[new_index]

    def _wrap_to_previous_row(self) -> None:
        if len(self._elements) <= 1:
            return
        original_row = self.current_row
        while True:
            self.current_row = (self.current_row - 1) % len(self._elements)
            row = self._elements[self.current_row]
            focusable_indices = [i for i, elem in enumerate(row) if elem.is_focusable()]
            if focusable_indices:
                self.current_column = focusable_indices[-1]
                break
            if self.current_row == original_row:
                break

    def _wrap_to_next_row(self) -> None:
        if len(self._elements) <= 1:
            return
        original_row = self.current_row
        while True:
            self.current_row = (self.current_row + 1) % len(self._elements)
            row = self._elements[self.current_row]
            focusable_indices = [i for i, elem in enumerate(row) if elem.is_focusable()]
            if focusable_indices:
                self.current_column = focusable_indices[0]
                break
            if self.current_row == original_row:
                break

    def _current_row_has_focusable_elements(self) -> bool:
        if not (0 <= self.current_row < len(self._elements)):
            return False
        row = self._elements[self.current_row]
        return any(elem.is_focusable() for elem in row)

    def _clamp_column(self) -> None:
        if not (0 <= self.current_row < len(self._elements)):
            return
        row = self._elements[self.current_row]
        focusable_indices = [i for i, elem in enumerate(row) if elem.is_focusable()]
        if not focusable_indices:
            self.current_column = 0
            return
        if self.current_column not in focusable_indices:
            closest = min(focusable_indices, key=lambda x: abs(x - self.current_column))
            self.current_column = closest

    def _clamp_focus(self) -> None:
        if not self._elements:
            self.current_row = 0
            self.current_column = 0
            return
        self.current_row = max(0, min(self.current_row, len(self._elements) - 1))
        if not self._current_row_has_focusable_elements():
            for offset in range(len(self._elements)):
                for direction in [1, -1]:
                    test_row = (self.current_row + direction * offset) % len(self._elements)
                    if 0 <= test_row < len(self._elements):
                        test_elements = self._elements[test_row]
                        if any(elem.is_focusable() for elem in test_elements):
                            self.current_row = test_row
                            break
                else:
                    continue
                break
        self._clamp_column()

    def reset_focus(self) -> None:
        self.current_row = 0
        self.current_column = 0
        self._clamp_focus()
