import os

import pygame

from src.utils.image_util import load_image_safe
from src.utils.path_util import project_root
from src.utils.runner import get_app_metadata
from src.utils.ui_constants import DARK_BG


class MenuItem:
    def __init__(
        self, surface: pygame.Surface, rect: pygame.Rect, label: str, run_path: str
    ) -> None:
        self.surface = surface
        self.rect = rect
        self.label = label
        self.run_path = run_path


def create_menu_item(
    icon_path: str,
    run_path: str,
    surface_size: tuple[int, int],
    label: str | None = None,
    *,
    bg_color: tuple[int, int, int] | None = None,
) -> MenuItem:
    screen_width, screen_height = surface_size
    ideal_w = int(screen_width * 0.20)
    ideal_h = int(screen_height * 0.24)
    tile = max(1, min(ideal_w, ideal_h))
    box_width = tile
    box_height = tile
    inner_padding = max(8, int(tile * 0.08))
    img = load_image_safe(icon_path)
    if img is None:
        raise FileNotFoundError(f"Could not load icon: {icon_path}")
    inner_w = max(1, box_width - 2 * inner_padding)
    inner_h = max(1, box_height - 2 * inner_padding)
    image_w, image_h = img.get_size()
    scale = min(inner_w / image_w, inner_h / image_h)
    scaled_size = (max(1, int(image_w * scale)), max(1, int(image_h * scale)))
    scaled = pygame.transform.smoothscale(img, scaled_size)
    box_surface = pygame.Surface((box_width, box_height), pygame.SRCALPHA)
    box_rect = box_surface.get_rect()
    fill = (255, 255, 255)
    if bg_color is not None:
        fill = bg_color
    pygame.draw.rect(box_surface, fill, box_rect, border_radius=20)
    scaled_rect = scaled.get_rect(center=box_rect.center)
    box_surface.blit(scaled, scaled_rect)
    final_label = label if label else os.path.splitext(os.path.basename(icon_path))[0]
    return MenuItem(box_surface, box_rect, final_label, run_path)


def _find_menu_icon_in_app_directory(app_directory: str) -> str:
    for ext in (".png", ".jpg", ".jpeg", ".bmp", ".gif"):
        candidate = os.path.join(app_directory, f"menu_icon{ext}")
        if os.path.exists(candidate):
            return candidate
    raise FileNotFoundError(f"No menu_icon.* found in {app_directory}")


def build_menu_from_apps(
    surface_size: tuple[int, int], apps_directory: str | None = None
) -> list[MenuItem]:
    items: list[MenuItem] = []
    if apps_directory is None:
        apps_directory = os.path.join(str(project_root()), "src", "apps")
    if not os.path.isdir(apps_directory):
        return items

    for entry in sorted(os.listdir(apps_directory)):
        app_path = os.path.join(apps_directory, entry)
        if not os.path.isdir(app_path):
            continue
        run_path = os.path.join(app_path, "app.py")
        if not os.path.exists(run_path):
            continue

        module_name = f"src.apps.{entry}.app"

        icon_path = _find_menu_icon_in_app_directory(app_path)

        data = get_app_metadata(module_name)

        app_label = None
        app_bg = None
        if isinstance(data, dict):
            app_label = data.get("name")
            color = data.get("menu_icon_bg_color")
            if isinstance(color, tuple) and len(color) == 3:
                app_bg = tuple(int(max(0, min(255, c))) for c in color)
            elif isinstance(color, str):
                s = color.strip().lstrip("#")
                if len(s) == 3:
                    s = "".join(ch * 2 for ch in s)
                if len(s) == 6:
                    app_bg = (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))

        item = create_menu_item(icon_path, module_name, surface_size, app_label, bg_color=app_bg)
        items.append(item)
    return items


def layout_grid(parent_size: tuple[int, int], item_rects: list[pygame.Rect]) -> list[pygame.Rect]:
    if not item_rects:
        return []
    screen_width, screen_height = parent_size
    num_items = len(item_rects)
    min_spacing = 32
    avg_item_width = sum(r.width for r in item_rects) // num_items
    avg_item_height = sum(r.height for r in item_rects) // num_items
    usable_width = screen_width - (2 * min_spacing)
    max_cols_by_width = max(1, usable_width // (avg_item_width + min_spacing))
    preferred_max_cols = min(max_cols_by_width, max(4, int(num_items**0.6)))
    cols = min(preferred_max_cols, num_items)
    if num_items <= 6:
        best_cols = cols
        best_aspect_ratio = float("inf")
        for test_cols in range(1, min(4, num_items) + 1):
            test_rows = (num_items + test_cols - 1) // test_cols
            grid_width = test_cols * (avg_item_width + min_spacing)
            grid_height = test_rows * (avg_item_height + min_spacing)
            if grid_width <= usable_width:
                aspect_ratio = max(grid_width / grid_height, grid_height / grid_width)
                if aspect_ratio < best_aspect_ratio:
                    best_aspect_ratio = aspect_ratio
                    best_cols = test_cols
        cols = best_cols
    rows = (num_items + cols - 1) // cols
    total_item_width = cols * avg_item_width
    horizontal_spacing = max(min_spacing, (screen_width - total_item_width) // (cols + 1))
    total_item_height = rows * avg_item_height
    vertical_spacing = max(min_spacing, (screen_height - total_item_height) // (rows + 1))
    grid_width = cols * avg_item_width + (cols - 1) * horizontal_spacing
    grid_height = rows * avg_item_height + (rows - 1) * vertical_spacing
    start_x = (screen_width - grid_width) // 2
    start_y = (screen_height - grid_height) // 2
    laid_out: list[pygame.Rect] = []
    for i, rect in enumerate(item_rects):
        row = i // cols
        col = i % cols
        x = start_x + col * (avg_item_width + horizontal_spacing)
        y = start_y + row * (avg_item_height + vertical_spacing)
        new_rect = rect.copy()
        new_rect.topleft = (x, y)
        laid_out.append(new_rect)
    return laid_out


def draw_menu(
    screen: pygame.Surface,
    items: list[MenuItem],
    laid_out_rects: list[pygame.Rect],
    title_font: pygame.font.Font,
) -> None:
    screen.fill(DARK_BG)
    label_font = pygame.font.Font(None, 36)
    for item, rect in zip(items, laid_out_rects, strict=False):
        screen.blit(item.surface, rect)
        pygame.draw.rect(screen, (255, 255, 255), rect.inflate(16, 16), width=2, border_radius=18)
        label_surf = label_font.render(item.label, True, (230, 230, 230))
        label_rect = label_surf.get_rect(midtop=(rect.centerx, rect.bottom + 12))
        screen.blit(label_surf, label_rect)
