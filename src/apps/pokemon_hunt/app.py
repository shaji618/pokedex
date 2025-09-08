from __future__ import annotations

import logging
import math
import os
import random
import time
from enum import Enum

import pygame

from src.utils.audio_util import play_sfx, AudioChannel
from src.utils.focus_integration import FocusIntegrationMixin
from src.utils.focus_manager import FocusableElement, NavigationAction, NavigationResult
from src.utils.focus_renderer import FocusRenderer
from src.utils.image_util import load_image_safe
from src.utils.palette import VARIANT_COLOR_MAP
from src.utils.pill_util import draw_pill
from src.utils.pokemon_card import PokemonCard, _load_metadata
from src.utils.pokemon_image_util import images_root, index_images
from src.utils.pokemon_types import PokemonVariant, is_valid_variant
from .minigames import MiniGame, MiniGameResult, TimingChallenge, ColorDetection


logger = logging.getLogger(__name__)

# Game balance constants
POKEBALL_ATTEMPTS = 5
POKEMON_SPEED_MULTIPLIER = 2.0  # Adjust global speed (1.0 = use raw stats)
HIT_BOX_MULTIPLIER = 1.0  # Child-friendly enlarged hit box around actual Pokemon
TIME_LIMIT_MIN = 8  # seconds
TIME_LIMIT_MAX = 30  # seconds
POKEBALL_SPEED_MULTIPLIER = (
    1.2  # How much faster pokeball moves than fastest Pokemon (400 * 1.2 = 480 px/s)
)
POKEBALL_THROW_SPEED = -1200  # pixels per second for y-axis (upward is negative)
POKEBALL_SIZE = 36  # pokeball sprite size in pixels (scaled down from 512x512)
POKEMON_MIN_SPEED = 100  # minimum pixels per second
POKEMON_MAX_SPEED = 400  # maximum pixels per second
ESCAPE_SPEED_THRESHOLD = 120  # Pokemon with speed > this can escape after being caught
POKEMON_SUCK_DURATION = 0.08  # seconds for Pokemon to get sucked into pokeball (0.08 = 80ms)
VARIANT_ANNOUNCEMENT_DURATION = 2.0  # seconds to display variant announcement
POKEMON_AUDIO_MIN_INTERVAL = 0.5  # minimum seconds between Pokemon calls (500ms)
POKEMON_AUDIO_MAX_INTERVAL = 2.0  # maximum seconds between Pokemon calls (2000ms)
POKEMON_AUDIO_VOLUME = 0.7  # volume for Pokemon audio calls

APP_DATA = {
    "name": "Pokémon Hunt",
    "menu_icon_bg_color": (42, 117, 187),  # Official Pokemon blue
}


class GameState(Enum):
    VARIANT_ANNOUNCEMENT = "variant_announcement"  # Showing variant announcement
    AIMING = "aiming"  # Player positioning pokeball
    THROWING = "throwing"  # Pokeball in flight
    CONTACT_APPROACH = "contact_approach"  # Pokemon moving toward pokeball for natural contact
    MINIGAME = "minigame"  # Playing post-catch mini-game
    CAUGHT = "caught"  # Success - show Pokemon card
    MISSED = "missed"  # Pokeball missed, reset for next attempt
    ESCAPED = "escaped"  # Time up or no pokeballs - Pokemon escapes
    SMOKE_ANIMATION = "smoke"  # Playing smoke animation


