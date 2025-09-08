import pygame

from src.utils.focus_integration import FocusIntegrationMixin, create_grid_elements
from src.utils.focus_manager import NavigationAction, NavigationResult
from src.utils.menu import build_menu_from_apps, draw_menu, layout_grid
from src.utils.play_button_util import is_any_audio_playing
from src.utils.runner import run_app


class Launcher(FocusIntegrationMixin):
    def __init__(self) -> None:
        pygame.init()
        self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        self.clock = pygame.time.Clock()
        self.title_font = pygame.font.Font(None, 64)
        self.running = True
        self.init_focus_system()
        self.items = []
        self.laid_out_rects = []
        self.needs_layout = False
        self.rebuild_menu()

    def rebuild_menu(self) -> None:
        self.items = build_menu_from_apps(self.screen.get_size())
        rects = [item.rect for item in self.items]
        self.laid_out_rects = layout_grid(self.screen.get_size(), rects)
        self.needs_layout = False
        self.reset_focus()
        self.update_focus_elements()

    def launch_app(self, application_index: int) -> None:
        if 0 <= application_index < len(self.items):
            item = self.items[application_index]
            if item.run_path:
                run_app(self.screen, item.run_path)
                self.rebuild_menu()

    def detect_grid_layout(self) -> int:
        if not self.laid_out_rects:
            return 1
        y_groups = {}
        tolerance = 20
        for i, rect in enumerate(self.laid_out_rects):
            y = rect.centery
            found_group = None
            for group_y in y_groups:
                if abs(y - group_y) <= tolerance:
                    found_group = group_y
                    break
            if found_group is not None:
                y_groups[found_group].append(i)
            else:
                y_groups[y] = [i]
        sorted_rows = sorted(y_groups.items())
        max_items_per_row = max(len(indices) for _, indices in sorted_rows) if sorted_rows else 1
        return max_items_per_row

    def get_focusable_elements(self) -> list:
        if not self.items or not self.laid_out_rects:
            return []
        callbacks = [lambda i=i: self.launch_app(i) for i in range(len(self.items))]
        columns = self.detect_grid_layout()
        return create_grid_elements(rects=self.laid_out_rects, callbacks=callbacks, columns=columns)

    def handle_navigation_result(self, result: NavigationResult) -> bool:
        if (
            result.action == NavigationAction.EXIT
            or result.action == NavigationAction.EXIT_TO_LAUNCHER
        ):
            self.running = False
            return True
        elif result.action == NavigationAction.ACTIVATE:
            return True
        return False

    def handle_mouse_events(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mouse_x, mouse_y = event.pos
            for i, rect in enumerate(self.laid_out_rects):
                if rect.collidepoint(mouse_x, mouse_y):
                    self.launch_app(i)
                    return True
        return False

    def draw_focus_indicator(self, screen: pygame.Surface) -> None:
        if is_any_audio_playing():
            return
        super().draw_focus_indicator(screen)

    def run(self) -> None:
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if not self.handle_focus_event(event) and event.key == pygame.K_q:
                        self.running = False
                else:
                    self.handle_mouse_events(event)
            if self.needs_layout:
                rects = [item.rect for item in self.items]
                self.laid_out_rects = layout_grid(self.screen.get_size(), rects)
                self.needs_layout = False
            draw_menu(self.screen, self.items, self.laid_out_rects, self.title_font)
            self.draw_focus_indicator(self.screen)
            pygame.display.flip()
            self.clock.tick(60)
        pygame.quit()


def run() -> None:
    launcher = Launcher()
    launcher.run()


if __name__ == "__main__":
    run()
