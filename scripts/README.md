# Pokémon Data Collection Scripts

This directory contains scripts for building a complete Pokémon dataset from official sources.

## 🚀 Quick Start

**To build the complete Pokémon dataset in one command:**

```bash
python scripts/build_pokemon_data.py
```

This orchestrates the entire data collection process automatically.

## 📋 How It Works

The data collection follows a **comprehensive 8-step approach** for maximum accuracy:

### Step 1: Core Data & Structure (Serebii)
- **Script**: `scrape_serebii_data.py`
- **Purpose**: Creates complete directory structure, metadata, and artwork from authoritative source
- **Source**: [Serebii.net National Pokédex](https://www.serebii.net/pokemon/nationalpokedex.shtml)
- **Output**: 
  - `pokemon_data/{pokemon_name}/` directories
  - `pokemon_data/{pokemon_name}/metadata.json` (name, types, Pokédex number, speed stats)
  - `pokemon_data/{pokemon_name}/main.png` (high-quality artwork)
- **Cleanup**: Automatically removes directories for Pokemon not found in Serebii's official list

### Step 2: Sprite Icons
- **Script**: `download_sprites.py`
- **Purpose**: Downloads small sprite icons for each Pokemon
- **Source**: [PokemonDB Sprites](https://pokemondb.net/sprites)
- **Validation**: Pre-flight validation tests sprite availability with improved name matching
- **Behavior**: Only downloads missing sprites by default (use `--overwrite` to force re-download)
- **Features**: 
  - ✅ **100% validation success** for edge cases (Nidoran, Mr. Mime, Ho-Oh, etc.)
  - 🎯 **Smart name mapping** between local directories and remote sprite names
  - 🔍 **Bidirectional resolution** handles both `flab_b` → `flabebe` and `flabebe` → `flab_b`

### Step 3: Descriptions
- **Script**: `scrape_descriptions.py`
- **Purpose**: Fetches Pokemon descriptions
- **Source**: [Pokelore.com](https://pokelore.com/pokedex)
- **Behavior**: Updates missing/incorrect descriptions by default (use `--overwrite` to force updates)

### Step 4: Pokédex Entries
- **Script**: `scrape_pokedex_entries.py`
- **Purpose**: Fetches detailed Pokédex entries
- **Source**: [PokemonDB Pokédex](https://pokemondb.net/pokedex)
- **Behavior**: Updates missing/incorrect entries by default (use `--overwrite` to force updates)

### Step 5: Evolution Chains
- **Script**: `scrape_evolution_chains.py`
- **Purpose**: Fetches Pokemon evolution relationships and chains
- **Source**: [PokemonDB Evolution](https://pokemondb.net/evolution)
- **Behavior**: Updates missing/incorrect evolution data by default (use `--overwrite` to force updates)

### Step 6: Pronunciations
- **Script**: `scrape_pronunciations.py`
- **Purpose**: Fetches Pokemon pronunciations (phonetic and IPA)
- **Source**: [PokemonLP Fandom Wiki](https://pokemonlp.fandom.com/wiki/Pok%C3%A9mon_Pronunciation_Guide)
- **Behavior**: Uses generation-specific lookup for efficiency, skips unchanged pronunciations (upsert mode)

### Step 7: Logo Font Names
- **Script**: `download_pokemon_logo_font_names.py`
- **Purpose**: Downloads Pokemon logo font name images
- **Source**: [Textcraft.net](https://textcraft.net)
- **Behavior**: Skips unchanged logo fonts (upsert mode)

### Step 8: Metadata Normalization
- **Script**: `normalize_metadata.py` (integrated into build process)
- **Purpose**: Cleans up text inconsistencies in metadata
- **Actions**:
  - 📝 **Normalizes text**: Fixes periods, apostrophes, capitalization
  - 🏷️ **Pokemon branding**: Ensures consistent "Pokémon" spelling
  - 🔤 **Capitalization**: Fixes ALL CAPS words and Pokemon names
  - 🧹 **Whitespace**: Removes duplicate entries and extra spaces

### Verification
- **Validates count**: Ensures local Pokémon count matches Serebii's official count
- **Completeness check**: Verifies all Pokemon from #1 to the latest are present
- **Comprehensive reporting**: Shows build results and any issues found

## 🛠️ Available Scripts

### Primary Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `build_pokemon_data.py` | **Main orchestrator** | `python scripts/build_pokemon_data.py` |
| `scrape_serebii_data.py` | Serebii artwork & structure | `python scripts/scrape_serebii_data.py` |


### Supplementary Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `download_sprites.py` | Download small sprite icons | `python scripts/download_sprites.py` |
| `download_hunt_assets.py` | **Download hunt game assets (sprites & audio)** | `python scripts/download_hunt_assets.py` |
| `scrape_descriptions.py` | Pokemon descriptions | `python scripts/scrape_descriptions.py` |
| `scrape_pokedex_entries.py` | Pokedex entries | `python scripts/scrape_pokedex_entries.py` |
| `scrape_pronunciations.py` | Pronunciation data | `python scripts/scrape_pronunciations.py` |
| `scrape_evolution_chains.py` | Evolution relationships | `python scripts/scrape_evolution_chains.py` |
| `download_pokemon_logo_font_names.py` | Logo font generation | `python scripts/download_pokemon_logo_font_names.py` |
| `import_pokemon_cries.py` | **Import Pokemon cry audio files** | `python scripts/import_pokemon_cries.py ./RealCries` |
| `normalize_metadata.py` | Text normalization | `python scripts/normalize_metadata.py` |
| `verify_pokemon_data.py` | **Comprehensive verification** | `python scripts/verify_pokemon_data.py` |
| `fix_png_profiles.py` | Fix PNG color profiles | `python scripts/fix_png_profiles.py` |
| `lint_and_validate.py` | Code quality & validation | `python scripts/lint_and_validate.py` |

### Utility Modules

| Module | Purpose | Usage |
|--------|---------|-------|
| `validation_utils.py` | **Pokemon name resolution, image & audio validation** | Imported by other scripts |
| `cli.py` | Common CLI functions & Pokemon directory resolution | Imported by other scripts |
| `script_logger.py` | Emoji-enhanced logging for scripts | Imported by other scripts |
| `browser_utils.py` | Playwright browser automation utilities | Imported by other scripts |

## 🎮 Hunt Game Assets

### `download_hunt_assets.py` - Pokemon Hunt Game Asset Download

This script downloads sprites and audio assets specifically for the Pokemon Hunt game, organizing them in `hunt_assets/` directories for easy access by the game.

**Features:**
- 🎨 **Auto-discovery**: Automatically finds all generation pages from Project Pokemon sprite index
- 🔊 **Comprehensive audio**: Downloads all Pokemon cries from Pokemon Showdown
- 🎯 **Smart filtering**: Can target specific Pokemon or download everything
- 📱 **Game-ready**: Stores assets in format expected by hunt game
- 🧠 **Intelligent naming**: Preserves variant info (shiny, mega, etc.) in filenames

**Asset Sources:**
- **Sprites**: [Project Pokemon 3D Models](https://projectpokemon.org/home/docs/spriteindex_148/)
- **Audio**: [Pokemon Showdown Audio Cries](https://play.pokemonshowdown.com/audio/cries/)

**Usage Examples:**
```bash
# Download all hunt assets (sprites + audio)
python scripts/download_hunt_assets.py

# Download assets for specific Pokemon only
python scripts/download_hunt_assets.py --pokemon bulbasaur

# Download only sprites (no audio)
python scripts/download_hunt_assets.py --sprites-only

# Download only audio (no sprites)  
python scripts/download_hunt_assets.py --audio-only

# Dry run to see what would be downloaded
python scripts/download_hunt_assets.py --dry-run

# Overwrite existing assets
python scripts/download_hunt_assets.py --overwrite
```

**Output Structure:**
```
pokemon_data/bulbasaur/hunt_assets/
├── bulbasaur.gif          # Normal sprite
├── bulbasaur_shiny.gif    # Shiny variant
├── bulbasaur.mp3          # Pokemon cry
└── bulbasaur.ogg          # Alternative audio format
```

## 🎵 Audio Import & Validation

### `import_pokemon_cries.py` - Pokemon Cry Audio Import

This script imports authentic Pokemon anime cry sound effects from the community-sourced RealCries collection.

**Features:**
- 🎵 **Smart file matching**: Automatically matches audio files to Pokemon by Pokedex number
- 🤔 **Interactive selection**: When multiple audio files exist for one Pokemon, asks user to choose
- 🔍 **Audio validation**: Validates file format, duration, and audio properties
- 📊 **Audio comparison**: Can compare local vs imported files using duration, spectral analysis
- 🛡️ **Safe importing**: Dry-run mode and validation before overwriting existing files
- 🔄 **Batch processing**: Can import all files or specific Pokemon only

**Audio Source:**
- **Original**: [RealCries.zip on MediaFire](https://www.mediafire.com/file/bwtoaxbvt2fnage/RealCries.zip/file)
- **Community**: [PokeMMO Forums - HQ Pokemon Anime Cries](https://forums.pokemmo.com/index.php?/topic/86447-hq-pokemon-anime-cries-gen-1-5/)

**Usage Examples:**
```bash
# Download and extract RealCries.zip to your project root, then:

# Preview what would be imported
python scripts/import_pokemon_cries.py --dry-run

# Import all audio files interactively
python scripts/import_pokemon_cries.py ./RealCries

# Import all files in batch mode (auto-select largest file)
python scripts/import_pokemon_cries.py ./RealCries --batch

# Import specific Pokemon only
python scripts/import_pokemon_cries.py ./RealCries --pokemon pikachu

# Validation only (check RealCries directory structure)
python scripts/import_pokemon_cries.py --validation-only
```

**Interactive Mode:**
When multiple audio files exist for the same Pokemon, the script shows details:
```
🎵 Multiple audio files found for #025 Pikachu:
============================================================
 1. 025 - Pikachu.wav
    Duration: 1.23s | Size: 196.2KB | Rate: 44100Hz | Format: .wav
    Spectral: 2847Hz | RMS: 0.0542

 2. 025Pikachu_Cry.mp3  
    Duration: 1.19s | Size: 28.4KB | Rate: 22050Hz | Format: .mp3
    Spectral: 2203Hz | RMS: 0.0489

Choose file (1-2) or 's' to skip: 1
✅ Selected: 025 - Pikachu.wav
```

**Audio Validation:**
- Validates audio format, duration (0.1-10s), and sample rate
- Uses librosa (if available) for spectral analysis and advanced comparison
- Compares file properties when replacing existing audio files
- Pi-friendly: gracefully handles missing advanced audio libraries

## 🔍 Data Verification & Correction

### `verify_pokemon_data.py` - Comprehensive Verification

This script provides **comprehensive verification and correction** of Pokemon data:

**Features:**
- ✅ **Directory validation**: Checks Pokemon directory names against canonical sources
- 📁 **File completeness**: Verifies required files exist (main.png, sprite.png, metadata.json, etc.)
- 📊 **Metadata validation**: Validates metadata content against scraping sources  
- 🖼️ **Image validation**: Uses perceptual hashing to verify images match remote sources
- 🔧 **Auto-correction**: Can fix corrupted data using existing scrapers
- 📈 **Batch processing**: Can verify entire dataset or single Pokemon

**Usage Examples:**
```bash
# Verify entire dataset
python scripts/verify_pokemon_data.py

# Verify specific Pokemon (with smart name resolution)
python scripts/verify_pokemon_data.py --pokemon "Flabebe"     # Works with user-friendly names
python scripts/verify_pokemon_data.py --pokemon "Flabébé"    # Works with accented names  
python scripts/verify_pokemon_data.py --pokemon "669"        # Works with Pokedex numbers

# Dry run (show what would be verified/fixed)
python scripts/verify_pokemon_data.py --pokemon "Flabebe" --dry-run

# Auto-fix issues found during verification
python scripts/verify_pokemon_data.py --pokemon "Flabebe" --fix

# Only check specific aspects
python scripts/verify_pokemon_data.py --files-only           # Only check file existence
python scripts/verify_pokemon_data.py --metadata-only        # Only validate metadata
```

## 🧠 Smart Pokemon Name Resolution

All scripts with `--pokemon` flags now support **intelligent name resolution**:

**Supported Input Formats:**
- ✅ **Display names**: `"Flabebe"`, `"Mr. Mime"`, `"Ho-Oh"`
- ✅ **Accented names**: `"Flabébé"`, `"Pokémon"`  
- ✅ **Directory names**: `"flab_b"`, `"mr_mime"`, `"ho_oh"`
- ✅ **Pokedex numbers**: `"669"`, `"122"`, `"250"`
- ✅ **Gender variants**: `"Nidoran♂"`, `"Nidoran♀"`
- ✅ **Case insensitive**: `"pikachu"`, `"CHARIZARD"`, `"Bulbasaur"`

**Examples:**
```bash
# All of these work for the same Pokemon:
python scripts/download_sprites.py --pokemon "Flabebe"
python scripts/download_sprites.py --pokemon "Flabébé"  
python scripts/download_sprites.py --pokemon "flab_b"
python scripts/download_sprites.py --pokemon "669"
```

This eliminates the need to know exact directory naming conventions!

## 📝 Update vs Overwrite Behavior

All scripts follow a consistent pattern for data handling:

- **Default behavior (update)**: Only processes missing or incorrect data
  - Downloads/scrapes only if the file doesn't exist or content has changed
  - Preserves existing correct data to avoid unnecessary network requests
  - Example: `python scripts/download_sprites.py` (only downloads missing sprites)

- **Overwrite behavior**: Forces processing even for existing correct data  
  - Use `--overwrite` flag to force re-download/re-scrape everything
  - Useful for refreshing all data or fixing corrupted files
  - Example: `python scripts/download_sprites.py --overwrite` (re-downloads all sprites)

This design ensures scripts are fast by default while providing full control when needed.

## 🎛️ Command Line Options

### `build_pokemon_data.py` Options

```bash
# Full build (recommended)
python scripts/build_pokemon_data.py

# Validate existing data only (skip Serebii)
python scripts/build_pokemon_data.py --validate-only

# Dry run (show what would be done)
python scripts/build_pokemon_data.py --dry-run

# Overwrite existing Serebii data
python scripts/build_pokemon_data.py --overwrite

# Skip final count verification
python scripts/build_pokemon_data.py --skip-count-check

# Testing single Pokemon (for development)
python scripts/build_pokemon_data.py --pokemon "bulbasaur"

# Performance options
python scripts/build_pokemon_data.py --core-only           # Essential scripts only
python scripts/build_pokemon_data.py --skip-expensive      # Skip logos + pronunciations
python scripts/build_pokemon_data.py --skip-browser-heavy  # Skip browser automation
python scripts/build_pokemon_data.py --skip-logos          # Skip logo generation
```

### `scrape_official_pokemon_site.py` Options

```bash
# Validate specific Pokemon  
python scripts/scrape_official_pokemon_site.py --pokemon "Pikachu"
python scripts/scrape_official_pokemon_site.py --pokemon "pikachu"
python scripts/scrape_official_pokemon_site.py --pokemon "25"  # by Pokedex number

# Dry run
python scripts/scrape_official_pokemon_site.py --pokemon "Pikachu" --dry-run
```

### `verify_pokemon_data.py` Options

```bash
# Full dataset verification
python scripts/verify_pokemon_data.py

# Single Pokemon verification (with smart name resolution)
python scripts/verify_pokemon_data.py --pokemon "Flabebe"
python scripts/verify_pokemon_data.py --pokemon "669"

# Dry run (show what would be verified)
python scripts/verify_pokemon_data.py --pokemon "Flabebe" --dry-run

# Auto-fix issues found
python scripts/verify_pokemon_data.py --pokemon "Flabebe" --fix

# Verification scope options
python scripts/verify_pokemon_data.py --files-only           # Only check file existence
python scripts/verify_pokemon_data.py --metadata-only        # Only validate metadata
python scripts/verify_pokemon_data.py --images-only          # Only verify images

# Validation control
python scripts/verify_pokemon_data.py --validation-only      # Pre-flight validation only
```

## 🔧 Technical Details

### Anti-Bot Protection
- **Primary method**: Enhanced HTTP requests with realistic browser headers
- **Fallback method**: Playwright browser automation for blocked requests
- **Automatic switching**: Seamlessly falls back when rate-limited

### Data Safety
- ✅ **Safe operations**: Only modifies `metadata.json` files
- 🖼️ **Preserves assets**: Never touches images, audio, or other files
- 📊 **Preserves data**: Maintains all existing metadata fields, only updates core ones

### Type Safety
- 🏷️ **Pokemon type validation**: Uses centralized enum (`src/utils/pokemon_types.py`)
- 🔄 **Consistent ordering**: Types are normalized and sorted for reliable comparisons
- ✨ **Enum-based**: Type effectiveness uses enum values, not strings

### Image Validation
- 🖼️ **Perceptual hashing**: Uses `imagehash` library for robust image comparison
- 🎯 **Pi-friendly**: Lightweight algorithms suitable for Raspberry Pi deployment
- 🔍 **Smart comparison**: Handles compression artifacts and minor quality differences
- ✅ **Automated verification**: Validates local images match remote sources

### Error Handling
- 🔄 **Resilient requests**: Automatic retry with Playwright on failures
- 📊 **Comprehensive reporting**: Detailed success/failure statistics
- 🛡️ **Graceful degradation**: Continues processing other Pokemon if one fails

## 📊 Example Output

```
🎮 Building complete Pokemon dataset
==================================================
🌐 Step 1: Running Serebii scraper to build directory structure...
  ✅ Serebii scraper completed successfully
  📊 Total Pokemon directories: 1025

🏛️ Step 2: Validating 1025 Pokemon against pokemon.com...
[   1/1025] Validating bulbasaur...
  ✅ Valid
[   2/1025] Validating ivysaur...
  🔄 Updated
[   3/1025] Validating venusaur...
  ✅ Valid
...

🖼️  Step 3: Downloading all Pokemon sprites...
  ✅ Sprite download completed successfully
    Downloaded: 15 new sprites
    Skipped: 1010 existing sprites

📖 Step 4: Scraping Pokemon descriptions...
  ✅ Description scraping completed successfully
    Updated: 8 descriptions
    Skipped: 1017 unchanged

📚 Step 5: Scraping all Pokédex entries...
  ✅ Pokédex entries scraping completed successfully
    Updated: 12 entries
    Skipped: 1013 unchanged

🔗 Step 6: Scraping Pokemon evolution chains...
  ✅ Evolution chains scraping completed successfully
    Updated: 3 evolution chains

🗣️  Step 7: Scraping all Pokemon pronunciations...
  ✅ Pronunciations scraping completed successfully
    Updated: 5 pronunciations
    Skipped: 1020 unchanged

🖋️  Step 8: Downloading Pokemon logo fonts...
  ✅ Logo font download completed successfully
    Downloaded: 12 new logos
    Skipped: 1013 existing logos

🧹 Step 9: Normalizing metadata text...
  ✅ Metadata normalization completed successfully
    Fixed: 23 text inconsistencies
    Skipped: 1002 clean entries

🔍 Step 10: Verifying Pokémon count matches official source...
  📁 Local Pokémon directories: 1025
  🔢 Highest Pokédex number found: 1025
  🌐 Testing if Pokémon #1026 exists on pokemon.com...
  ✅ Pokémon #1026 does not exist - count appears correct

==================================================
🎯 BUILD SUMMARY
==================================================
📊 Validation Results:
  • Total processed: 1025
  • Valid (no changes): 1020
  • Updated/corrected: 5
  • Deleted (invalid): 0
  • Failed: 0

📈 Count Verification:
  • Local Pokémon count: 1025
  • Max Pokédex number: 1025
  ✅ Dataset appears complete

🎉 Dataset build completed successfully!
📁 Pokémon data is ready in: /path/to/pokemon_data
```

## 🚨 Troubleshooting

### Common Issues

1. **"Blocked by anti-bot detection"**
   - ✅ **Normal**: Script automatically falls back to Playwright
   - 🛠️ **Fix**: Ensure Playwright is installed: `playwright install chromium`

2. **"Pokemon #X does not exist on pokemon.com"**
   - ✅ **Normal**: Invalid Pokemon are automatically removed
   - 📊 **Expected**: Some Serebii entries may not exist on the official site

3. **"Failed to extract data"**
   - 🔄 **Retry**: Run the script again (temporary network issues)
   - 🌐 **Check**: Verify internet connection
   - 🛠️ **Install**: Ensure all dependencies are installed

### Dependencies

Make sure all dependencies are installed:

```bash
pip install -r requirements.txt
playwright install chromium  # For anti-bot fallback
```

**New dependencies for image validation:**
- `imagehash>=4.3.1` - For perceptual image comparison (Pi-friendly)
- Automatically handles missing dependency gracefully (validation skipped if not available)

## 📁 Output Structure

```
pokemon_data/
├── bulbasaur/
│   ├── metadata.json      # Core Pokemon data
│   ├── main.png          # Official artwork
│   ├── sprite.png        # Small icon
│   └── anime_cry.wav     # Audio (if available)
├── ivysaur/
│   └── ...
└── ...
```

### `metadata.json` Structure

```json
{
  "pokedex_number": 1,
  "name": "Bulbasaur",
  "types": ["grass", "poison"],
  "description": "...",
  "pokedex_entries": [...],
  "evolution_chain": ["bulbasaur", "ivysaur", "venusaur"],
  "evolution_graph": [
    {"from": "bulbasaur", "to": "ivysaur"},
    {"from": "ivysaur", "to": "venusaur"}
  ],
  "pronunciations": {
    "phonetic": "BUL-ba-sore",
    "ipa": "/ˈbʌlbəsɔr/"
  },
  "generation": 1
}
```

**Note**: The build process only modifies the first 3 fields (`pokedex_number`, `name`, `types`) during validation. All other fields are preserved from supplementary scripts. The final normalization step cleans up text formatting without changing content meaning.