class PokemonHuntApp(FocusIntegrationMixin):
    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen
        self.clock = pygame.time.Clock()
        self.running = True

        # Initialize focus system with invisible renderer (we handle our own UI)
        invisible_renderer = FocusRenderer(thickness=0, padding=0)
        self.init_focus_system(renderer=invisible_renderer)

        # Game state
        self.state = GameState.VARIANT_ANNOUNCEMENT  # Start with announcement if variants exist
        self.pokeballs_left = POKEBALL_ATTEMPTS
        self.time_limit = random.randint(TIME_LIMIT_MIN, TIME_LIMIT_MAX)  # Hidden from player
        self.start_time = time.time()

        # Variant announcement system
        self.announcement_start_time = 0.0
        self.announcement_message = ""

        # Pokemon audio system
        self.pokemon_audio_files: list[str] = []
        self.next_audio_time = 0.0

        # Screen setup (needed for Pokemon positioning)
        screen_height = screen.get_height()
        self.pokeball_launch_y = screen_height - 80  # Fixed launch position

        # Pokemon setup
        self.pokemon_species = self._select_random_pokemon()
        self.pokemon_sprite, self.pokemon_variants, self.pokemon_sprite_path = (
            self._load_pokemon_sprite()
        )
        self.pokemon_metadata = _load_metadata(self.pokemon_species)
        self.pokemon_speed = self.pokemon_metadata.get("speed", 50)
        self.pokemon_pos = self._get_random_pokemon_start_pos()
        self.pokemon_velocity = self._calculate_pokemon_velocity()
        self.pokemon_hit_box_cache: pygame.Rect | None = None

        # Pokemon animation system
        self.pokemon_frames: list[pygame.Surface] = []
        self.pokemon_frame_index = 0
        self.pokemon_frame_duration = 0.1  # Default 100ms per frame
        self.pokemon_last_frame_time = time.time()
        self._load_pokemon_animation_frames()

        # Load Pokemon audio files
        self.pokemon_audio_files = self._load_pokemon_audio_files()

        # Setup variant announcement
        if self.pokemon_variants:
            self.announcement_message = self._generate_variant_announcement_message(
                self.pokemon_variants
            )
            self.announcement_start_time = time.time()
            logger.info(f"Variant announcement: {self.announcement_message}")
        else:
            # No variants, start aiming immediately
            self.state = GameState.AIMING

        # Schedule first Pokemon audio call
        self._schedule_next_pokemon_audio()

        # Pokeball setup
        self.pokeball_pos = [screen.get_width() // 2, self.pokeball_launch_y]
        self.pokeball_velocity = [0, 0]
        self.pokeball_sprite = self._load_pokeball_sprite()

        # Assets
        self.background = self._load_random_background()
        self.smoke_frames: list[pygame.Surface] = []
        self.smoke_frame_index = 0
        self.smoke_start_time = 0.0
        self.smoke_pos = [0, 0]
        self.smoke_scale = 1.0
        self.escape_start_time = 0.0

        # Contact approach (Pokemon moves toward pokeball)
        self.approach_start_time = 0.0
        self.approach_duration = POKEMON_SUCK_DURATION  # Fast "sucking" animation
        self.approach_start_pos = [0, 0]  # Pokemon position when approach starts
        self.approach_target_pos = [0, 0]  # Where Pokemon should move to
        self.pokemon_alpha = 255  # Pokemon visibility (0=invisible, 255=fully visible)

        # Mini-game system
        self.current_minigame: MiniGame | None = None

        # Input handling
        self.keys_held: set[int] = set()

        # Debug options
        self.show_hit_boxes = False

        # Log game stats for debugging
        pokeball_calculated_speed = POKEMON_MAX_SPEED * POKEBALL_SPEED_MULTIPLIER
        logger.info(f"Pokemon Hunt started: {self.pokemon_species} (speed: {self.pokemon_speed})")
        logger.debug(
            f"Pokeball move speed: {pokeball_calculated_speed} px/s (vs max Pokemon: {POKEMON_MAX_SPEED} px/s)"
        )

    def _select_random_pokemon(self) -> str:
        """Select a random Pokemon from available data."""
        pairs = index_images(images_root())
        if not pairs:
            raise FileNotFoundError("No Pokemon data found")
        return random.choice(pairs)[0]

    def _restart_game(self) -> None:
        """Restart the game with new Pokemon, background, and reset stats."""
        logger.info("Restarting Pokemon Hunt game...")

        # Reset game state
        self.pokeballs_left = POKEBALL_ATTEMPTS
        self.time_limit = random.randint(TIME_LIMIT_MIN, TIME_LIMIT_MAX)
        self.start_time = time.time()

        # New Pokemon
        self.pokemon_species = self._select_random_pokemon()
        self.pokemon_sprite, self.pokemon_variants, self.pokemon_sprite_path = (
            self._load_pokemon_sprite()
        )
        self.pokemon_metadata = _load_metadata(self.pokemon_species)
        self.pokemon_speed = self.pokemon_metadata.get("speed", 50)
        self.pokemon_pos = self._get_random_pokemon_start_pos()
        self.pokemon_velocity = self._calculate_pokemon_velocity()
        self.pokemon_hit_box_cache = None

        # Reset Pokemon animation
        self.pokemon_frames = []
        self.pokemon_frame_index = 0
        self.pokemon_last_frame_time = time.time()
        self._load_pokemon_animation_frames()

        # Load Pokemon audio files
        self.pokemon_audio_files = self._load_pokemon_audio_files()

        # Setup variant announcement
        if self.pokemon_variants:
            self.announcement_message = self._generate_variant_announcement_message(
                self.pokemon_variants
            )
            self.announcement_start_time = time.time()
            self.state = GameState.VARIANT_ANNOUNCEMENT
            logger.info(f"Variant announcement: {self.announcement_message}")
        else:
            # No variants, start aiming immediately
            self.state = GameState.AIMING

        # Schedule first Pokemon audio call
        self._schedule_next_pokemon_audio()

        # Reset pokeball
        self.pokeball_pos = [self.screen.get_width() // 2, self.pokeball_launch_y]
        self.pokeball_velocity = [0, 0]

        # New background
        self.background = self._load_random_background()

        # Reset animations
        self.approach_start_time = 0.0
        self.approach_start_pos = [0, 0]
        self.approach_target_pos = [0, 0]
        self.pokemon_alpha = 255  # Reset to fully visible

        # Reset mini-game system
        if self.current_minigame is not None:
            if hasattr(self.current_minigame, "cleanup"):
                self.current_minigame.cleanup()
        self.current_minigame = None

        # Clear any existing timers
        pygame.time.set_timer(pygame.USEREVENT + 1, 0)
        pygame.time.set_timer(pygame.USEREVENT + 2, 0)

        self.smoke_frames = []
        self.smoke_frame_index = 0
        self.smoke_start_time = 0.0
        self.escape_start_time = 0.0

        logger.info(f"Game restarted with {self.pokemon_species} (speed: {self.pokemon_speed})")

    def _start_contact_approach(self) -> None:
        """Start Pokemon approach animation toward pokeball for natural contact."""
        self.state = GameState.CONTACT_APPROACH
        self.approach_start_time = time.time()

        # Store starting position for interpolation
        self.approach_start_pos = [self.pokemon_pos[0], self.pokemon_pos[1]]

        # Calculate where Pokemon should move to (near the pokeball for visual contact)
        pokeball_center_x = self.pokeball_pos[0] + (self.pokeball_sprite.get_width() // 2)
        pokeball_center_y = self.pokeball_pos[1] + (self.pokeball_sprite.get_height() // 2)

        # Find the visual Pokemon center (not the full sprite center)
        try:
            current_sprite = self._get_current_pokemon_sprite()
            alpha_array = pygame.surfarray.array_alpha(current_sprite)
            non_transparent = alpha_array > 0
            if non_transparent.any():
                y_indices, x_indices = non_transparent.nonzero()
                min_x, max_x = x_indices.min(), x_indices.max()
                min_y, max_y = y_indices.min(), y_indices.max()

                visual_center_x = self.pokemon_pos[0] + min_x + ((max_x - min_x) // 2)
                visual_center_y = self.pokemon_pos[1] + min_y + ((max_y - min_y) // 2)
            else:
                # Fallback to sprite center
                visual_center_x = self.pokemon_pos[0] + (current_sprite.get_width() // 2)
                visual_center_y = self.pokemon_pos[1] + (current_sprite.get_height() // 2)
        except Exception:
            # Fallback to sprite center
            current_sprite = self._get_current_pokemon_sprite()
            visual_center_x = self.pokemon_pos[0] + (current_sprite.get_width() // 2)
            visual_center_y = self.pokemon_pos[1] + (current_sprite.get_height() // 2)

        # Calculate approach target (Pokemon moves toward pokeball)
        dx = pokeball_center_x - visual_center_x
        dy = pokeball_center_y - visual_center_y
        distance = math.sqrt(dx * dx + dy * dy)

        if distance > 0:
            # Move Pokemon 70% of the way toward pokeball for natural contact
            approach_distance = distance * 0.7
            self.approach_target_pos = [
                self.pokemon_pos[0] + (dx / distance) * approach_distance,
                self.pokemon_pos[1] + (dy / distance) * approach_distance,
            ]
        else:
            self.approach_target_pos = [self.pokemon_pos[0], self.pokemon_pos[1]]

        logger.debug(
            f"Pokemon approach: {self.pokemon_pos} -> {[int(x) for x in self.approach_target_pos]}"
        )

    def update_contact_approach(self, _dt: float) -> None:
        """Update Pokemon approach animation toward pokeball."""
        if self.state != GameState.CONTACT_APPROACH:
            return

        elapsed = time.time() - self.approach_start_time

        if elapsed >= self.approach_duration:
            # Approach complete - start mini-game
            self._start_minigame()
            return

        # Fast "sucking" animation toward pokeball
        progress = elapsed / self.approach_duration
        progress = min(1.0, progress)  # Clamp to 1.0

        # Accelerated movement (ease-in for sucking effect)
        accelerated_progress = progress * progress * progress  # Cubic acceleration

        # Linear interpolation from start position to approach target
        start_x, start_y = self.approach_start_pos[0], self.approach_start_pos[1]
        target_x, target_y = self.approach_target_pos[0], self.approach_target_pos[1]

        self.pokemon_pos[0] = start_x + (target_x - start_x) * accelerated_progress
        self.pokemon_pos[1] = start_y + (target_y - start_y) * accelerated_progress

        # Fade out Pokemon sprite during sucking (disappear effect)
        self.pokemon_alpha = int(255 * (1.0 - progress))  # Fade from 255 to 0

    def update_variant_announcement(self, _dt: float) -> None:
        """Update variant announcement phase."""
        if self.state != GameState.VARIANT_ANNOUNCEMENT:
            return

        elapsed = time.time() - self.announcement_start_time
        if elapsed >= VARIANT_ANNOUNCEMENT_DURATION:
            # Announcement complete - start aiming
            self.state = GameState.AIMING
            logger.debug("Variant announcement complete, starting hunt phase")

    def update_pokemon_audio(self, _dt: float) -> None:
        """Update Pokemon audio calls during hunt phases."""
        if self.state not in [GameState.AIMING, GameState.THROWING]:
            return

        current_time = time.time()
        if current_time >= self.next_audio_time:
            self._play_random_pokemon_audio()

    def _load_pokemon_sprite(self) -> tuple[pygame.Surface, list[str], str]:
        """Load the sprite for the current Pokemon, prioritizing hunt_assets.

        Returns: (sprite_surface, variant_list, sprite_path)
        """
        # First check hunt_assets directory
        hunt_assets_path = os.path.join(str(images_root()), self.pokemon_species, "hunt_assets")
        if os.path.exists(hunt_assets_path):
            image_files = [
                f
                for f in os.listdir(hunt_assets_path)
                if f.lower().endswith((".png", ".gif", ".jpg", ".jpeg"))
            ]

            if image_files:
                # Randomly select one of the available images
                chosen_file = random.choice(image_files)
                sprite_path = os.path.join(hunt_assets_path, chosen_file)
                sprite = load_image_safe(sprite_path, convert_alpha=True)

                if sprite is not None:
                    # Parse variants from filename
                    variants = self._parse_variants_from_filename(chosen_file)
                    logger.debug(f"Loaded hunt asset: {chosen_file}, variants: {variants}")
                    return sprite, variants, sprite_path

        # Fallback to original sprite.png
        sprite_path = os.path.join(str(images_root()), self.pokemon_species, "sprite.png")
        sprite = load_image_safe(sprite_path, convert_alpha=True)
        if sprite is None:
            raise FileNotFoundError(f"Could not load sprite: {sprite_path}")

        return sprite, [], sprite_path  # No variants for fallback sprite

    def _parse_variants_from_filename(self, filename: str) -> list[str]:
        """Parse variant modifiers from a filename.

        Example: "charizard_shiny_mega.png" -> ["shiny", "mega"]
        """
        # Remove file extension and the base pokemon name
        name_without_ext = os.path.splitext(filename)[0]

        # Split by underscores and remove the first part (pokemon name)
        parts = name_without_ext.split("_")
        if len(parts) <= 1:
            return []

        # Extract valid variants (skip the first part which is the pokemon name)
        variants = []
        for part in parts[1:]:
            part_lower = part.lower()

            # Handle common filename aliases
            normalized_part = part_lower
            if part_lower == "f":
                normalized_part = "female"
            elif part_lower == "m":
                normalized_part = "male"
            elif part_lower == "gmax":
                normalized_part = "gigantamax"
            elif part_lower in ["alola", "galar", "hisui", "paldea"]:
                # Convert region names to their adjective form
                normalized_part = part_lower + "n"

            # Check if it's a valid variant using the enum
            if is_valid_variant(normalized_part):
                variants.append(normalized_part)

        return variants

    def _load_pokemon_audio_files(self) -> list[str]:
        """Load all available audio files for the current Pokemon."""
        audio_files = []

        # Check hunt_assets directory for audio files
        hunt_assets_path = os.path.join(str(images_root()), self.pokemon_species, "hunt_assets")
        if os.path.exists(hunt_assets_path):
            for filename in os.listdir(hunt_assets_path):
                if filename.lower().endswith((".mp3", ".wav", ".ogg")):
                    audio_files.append(os.path.join(hunt_assets_path, filename))

        # Check for anime_cry.wav in species directory
        anime_cry_path = os.path.join(str(images_root()), self.pokemon_species, "anime_cry.wav")
        if os.path.exists(anime_cry_path):
            audio_files.append(anime_cry_path)

        logger.debug(f"Found {len(audio_files)} audio files for {self.pokemon_species}")
        return audio_files

    def _generate_variant_announcement_message(self, variants: list[str]) -> str:
        """Generate an exciting announcement message for Pokemon variants."""
        if not variants:
            return ""

        # Special combinations
        if PokemonVariant.SHINY.value in variants and any(
            v in variants
            for v in [
                PokemonVariant.MEGA.value,
                PokemonVariant.MEGAX.value,
                PokemonVariant.MEGAY.value,
            ]
        ):
            return "IT'S A SHINY MEGA!"
        elif PokemonVariant.SHINY.value in variants:
            return "IT'S SHINY!"
        elif any(
            v in variants
            for v in [
                PokemonVariant.MEGA.value,
                PokemonVariant.MEGAX.value,
                PokemonVariant.MEGAY.value,
            ]
        ):
            return "A MEGA POKEMON!"
        elif PokemonVariant.GIGANTAMAX.value in variants:
            return "A GIGANTAMAX POKEMON!"
        elif PokemonVariant.PRIMAL.value in variants:
            return "A PRIMAL POKEMON!"
        elif any(
            v in variants
            for v in [
                PokemonVariant.ALOLAN.value,
                PokemonVariant.GALARIAN.value,
                PokemonVariant.HISUIAN.value,
                PokemonVariant.PALDEAN.value,
            ]
        ):
            # Find the regional variant
            for region_variant in [
                PokemonVariant.ALOLAN,
                PokemonVariant.GALARIAN,
                PokemonVariant.HISUIAN,
                PokemonVariant.PALDEAN,
            ]:
                if region_variant.value in variants:
                    return f"A {region_variant.value.upper()} POKEMON!"
        elif PokemonVariant.FEMALE.value in variants:
            return "A FEMALE POKEMON!"
        elif PokemonVariant.SHADOW.value in variants:
            return "A SHADOW POKEMON!"

        # Default for other variants
        variant_text = " ".join(variants).upper()
        return f"A {variant_text} POKEMON!"

    def _schedule_next_pokemon_audio(self) -> None:
        """Schedule the next Pokemon audio call."""
        interval = random.uniform(POKEMON_AUDIO_MIN_INTERVAL, POKEMON_AUDIO_MAX_INTERVAL)
        self.next_audio_time = time.time() + interval

    def _play_random_pokemon_audio(self) -> None:
        """Play a random Pokemon audio file if available."""
        if not self.pokemon_audio_files:
            return

        audio_file = random.choice(self.pokemon_audio_files)
        success = play_sfx(audio_file, volume=POKEMON_AUDIO_VOLUME, channel_name=AudioChannel.CRY)
        if success:
            logger.debug(f"Playing Pokemon audio: {os.path.basename(audio_file)}")

        # Schedule next audio call
        self._schedule_next_pokemon_audio()

    def _load_pokemon_animation_frames(self) -> None:
        """Load animation frames from the Pokemon sprite if it's a GIF."""
        if not self.pokemon_sprite_path or not self.pokemon_sprite_path.lower().endswith(".gif"):
            # Not a GIF, use single frame
            self.pokemon_frames = [self.pokemon_sprite]
            return

        if not os.path.exists(self.pokemon_sprite_path):
            self.pokemon_frames = [self.pokemon_sprite]
            return

        try:
            # Load GIF frames using PIL (similar to smoke animation)
            from PIL import Image

            gif = Image.open(self.pokemon_sprite_path)
            frames = []
            frame_durations = []

            # Extract all frames from the GIF
            try:
                while True:
                    # Get frame duration if available
                    duration = gif.info.get("duration", 100)  # Default 100ms
                    frame_durations.append(duration / 1000.0)  # Convert to seconds

                    # Convert PIL image to pygame surface
                    mode = gif.mode
                    size = gif.size
                    data = gif.tobytes()

                    # Create pygame surface from PIL data
                    if mode == "RGBA" or mode == "RGB":
                        pygame_surface = pygame.image.fromstring(data, size, mode)
                    elif mode == "P":
                        # Convert palette mode to RGBA
                        gif_rgba = gif.convert("RGBA")
                        data = gif_rgba.tobytes()
                        pygame_surface = pygame.image.fromstring(data, size, "RGBA")
                    else:
                        # Fallback: convert to RGBA
                        gif_rgba = gif.convert("RGBA")
                        data = gif_rgba.tobytes()
                        pygame_surface = pygame.image.fromstring(data, size, "RGBA")

                    frames.append(pygame_surface.convert_alpha())
                    gif.seek(gif.tell() + 1)

            except EOFError:
                pass  # End of GIF frames

            if frames:
                self.pokemon_frames = frames
                # Use average frame duration, or default if durations are inconsistent
                if frame_durations:
                    self.pokemon_frame_duration = sum(frame_durations) / len(frame_durations)
                else:
                    self.pokemon_frame_duration = 0.1  # Default 100ms

                logger.debug(f"Loaded {len(frames)} animation frames for {self.pokemon_species}")
            else:
                logger.warning("No frames found in Pokemon GIF")
                self.pokemon_frames = [self.pokemon_sprite]

        except Exception as e:
            logger.warning(f"Could not load Pokemon GIF animation: {e}")
            # Fallback to single frame
            self.pokemon_frames = [self.pokemon_sprite]

    def update_pokemon_animation(self, _dt: float) -> None:
        """Update Pokemon sprite animation."""
        if len(self.pokemon_frames) <= 1:
            return  # No animation needed

        current_time = time.time()
        if current_time - self.pokemon_last_frame_time >= self.pokemon_frame_duration:
            self.pokemon_frame_index = (self.pokemon_frame_index + 1) % len(self.pokemon_frames)
            self.pokemon_last_frame_time = current_time

    def _get_current_pokemon_sprite(self) -> pygame.Surface:
        """Get the current frame of the Pokemon sprite animation."""
        if not self.pokemon_frames:
            return self.pokemon_sprite

        return self.pokemon_frames[self.pokemon_frame_index]

    def _load_pokeball_sprite(self) -> pygame.Surface:
        """Load the pokeball sprite and scale to appropriate size."""
        pokeball_path = os.path.join(os.path.dirname(__file__), "assets", "pokeball.png")
        sprite = load_image_safe(pokeball_path, convert_alpha=True)
        if sprite is None:
            raise FileNotFoundError(f"Could not load pokeball: {pokeball_path}")

        # Scale pokeball to be similar size to Pokemon
        target_size = POKEBALL_SIZE
        current_size = max(sprite.get_size())
        scale_factor = target_size / current_size
        new_width = int(sprite.get_width() * scale_factor)
        new_height = int(sprite.get_height() * scale_factor)

        return pygame.transform.smoothscale(sprite, (new_width, new_height))

    def _load_random_background(self) -> pygame.Surface:
        """Load a random background from assets."""
        backgrounds_dir = os.path.join(os.path.dirname(__file__), "assets", "backgrounds")
        if not os.path.exists(backgrounds_dir):
            # Create a simple background if none available
            background = pygame.Surface(self.screen.get_size())
            background.fill((135, 206, 235))  # Sky blue
            return background

        background_files = [
            f for f in os.listdir(backgrounds_dir) if f.lower().endswith((".jpg", ".png"))
        ]
        if not background_files:
            background = pygame.Surface(self.screen.get_size())
            background.fill((135, 206, 235))  # Sky blue
            return background

        chosen_bg = random.choice(background_files)
        bg_path = os.path.join(backgrounds_dir, chosen_bg)
        background = load_image_safe(bg_path, convert_alpha=False)

        if background is None:
            background = pygame.Surface(self.screen.get_size())
            background.fill((135, 206, 235))  # Sky blue
        else:
            # Scale to screen size
            background = pygame.transform.smoothscale(background, self.screen.get_size())

        return background

    def _load_smoke_frames(self) -> None:
        """Load actual smoke.gif animation frames."""
        if self.smoke_frames:  # Already loaded
            return

        smoke_path = os.path.join(os.path.dirname(__file__), "assets", "smoke.gif")
        if not os.path.exists(smoke_path):
            logger.warning(f"Smoke GIF not found: {smoke_path}")
            return

        try:
            # Load GIF frames using PIL
            from PIL import Image

            gif = Image.open(smoke_path)
            frames = []

            # Extract all frames from the GIF
            try:
                while True:
                    # Convert PIL image to pygame surface
                    mode = gif.mode
                    size = gif.size
                    data = gif.tobytes()

                    # Create pygame surface from PIL data
                    if mode == "RGBA" or mode == "RGB":
                        pygame_surface = pygame.image.fromstring(data, size, mode)
                    elif mode == "P":
                        # Convert palette mode to RGBA
                        gif_rgba = gif.convert("RGBA")
                        data = gif_rgba.tobytes()
                        pygame_surface = pygame.image.fromstring(data, size, "RGBA")
                    else:
                        # Fallback: convert to RGBA
                        gif_rgba = gif.convert("RGBA")
                        data = gif_rgba.tobytes()
                        pygame_surface = pygame.image.fromstring(data, size, "RGBA")

                    frames.append(pygame_surface.convert_alpha())
                    gif.seek(gif.tell() + 1)

            except EOFError:
                pass  # End of GIF frames

            if frames:
                self.smoke_frames = frames
                logger.debug(f"Loaded {len(frames)} smoke animation frames")
            else:
                logger.warning("No frames found in smoke.gif")

        except Exception as e:
            logger.warning(f"Could not load smoke.gif: {e}")
            # Fallback to simple effect if GIF loading fails
            self._create_fallback_smoke()

    def _create_fallback_smoke(self) -> None:
        """Create simple smoke animation as fallback."""
        for i in range(10):
            frame = pygame.Surface((80, 80), pygame.SRCALPHA)
            alpha = max(50, 200 - (i * 20))
            radius = 20 + (i * 3)
            color = (128, 128, 128)
            pygame.draw.circle(frame, color, (40, 40), radius)
            frame.set_alpha(alpha)
            self.smoke_frames.append(frame)

    def _get_random_pokemon_start_pos(self) -> list[float]:
        """Get a random starting position for Pokemon (avoiding pokeball area)."""
        screen_width, screen_height = self.screen.get_size()

        # Use current animated sprite dimensions (or fallback to static sprite)
        current_sprite = (
            self._get_current_pokemon_sprite()
            if hasattr(self, "pokemon_frames") and self.pokemon_frames
            else self.pokemon_sprite
        )
        sprite_width, sprite_height = current_sprite.get_size()

        # Keep Pokemon above the pokeball launch area
        max_y = self.pokeball_launch_y - sprite_height - 50

        x = random.randint(0, max(0, screen_width - sprite_width))
        y = random.randint(0, max(0, max_y))

        return [float(x), float(y)]

    def _calculate_pokemon_velocity(self) -> list[float]:
        """Convert Pokemon speed stat to pixel velocity with DVD bounce style."""
        # Map speed stat (5-180) to pixel velocity (100-400 pixels/second)
        normalized_speed = self.pokemon_speed / 180.0
        base_speed = POKEMON_MIN_SPEED + (
            normalized_speed * (POKEMON_MAX_SPEED - POKEMON_MIN_SPEED)
        )
        final_speed = base_speed * POKEMON_SPEED_MULTIPLIER

        # Random direction for DVD-style bouncing
        angle = random.uniform(0, 2 * math.pi)
        vx = final_speed * 0.8 * math.cos(angle)
        vy = final_speed * 0.8 * math.sin(angle)

        return [vx, vy]

    def _calculate_pokemon_hit_box(self) -> pygame.Rect:
        """Calculate hit box based on actual Pokemon content, not full sprite."""
        if self.pokemon_hit_box_cache is not None:
            # Update position but keep the cached relative offset and size
            return pygame.Rect(
                int(self.pokemon_pos[0]) + self.pokemon_hit_box_cache.x,
                int(self.pokemon_pos[1]) + self.pokemon_hit_box_cache.y,
                self.pokemon_hit_box_cache.width,
                self.pokemon_hit_box_cache.height,
            )

        try:
            # Use current animated frame for hit box calculation
            current_sprite = self._get_current_pokemon_sprite()

            # Get actual Pokemon bounds (non-transparent pixels)
            alpha_array = pygame.surfarray.array_alpha(current_sprite)
            non_transparent = alpha_array > 0

            if not non_transparent.any():
                # Fallback to full sprite if no transparency data
                hit_box = pygame.Rect(
                    int(self.pokemon_pos[0]),
                    int(self.pokemon_pos[1]),
                    current_sprite.get_width(),
                    current_sprite.get_height(),
                )
                self.pokemon_hit_box_cache = hit_box
                return hit_box

            # Find actual content bounds
            y_indices, x_indices = non_transparent.nonzero()
            min_x, max_x = x_indices.min(), x_indices.max()
            min_y, max_y = y_indices.min(), y_indices.max()

            actual_w = max_x - min_x + 1
            actual_h = max_y - min_y + 1

            # Apply child-friendly multiplier to actual content
            hit_w = int(actual_w * HIT_BOX_MULTIPLIER)
            hit_h = int(actual_h * HIT_BOX_MULTIPLIER)

            # Center the hit box on the actual Pokemon content
            content_center_x = int(self.pokemon_pos[0] + min_x + (actual_w // 2))
            content_center_y = int(self.pokemon_pos[1] + min_y + (actual_h // 2))

            hit_box = pygame.Rect(
                content_center_x - (hit_w // 2), content_center_y - (hit_h // 2), hit_w, hit_h
            )

            # Cache the relative position
            self.pokemon_hit_box_cache = pygame.Rect(
                hit_box.x - int(self.pokemon_pos[0]),
                hit_box.y - int(self.pokemon_pos[1]),
                hit_box.width,
                hit_box.height,
            )

            return hit_box

        except Exception as e:
            logger.warning(f"Error calculating hit box for {self.pokemon_species}: {e}")
            # Fallback to full sprite
            current_sprite = self._get_current_pokemon_sprite()
            hit_box = pygame.Rect(
                int(self.pokemon_pos[0]),
                int(self.pokemon_pos[1]),
                current_sprite.get_width(),
                current_sprite.get_height(),
            )
            return hit_box

    def _get_pokeball_hit_box(self) -> pygame.Rect:
        """Get generous hit box for pokeball."""
        pokeball_w, pokeball_h = self.pokeball_sprite.get_size()

        # Make pokeball hit box slightly larger for child-friendliness
        hit_w = int(pokeball_w * 1.2)
        hit_h = int(pokeball_h * 1.2)

        return pygame.Rect(
            int(self.pokeball_pos[0]) - ((hit_w - pokeball_w) // 2),
            int(self.pokeball_pos[1]) - ((hit_h - pokeball_h) // 2),
            hit_w,
            hit_h,
        )

    def update_pokemon_movement(self, dt: float) -> None:
        """Pokemon bounces around screen like DVD screensaver."""
        if self.state not in [GameState.AIMING, GameState.THROWING]:
            return

        screen_width, screen_height = self.screen.get_size()

        # Use current animated sprite dimensions
        current_sprite = self._get_current_pokemon_sprite()
        sprite_width, sprite_height = current_sprite.get_size()

        # Update position
        self.pokemon_pos[0] += self.pokemon_velocity[0] * dt
        self.pokemon_pos[1] += self.pokemon_velocity[1] * dt

        # Bounce off walls (x-axis)
        if self.pokemon_pos[0] <= 0:
            self.pokemon_pos[0] = 0
            self.pokemon_velocity[0] = abs(self.pokemon_velocity[0])  # Bounce right
        elif self.pokemon_pos[0] + sprite_width >= screen_width:
            self.pokemon_pos[0] = screen_width - sprite_width
            self.pokemon_velocity[0] = -abs(self.pokemon_velocity[0])  # Bounce left

        # Bounce off top and cannot go below pokeball launch line
        min_y = 0
        max_y = min(screen_height - sprite_height, self.pokeball_launch_y - sprite_height - 20)

        if self.pokemon_pos[1] <= min_y:
            self.pokemon_pos[1] = min_y
            self.pokemon_velocity[1] = abs(self.pokemon_velocity[1])  # Bounce down
        elif self.pokemon_pos[1] >= max_y:
            self.pokemon_pos[1] = max_y
            self.pokemon_velocity[1] = -abs(self.pokemon_velocity[1])  # Bounce up

    def handle_pokeball_aiming(self, dt: float) -> None:
        """Smooth x-axis movement when holding arrow keys."""
        if self.state != GameState.AIMING:
            return

        screen_width = self.screen.get_width()
        pokeball_width = self.pokeball_sprite.get_width()

        # Calculate pokeball speed based on max Pokemon speed
        pokeball_move_speed = POKEMON_MAX_SPEED * POKEBALL_SPEED_MULTIPLIER

        # Smooth movement based on held keys
        if pygame.K_LEFT in self.keys_held:
            self.pokeball_pos[0] -= pokeball_move_speed * dt
        if pygame.K_RIGHT in self.keys_held:
            self.pokeball_pos[0] += pokeball_move_speed * dt

        # Clamp to screen bounds
        self.pokeball_pos[0] = max(0, min(screen_width - pokeball_width, self.pokeball_pos[0]))

    def throw_pokeball(self) -> None:
        """Launch pokeball towards Pokemon intercept point."""
        if self.state != GameState.AIMING or self.pokeballs_left <= 0:
            return

        self.state = GameState.THROWING
        self.pokeballs_left -= 1

        # Simple upward velocity - player must predict intercept
        self.pokeball_velocity = [0, POKEBALL_THROW_SPEED]

        logger.debug(
            f"Pokeball thrown from x={int(self.pokeball_pos[0])}, {self.pokeballs_left} remaining"
        )

    def update_pokeball_throw(self, dt: float) -> None:
        """Update pokeball position during throw."""
        if self.state != GameState.THROWING:
            return

        self.pokeball_pos[1] += self.pokeball_velocity[1] * dt

        # Check if pokeball left screen (missed)
        if self.pokeball_pos[1] < -50:
            self._handle_miss()

    def check_collision(self) -> bool:
        """Check if pokeball and Pokemon collide using child-friendly hit boxes."""
        if self.state != GameState.THROWING:
            return False

        pokemon_hit_box = self._calculate_pokemon_hit_box()
        pokeball_hit_box = self._get_pokeball_hit_box()

        if pokeball_hit_box.colliderect(pokemon_hit_box):
            logger.debug(f"COLLISION! Pokeball: {pokeball_hit_box}, Pokemon: {pokemon_hit_box}")
            # Stop pokeball and start Pokemon approach sequence
            self.pokeball_velocity = [0, 0]  # Stop vertical movement
            self._start_contact_approach()
            return True

        return False

    def check_time_limit(self) -> bool:
        """Check if time limit has been exceeded."""
        if self.state in [
            GameState.CAUGHT,
            GameState.ESCAPED,
            GameState.SMOKE_ANIMATION,
            GameState.MINIGAME,
            GameState.VARIANT_ANNOUNCEMENT,
        ]:
            return False

        elapsed = time.time() - self.start_time
        # Adjust for announcement time if it occurred
        if self.pokemon_variants and self.announcement_start_time > 0:
            elapsed -= VARIANT_ANNOUNCEMENT_DURATION

        if elapsed >= self.time_limit:
            self._handle_escape()
            return True

        return False

    def _start_minigame(self) -> None:
        """Start a post-catch mini-game for Pokemon capture."""
        self.state = GameState.MINIGAME

        # Keep Pokemon invisible (already sucked into pokeball)
        self.pokemon_alpha = 0

        # Get Pokemon types for color detection mini-game
        pokemon_types = self.pokemon_metadata.get("types", ["normal"])

        # Randomly select between available mini-games
        minigame_choice = random.choice(["timing", "color"])

        if minigame_choice == "timing":
            self.current_minigame = TimingChallenge(
                self.screen, self.pokemon_species, self.pokemon_speed, self.pokeball_sprite
            )
            logger.info(f"Starting timing challenge mini-game for {self.pokemon_species}")
        else:  # color
            self.current_minigame = ColorDetection(
                self.screen, self.pokemon_species, self.pokemon_speed, pokemon_types
            )
            logger.info(
                f"Starting color detection mini-game for {self.pokemon_species} (types: {pokemon_types})"
            )

        self.current_minigame.start()

    def update_minigame(self, dt: float) -> None:
        """Update the current mini-game."""
        if self.state != GameState.MINIGAME or self.current_minigame is None:
            return

        self.current_minigame.update(dt)

        # Check if mini-game is complete
        if self.current_minigame.is_complete():
            result = self.current_minigame.get_result()
            if result == MiniGameResult.SUCCESS:
                self._handle_catch()
            else:
                self._handle_escape()

    def _handle_catch(self) -> None:
        """Handle successful Pokemon catch after mini-game."""
        self.state = GameState.CAUGHT
        logger.info(f"Pokemon {self.pokemon_species} caught successfully!")

        # Clear the mini-game
        if self.current_minigame is not None:
            if hasattr(self.current_minigame, "cleanup"):
                self.current_minigame.cleanup()
        self.current_minigame = None

        # Show Pokemon card
        card_app = PokemonCard(self.screen, self.pokemon_species)
        result = card_app.run_modal()

        # Handle card result
        if result == NavigationAction.EXIT_TO_PARENT:  # BACKSPACE pressed
            logger.info("Backspace pressed in card - starting new hunt!")
            self._restart_game()
        else:  # ESC or other - exit to launcher
            logger.info("Exiting to launcher from Pokemon card")
            self.running = False

    def _handle_miss(self) -> None:
        """Pokeball missed."""
        if self.pokeballs_left > 0:
            # Reset for next attempt
            self.state = GameState.AIMING
            self.pokeball_pos = [self.pokeball_pos[0], self.pokeball_launch_y]
            self.pokeball_velocity = [0, 0]
            logger.debug("Pokeball missed, trying again")
        else:
            # No pokeballs left
            self._handle_escape()

    def _handle_escape(self) -> None:
        """Time up or no pokeballs - Pokemon escapes."""
        # Clear any active mini-game
        if self.current_minigame is not None:
            if hasattr(self.current_minigame, "cleanup"):
                self.current_minigame.cleanup()
        self.current_minigame = None

        screen_width = self.screen.get_width()
        current_sprite = self._get_current_pokemon_sprite()
        pokemon_center_x = self.pokemon_pos[0] + (current_sprite.get_width() // 2)

        # Check if Pokemon is near screen edge
        edge_threshold = 100
        near_left_edge = pokemon_center_x < edge_threshold
        near_right_edge = pokemon_center_x > screen_width - edge_threshold

        if near_left_edge or near_right_edge:
            # Speed up Pokemon to exit off screen in 1 second
            self._animate_pokemon_escape()
        else:
            # Show smoke animation
            self._start_smoke_animation()

    def _animate_pokemon_escape(self) -> None:
        """Animate Pokemon escaping off screen."""
        self.state = GameState.ESCAPED
        screen_width = self.screen.get_width()
        current_sprite = self._get_current_pokemon_sprite()
        pokemon_center_x = self.pokemon_pos[0] + (current_sprite.get_width() // 2)

        # Determine escape direction and speed up
        if pokemon_center_x < screen_width // 2:
            # Escape left
            escape_distance = self.pokemon_pos[0] + current_sprite.get_width()
            self.pokemon_velocity[0] = -escape_distance  # Exit in 1 second
        else:
            # Escape right
            escape_distance = screen_width - self.pokemon_pos[0]
            self.pokemon_velocity[0] = escape_distance  # Exit in 1 second

        # Reduce vertical movement
        self.pokemon_velocity[1] *= 0.3

        logger.info(f"Pokemon {self.pokemon_species} escaped off screen!")

        # Set timer for escape animation
        self.escape_start_time = time.time()

    def _start_smoke_animation(self) -> None:
        """Start smoke animation where Pokemon was."""
        self.state = GameState.SMOKE_ANIMATION
        # Center smoke animation on Pokemon position
        # Scale smoke to be reasonable size (smoke.gif is 900x540, too big)
        smoke_scale = 0.3  # Scale down the large GIF
        smoke_width = int(900 * smoke_scale)  # 270px
        smoke_height = int(540 * smoke_scale)  # 162px

        current_sprite = self._get_current_pokemon_sprite()
        self.smoke_pos = [
            int(self.pokemon_pos[0] + current_sprite.get_width() // 2 - smoke_width // 2),
            int(self.pokemon_pos[1] + current_sprite.get_height() // 2 - smoke_height // 2),
        ]
        self.smoke_scale = smoke_scale  # Store for rendering
        self.smoke_start_time = time.time()
        self.smoke_frame_index = 0

        # Load smoke frames if not already loaded
        self._load_smoke_frames()

        logger.info(f"Pokemon {self.pokemon_species} disappeared in smoke!")

    def update_escape_animation(self, dt: float) -> None:
        """Update Pokemon escape animation."""
        if self.state != GameState.ESCAPED:
            return

        # Continue Pokemon movement for escape
        self.update_pokemon_movement(dt)

        # Check if escape animation is complete
        if time.time() - self.escape_start_time > 1.5:  # 1.5 seconds total
            logger.info("Pokemon escaped! Starting new hunt...")
            self._restart_game()

    def update_smoke_animation(self, _dt: float) -> None:
        """Update smoke animation."""
        if self.state != GameState.SMOKE_ANIMATION:
            return

        if not self.smoke_frames:
            # No smoke frames available, just wait briefly
            if time.time() - self.smoke_start_time > 1.0:
                logger.info("Pokemon vanished in smoke! Starting new hunt...")
                self._restart_game()
            return

        # Animate smoke frames (faster for game pace)
        frames_per_second = 20
        elapsed = time.time() - self.smoke_start_time
        target_frame = int(elapsed * frames_per_second)

        if target_frame >= len(self.smoke_frames):
            # Animation complete
            logger.info("Pokemon vanished in smoke! Starting new hunt...")
            self._restart_game()
        else:
            self.smoke_frame_index = target_frame

    def render(self) -> None:
        """Render all game elements."""
        # Background
        self.screen.blit(self.background, (0, 0))

        # Debug hit boxes
        if self.show_hit_boxes:
            self._render_hit_boxes()

        # Pokemon (unless in smoke animation)
        if self.state != GameState.SMOKE_ANIMATION:
            # Get current animated frame
            current_pokemon_sprite = self._get_current_pokemon_sprite()

            if self.pokemon_alpha < 255:
                # Apply fade-out effect during sucking animation
                pokemon_surface = current_pokemon_sprite.copy()
                pokemon_surface.set_alpha(self.pokemon_alpha)
                self.screen.blit(
                    pokemon_surface, (int(self.pokemon_pos[0]), int(self.pokemon_pos[1]))
                )
            else:
                # Normal rendering (fully visible)
                self.screen.blit(
                    current_pokemon_sprite, (int(self.pokemon_pos[0]), int(self.pokemon_pos[1]))
                )

        # Smoke animation
        if self.state == GameState.SMOKE_ANIMATION and self.smoke_frames:
            if 0 <= self.smoke_frame_index < len(self.smoke_frames):
                smoke_frame = self.smoke_frames[self.smoke_frame_index]

                # Scale smoke frame if needed (smoke.gif is 900x540, too big)
                if self.smoke_scale != 1.0:
                    original_size = smoke_frame.get_size()
                    new_size = (
                        int(original_size[0] * self.smoke_scale),
                        int(original_size[1] * self.smoke_scale),
                    )
                    smoke_frame = pygame.transform.smoothscale(smoke_frame, new_size)

                self.screen.blit(smoke_frame, self.smoke_pos)

        # Pokeball (unless escaped or in smoke)
        if self.state not in [GameState.ESCAPED, GameState.SMOKE_ANIMATION]:
            self.screen.blit(
                self.pokeball_sprite, (int(self.pokeball_pos[0]), int(self.pokeball_pos[1]))
            )

        # Mini-game rendering
        if self.state == GameState.MINIGAME and self.current_minigame is not None:
            self.current_minigame.render()

        # UI Elements
        self._render_pokeball_counter()
        self._render_variant_pills()

        # Overlay elements (drawn last)
        self._render_variant_announcement()

        pygame.display.flip()

    def _render_hit_boxes(self) -> None:
        """Debug: Show the hit boxes."""
        if self.state in [GameState.AIMING, GameState.THROWING]:
            # Pokemon hit box (green)
            pokemon_box = self._calculate_pokemon_hit_box()
            pygame.draw.rect(self.screen, (0, 255, 0), pokemon_box, width=2)

            # Pokeball hit box (blue)
            pokeball_box = self._get_pokeball_hit_box()
            pygame.draw.rect(self.screen, (0, 150, 255), pokeball_box, width=2)

    def _render_pokeball_counter(self) -> None:
        """Show pokeball icon + count using system font."""
        font = pygame.font.Font(None, 36)  # System font

        # Small pokeball icon for counter
        icon_size = 28
        small_pokeball = pygame.transform.scale(self.pokeball_sprite, (icon_size, icon_size))

        # Text with shadow for visibility
        text_color = (255, 255, 255)
        shadow_color = (0, 0, 0)
        text = font.render(str(self.pokeballs_left), True, text_color)
        shadow = font.render(str(self.pokeballs_left), True, shadow_color)

        # Position in top-left
        margin = 20

        # Draw shadow first
        self.screen.blit(shadow, (margin + icon_size + 10 + 2, margin + 2))
        self.screen.blit(small_pokeball, (margin, margin))
        self.screen.blit(text, (margin + icon_size + 10, margin))

    def _render_variant_announcement(self) -> None:
        """Render the variant announcement message."""
        if self.state != GameState.VARIANT_ANNOUNCEMENT or not self.announcement_message:
            return

        # Large, dramatic text
        font_large = pygame.font.Font(None, 72)
        font_medium = pygame.font.Font(None, 48)

        # Main announcement text
        text_color = (255, 255, 255)
        shadow_color = (0, 0, 0)
        outline_color = (
            (255, 215, 0) if "shiny" in self.announcement_message.lower() else (138, 43, 226)
        )

        # Create text with multiple layers for dramatic effect
        text_surface = font_large.render(self.announcement_message, True, text_color)
        shadow_surface = font_large.render(self.announcement_message, True, shadow_color)

        # Center on screen
        screen_center = (self.screen.get_width() // 2, self.screen.get_height() // 2)
        text_rect = text_surface.get_rect(center=screen_center)

        # Create animated effect based on elapsed time
        elapsed = time.time() - self.announcement_start_time
        pulse_factor = 1.0 + 0.1 * math.sin(elapsed * 8)  # Pulsing effect

        # Scale text for pulse effect
        scaled_width = int(text_surface.get_width() * pulse_factor)
        scaled_height = int(text_surface.get_height() * pulse_factor)

        if scaled_width > 0 and scaled_height > 0:
            scaled_text = pygame.transform.smoothscale(text_surface, (scaled_width, scaled_height))
            scaled_shadow = pygame.transform.smoothscale(
                shadow_surface, (scaled_width, scaled_height)
            )

            scaled_rect = scaled_text.get_rect(center=screen_center)

            # Draw shadow with offset
            shadow_offset = 4
            self.screen.blit(
                scaled_shadow, (scaled_rect.x + shadow_offset, scaled_rect.y + shadow_offset)
            )

            # Draw main text
            self.screen.blit(scaled_text, scaled_rect)

    def _render_variant_pills(self) -> None:
        """Render variant pills below the pokeball counter."""
        if not self.pokemon_variants:
            return

        # Position below pokeball counter
        margin = 20
        pill_start_y = margin + 36 + 10  # After pokeball counter
        pill_height = 24
        pill_gap = 6
        font_small = pygame.font.Font(None, 24)

        for i, variant in enumerate(self.pokemon_variants):
            # Get colors for this variant
            try:
                variant_enum = PokemonVariant(variant.lower())
                top_color, bottom_color = VARIANT_COLOR_MAP.get(
                    variant_enum,
                    ((120, 120, 120), (80, 80, 80)),  # Default gray
                )
            except ValueError:
                # Fallback for unknown variants
                top_color, bottom_color = ((120, 120, 120), (80, 80, 80))

            # Calculate pill dimensions
            text_surface = font_small.render(variant.upper(), True, (255, 255, 255))
            pill_width = text_surface.get_width() + 16  # Padding

            # Position pill
            pill_y = pill_start_y + i * (pill_height + pill_gap)
            pill_rect = pygame.Rect(margin, pill_y, pill_width, pill_height)

            # Draw pill
            draw_pill(self.screen, pill_rect, top_color, bottom_color, variant.upper(), font_small)

    def get_focusable_elements(self) -> list[list[FocusableElement]]:
        """Return empty list since we handle input directly."""
        return []

    def handle_focus_event(self, event: pygame.event.Event) -> bool:
        """Handle keyboard input and mini-game events."""
        # Let mini-game handle events first if active
        if self.state == GameState.MINIGAME and self.current_minigame is not None:
            if self.current_minigame.handle_event(event):
                return True

        if event.type == pygame.KEYDOWN:
            self.keys_held.add(event.key)

            if event.key == pygame.K_RETURN:
                if self.state not in [GameState.MINIGAME, GameState.VARIANT_ANNOUNCEMENT]:
                    self.throw_pokeball()
                return True
            elif event.key == pygame.K_SPACE:
                # Debug: Toggle hit box visibility
                self.show_hit_boxes = not self.show_hit_boxes
                logger.info(f"Hit box visibility: {'ON' if self.show_hit_boxes else 'OFF'}")
                return True
            elif event.key == pygame.K_ESCAPE or event.key == pygame.K_BACKSPACE:
                self.running = False
                return True

        elif event.type == pygame.KEYUP:
            self.keys_held.discard(event.key)

        return False

    def handle_navigation_result(self, result: NavigationResult) -> bool:
        """Handle navigation results."""
        if result.action in (NavigationAction.EXIT_TO_LAUNCHER, NavigationAction.EXIT_TO_PARENT):
            self.running = False
            return True
        return False

    def run(self) -> None:
        """Main game loop."""
        last_time = time.time()

        while self.running:
            current_time = time.time()
            dt = current_time - last_time
            last_time = current_time

            # Handle events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif not self.handle_focus_event(event):
                    pass  # Event not handled

            # Update game state
            if self.state == GameState.VARIANT_ANNOUNCEMENT:
                self.update_variant_announcement(dt)
                # Don't allow Pokemon movement or player input during announcement

            elif self.state == GameState.AIMING:
                self.handle_pokeball_aiming(dt)
                self.update_pokemon_movement(dt)
                self.update_pokemon_animation(dt)
                self.update_pokemon_audio(dt)
                self.check_time_limit()

            elif self.state == GameState.THROWING:
                self.update_pokeball_throw(dt)
                self.update_pokemon_movement(dt)
                self.update_pokemon_animation(dt)
                self.update_pokemon_audio(dt)
                self.check_collision()
                self.check_time_limit()

            elif self.state == GameState.CONTACT_APPROACH:
                self.update_contact_approach(dt)
                self.update_pokemon_animation(dt)
                # Pokemon moves toward pokeball for natural visual contact

            elif self.state == GameState.MINIGAME:
                self.update_minigame(dt)
                # Mini-game handling (timing challenge, etc.)

            elif self.state == GameState.ESCAPED:
                self.update_escape_animation(dt)

            elif self.state == GameState.SMOKE_ANIMATION:
                self.update_smoke_animation(dt)

            # Render
            self.render()
            self.clock.tick(60)

        # Cleanup resources
        if self.current_minigame is not None:
            if hasattr(self.current_minigame, "cleanup"):
                self.current_minigame.cleanup()

        logger.info("Pokemon Hunt session ended")


def run_on_existing_display(screen: pygame.Surface) -> None:
    """Entry point for launcher system - run on existing display."""
    app = PokemonHuntApp(screen)
    app.run()


def run() -> None:
    """Standalone entry point - initialize pygame and run."""
    pygame.init()
    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    run_on_existing_display(screen)
    pygame.quit()


if __name__ == "__main__":
    # Allow running the app directly: python -m src.apps.pokemon_hunt.app
    run()
