# Pokédex: Complete Pokémon Experience Suite

A comprehensive Pokémon application suite featuring a complete dataset, machine learning classifier, and interactive games built with Python and Pygame.

Full disclosure: Claude is responsible for generating literally every `*.md` file in this repo, along with all of the tests, and some of the scraper scripts...but yolo.

## 🎮 Features

### Interactive Applications
- **🔍 Pokédex Browser** - Search and explore complete Pokémon database with rich metadata
- **📱 Pokémon Scanner** - AI-powered image classification using Vision Transformer model  
- **🆔 ID Card Generator** - Create personalized trainer ID cards with TTS voice selection
- **🎮 Pokémon Hunt** - Action game with timing challenges and Pokéball mechanics
- **❓ Who's That Pokémon?** - Classic guessing game with silhouettes and sound effects

### 🤖 Machine Learning
- **Vision Transformer (ViT)** model fine-tuned for Pokémon classification
- Training pipeline with data augmentation and validation
- Real-time image classification from camera or file input

### 📊 Complete Dataset
- **1000+ Pokémon** with comprehensive metadata from official sources
- **High-quality artwork** and sprite images  
- **Anime cry audio** files for authentic sound effects
- **Rich metadata** including types, descriptions, Pokédex entries, evolution chains, pronunciations

## 🚀 Quick Start

### 1) Create and activate a virtual environment

macOS / Linux (bash/zsh):

```bash
python3 -m venv .venv
source .venv/bin/activate
```

PowerShell (Windows):

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2) Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

If pygame fails to install on your OS, you may need SDL libraries. On Debian/Raspberry Pi OS:

```bash
sudo apt update
sudo apt install -y libsdl2-2.0-0 libsdl2-image-2.0-0 libsdl2-mixer-2.0-0 libsdl2-ttf-2.0-0
```

### 3) Run the launcher

From the project root:

```bash
python launcher.py
```

or module mode:

```bash
python -m launcher
```

Exit fullscreen with **ESC**.

## 🎯 Running Apps Standalone

Each application can be run independently without the launcher:

```bash
# Pokédex Browser - Search and explore Pokémon database
python -m src.apps.pokedex.app

# Pokémon Scanner - AI-powered image classification  
python -m src.apps.scanner.app

# ID Card Generator - Create personalized trainer cards
python -m src.apps.id_card.app

# Pokémon Hunt - Action game with timing challenges
python -m src.apps.pokemon_hunt.app

# Who's That Pokémon? - Classic guessing game
python -m src.apps.whos_that_pokemon.app
```

All apps support unified keyboard navigation:
- **Arrow Keys** - Navigate between options and UI elements
- **ENTER** - Select/activate current item  
- **ESC** - Exit to launcher or previous screen
- **SPACE** - App-specific actions (play audio, capture photo, advance game)
- **BACKSPACE** - Go back or clear search (in Pokédex)
- **Mouse** - Click to select items directly

### 🎮 Navigation System
The project uses a sophisticated focus management system that provides consistent navigation across all applications:
- **Grid Navigation** - Apps automatically detect grid layouts and navigate accordingly
- **Focus Indicators** - Visual feedback shows currently selected elements
- **Smart Wrapping** - Navigation wraps between rows and columns intuitively
- **Context-Sensitive** - Controls adapt based on current app state

## 📁 Project Structure

```
pokedex/
├── src/apps/           # Interactive applications
│   ├── pokedex/       # Pokémon database browser
│   ├── scanner/       # AI image classifier
│   ├── id_card/       # ID card generator  
│   └── whos_that_pokemon/  # Guessing game
├── pokemon_data/      # Complete Pokémon dataset (1000+ entries)
├── pokemon_classifier/ # Trained ViT model
├── training/          # ML model training scripts
├── scripts/           # Data collection & processing
└── launcher.py        # Main application launcher
```

## 🤖 Machine Learning & Training

The project includes a complete machine learning pipeline for Pokémon classification using Vision Transformer (ViT) technology. For detailed information about model training, see [training/README.md](training/README.md).

### Quick Training
```bash
# Modern training pipeline (recommended - 10-25% better accuracy)
python -m training.modern.build_classifier

# Original 2021 tutorial approach
python training/build_pokemon_classifier.py

# Preview training without making changes
python -m training.modern.build_classifier --dry-run
```

The scanner app uses this trained model for real-time Pokémon identification from camera input or uploaded images.

## 📊 Data Collection

This project features a comprehensive data collection system that builds the complete Pokémon dataset from official sources. For detailed information about data collection, see [scripts/README.md](scripts/README.md).

