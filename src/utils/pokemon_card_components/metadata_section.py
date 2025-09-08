from __future__ import annotations

import pygame

from ..palette import GEN_COLOR_MAP, darken_color, get_text_color
from ..pill_util import draw_pill


class MetadataSection:
    """Renders Pokemon metadata pills (generation, Pokedex number) and TTS button positioning."""
    
    # Component constants
    PILL_HEIGHT = 28
    PILL_PADDING_X = 12
    GAP_X = 10
    FONT_SIZE = 22
    
    def __init__(self) -> None:
        pass
    
    def render(
        self,
        screen: pygame.Surface,
        area: pygame.Rect,
        generation: int | None,
        pokedex_number: int | str | None,
        tts_button_callback: callable | None = None,
    ) -> tuple[pygame.Rect | None, int]:
        """Render metadata pills and return TTS button rect and row height.
        
        Args:
            screen: Surface to render on
            area: Rectangle defining the render area
            generation: Pokemon generation (1-9)
            pokedex_number: Pokemon Pokedex number
            tts_button_callback: Optional callback for TTS button rendering
            
        Returns:
            Tuple of (tts_button_rect, row_height)
        """
        if area.width <= 0 or area.height <= 0:
            return None, 0
            
        current_x = area.left
        current_y = area.top
        row_height = 0
        font = pygame.font.Font(None, self.FONT_SIZE)
        
        # Render generation pill
        if isinstance(generation, int) and 1 <= generation <= 9:
            generation_color = GEN_COLOR_MAP.get(generation, (160, 160, 160))
            generation_label = f"GENERATION {generation}"
            
            text_surface = font.render(generation_label, True, get_text_color(generation_color))
            pill_width = text_surface.get_width() + self.PILL_PADDING_X * 2
            pill_rect = pygame.Rect(current_x, current_y, pill_width, self.PILL_HEIGHT)
            
            draw_pill(screen, pill_rect, generation_color, generation_color, generation_label, font)
            current_x = pill_rect.right + self.GAP_X
            row_height = max(row_height, self.PILL_HEIGHT)
        
        # Render Pokedex number pill
        if pokedex_number is not None:
            # Use darkened generation color or default
            if isinstance(generation, int) and 1 <= generation <= 9:
                base_color = GEN_COLOR_MAP.get(generation, (160, 160, 160))
                pill_color = darken_color(base_color, 0.75)
            else:
                pill_color = (160, 160, 160)
            
            # Format number (remove leading zeros)
            try:
                number_text = str(int(pokedex_number))
            except (ValueError, TypeError):
                number_text = str(pokedex_number).lstrip("0") or "0"
            
            text_surface = font.render(number_text, True, get_text_color(pill_color))
            pill_width = text_surface.get_width() + self.PILL_PADDING_X * 2
            pill_rect = pygame.Rect(current_x, current_y, pill_width, self.PILL_HEIGHT)
            
            draw_pill(screen, pill_rect, pill_color, pill_color, number_text, font)
            current_x = pill_rect.right + self.GAP_X
            row_height = max(row_height, self.PILL_HEIGHT)
        
        # Calculate TTS button position
        tts_button_rect = None
        if tts_button_callback and row_height > 0:
            target_height = max(24, int(row_height * 0.9))
            button_rect = pygame.Rect(0, 0, target_height, target_height)
            button_rect.centery = current_y + (row_height // 2)
            button_rect.left = current_x + 8
            
            # Ensure button fits in area
            if button_rect.right > area.right - 6:
                button_rect.right = area.right - 6
                button_rect.left = button_rect.right - target_height
            
            # Call the TTS button rendering callback
            tts_button_callback(screen, button_rect, target_height)
            tts_button_rect = button_rect
        
        return tts_button_rect, row_height
