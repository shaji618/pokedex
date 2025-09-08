from __future__ import annotations

import random

import pygame

from ..string_util import wrap_text


class DescriptionSection:
    """Renders Pokemon description and Pokedex entry text."""
    
    # Component constants
    LINE_HEIGHT_PADDING = 4
    MAX_LINES = 7
    TEXT_COLOR = (230, 230, 235)
    
    def __init__(self) -> None:
        self.pokedex_entry_cache: dict[str, str] = {}
    
    def render(
        self,
        screen: pygame.Surface,
        area: pygame.Rect,
        species: str,
        description: str,
        pokedex_entries: list[str],
        font: pygame.font.Font,
    ) -> None:
        """Render description and Pokedex entry text in the given area.
        
        Args:
            screen: Surface to render on
            area: Rectangle defining the render area
            species: Pokemon species name (for caching entry selection)
            description: Pokemon description text
            pokedex_entries: List of available Pokedex entries
            font: Font to use for text rendering
        """
        if area.width <= 0 or area.height <= 0:
            return
            
        # Get or cache a random Pokedex entry for this species
        entry = self._get_cached_pokedex_entry(species, pokedex_entries)
        
        # Combine description and entry
        combined_text = (description + (" " + entry if entry else "")).strip()
        
        if not combined_text:
            return
            
        # Calculate line spacing
        line_height = font.get_height() + self.LINE_HEIGHT_PADDING
        
        # Wrap text to fit area width
        lines = wrap_text(font, combined_text, area.width)
        
        # Render up to MAX_LINES
        y = area.top
        for index, line in enumerate(lines[:self.MAX_LINES]):
            if y + line_height > area.bottom:
                break
                
            text_surface = font.render(line, True, self.TEXT_COLOR)
            screen.blit(text_surface, (area.left, y))
            y += line_height
    
    def _get_cached_pokedex_entry(self, species: str, pokedex_entries: list[str]) -> str:
        """Get a cached random Pokedex entry for the species."""
        if species in self.pokedex_entry_cache:
            return self.pokedex_entry_cache[species]
        
        # Choose and cache a random entry
        if pokedex_entries:
            entry = random.choice(pokedex_entries).strip()
        else:
            entry = ""
            
        self.pokedex_entry_cache[species] = entry
        return entry
    
    def clear_cache(self) -> None:
        """Clear the Pokedex entry cache."""
        self.pokedex_entry_cache.clear()