### Key Data Sources
- **[Serebii.net](https://www.serebii.net)** - Official artwork and initial structure
- **[Pokemon.com](https://www.pokemon.com/us/pokedex)** - Official validation and metadata  
- **[PokemonDB](https://pokemondb.net)** - Sprites, Pokédex entries, evolution chains
- **[Pokelore.com](https://pokelore.com)** - Pokémon descriptions
- **[PokemonLP Wiki](https://pokemonlp.fandom.com)** - Pronunciation guides

### Quick Dataset Build
```bash
# Build complete dataset in one command
python scripts/build_pokemon_data.py
```

## 🎵 Audio & Assets

### Pokémon Cries
The project includes authentic Pokémon anime cry sound effects sourced from the community:

- **Original Source**: [RealCries.zip on MediaFire](https://www.mediafire.com/file/bwtoaxbvt2fnage/RealCries.zip/file)
- **Community Discussion**: [PokeMMO Forums - HQ Pokémon Anime Cries](https://forums.pokemmo.com/index.php?/topic/86447-hq-pokemon-anime-cries-gen-1-5/)

These high-quality audio files enhance the authenticity of the Pokédex and game experiences.

### Text-to-Speech Voices
The ID Card Generator uses **Piper TTS** for high-quality voice synthesis. The app supports multiple voices and accents.

#### Installation
```bash
# Install Piper TTS dependency
pip install piper-tts
```

#### Voice Models Setup
1. **Download Piper voice models** from: [Hugging Face - rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices/tree/main)

2. **Recommended voices**:
   - **English (GB)**: `en_GB-northern_english_male-medium.onnx`
   - **English (US)**: `en_US-amy-medium.onnx`
   - **Additional options**: Browse the repository for more voices and quality levels

3. **Directory structure**:
   ```
   voices/
   ├── en_GB/
   │   └── northern_english_male/
   │       ├── northern_english_male.onnx
   │       └── northern_english_male.onnx.json
   └── en_US/
       └── amy/
           ├── amy.onnx
           └── amy.onnx.json
   ```

4. **Manual setup**:
   ```bash
   # Create directories
   mkdir -p voices/en_GB/northern_english_male
   mkdir -p voices/en_US/amy
   
   # Download voice models (example for northern_english_male)
   cd voices/en_GB/northern_english_male
   wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/northern_english_male/medium/en_GB-northern_english_male-medium.onnx
   wget https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/northern_english_male/medium/en_GB-northern_english_male-medium.onnx.json
   
   # Rename for consistency
   mv en_GB-northern_english_male-medium.onnx northern_english_male.onnx
   mv en_GB-northern_english_male-medium.onnx.json northern_english_male.onnx.json
   ```

#### Voice Quality Levels
- **low**: Fastest inference, smallest files (~10-20MB)
- **medium**: Balanced quality/speed (~20-40MB) **[Recommended]**
- **high**: Best quality, slower inference (~40-80MB)

The ID Card app will automatically detect available voices and allow switching between them in the interface.

## 🔗 References & Inspiration

### Machine Learning Tutorial
The Vision Transformer implementation was inspired by:
- **[Creating a Pokémon Classifier with ViT](https://medium.com/@imjeffhi4/tutorial-using-vision-transformer-vit-to-create-a-pok%C3%A9mon-classifier-cb3f26ff2c20)** - Medium tutorial on using Vision Transformers for Pokémon classification

## 🛠️ Development

### Running Individual Components

```bash
# Build complete dataset
python scripts/build_pokemon_data.py

# Modern training pipeline (recommended)
python -m training.modern.build_classifier

# Original 2021 tutorial approach
python training/build_pokemon_classifier.py

# Modern individual training steps
python -m training.modern.augment_images
python -m training.modern.clip_quality_filter
python -m training.modern.finetune_vit

# Original individual training steps
python training/download_training_images.py
python training/augment_training_images.py  
python training/finetune_vit.py

# Run apps directly (see "Running Apps Standalone" section above for all apps)
python -m src.apps.pokedex.app
python -m src.apps.scanner.app
python -m src.apps.id_card.app
python -m src.apps.pokemon_hunt.app
python -m src.apps.whos_that_pokemon.app
```

## 💻 System Requirements

### Minimum Requirements
- **Python**: 3.8 or higher
- **RAM**: 4GB (8GB+ recommended for training)
- **Storage**: 3GB free space (6GB+ with full dataset & TTS voices)
- **OS**: Windows, macOS, or Linux

### For Machine Learning Training
- **GPU**: CUDA-compatible GPU highly recommended
  - **8GB+ VRAM** for modern training (Swin/ConvNeXt models)  
  - **4GB+ VRAM** for basic ViT training
- **CPU Training**: Possible but 5-10x slower
- **RAM**: 16GB+ recommended for large model training

### Platform-Specific Notes
- **Raspberry Pi**: Full app support, limited training capability
- **Apple Silicon**: Native support with Metal Performance Shaders
- **Linux**: Requires SDL2 libraries for Pygame
  ```bash
  sudo apt install libsdl2-2.0-0 libsdl2-image-2.0-0 libsdl2-mixer-2.0-0 libsdl2-ttf-2.0-0
  ```

### Core Dependencies
- **PyTorch** (≥2.2.0) - Deep learning framework
- **Pygame** (≥2.5.0) - UI and game engine  
- **Transformers** (≥4.41.0) - Vision Transformer models
- **Pillow** (≥10.3.0) - Image processing
- **NumPy** (≥1.26.0) - Numerical computations
- **Requests/BeautifulSoup** - Web scraping for data collection
- **piper-tts** - Text-to-speech for ID Card Generator

## 🎯 Key Features

- **Complete Dataset**: 1000+ Pokémon with rich metadata
- **AI Classification**: State-of-the-art Vision Transformer model
- **Interactive UI**: Full-screen applications with intuitive controls
- **Authentic Audio**: Original anime cry sound effects
- **Data Validation**: Automated collection from official sources
- **Extensible Architecture**: Modular design for easy expansion

## 📄 License

This project is for educational and personal use. Pokémon is a trademark of The Pokémon Company, Nintendo, Game Freak, and Creatures Inc.