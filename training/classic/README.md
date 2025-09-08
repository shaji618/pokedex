# Classic Pokémon Vision Transformer Training (2021)

**📚 Original tutorial implementation based on the [Medium article by @imjeffhi4](https://medium.com/@imjeffhi4/tutorial-using-vision-transformer-vit-to-create-a-pok%C3%A9mon-classifier-cb3f26ff2c20)**

This directory contains the classic training pipeline from the 2021 tutorial, implementing the original 3-step approach to build a Pokémon image classifier using Vision Transformer technology.

## 🎯 Overview

The classic pipeline follows the exact methodology described in the original Medium tutorial, providing a solid foundation for understanding ViT-based image classification.

## 🚀 Quick Start

**To train the complete classifier in one command:**

```bash
python training/classic/build_pokemon_classifier.py
```

This orchestrates the entire classic training pipeline and creates the model files in `pokemon_classifier/`.

## 📋 Training Pipeline

The classic training process follows the **original 3-step approach**:

### Step 1: Data Collection 🌐
- **Script**: `download_training_images.py`
- **Purpose**: Collect diverse training images from multiple search engines
- **Sources**: DuckDuckGo and Brave search engines
- **Strategy**: 3 search queries per Pokémon for maximum variety:
  - `Pokemon {name} art` - Artistic representations
  - `Pokemon {name} card` - Trading card images  
  - `Pokemon {name} wallpaper` - High-quality wallpapers
- **Output**: `pokemon_data/{pokemon}/images/` directories with 300+ images per species

### Step 2: Data Augmentation 🎨
- **Script**: `augment_training_images.py`
- **Purpose**: Expand dataset using 6 traditional augmentation techniques
- **Techniques**: 
  - **Mirroring** - Horizontal flips for orientation invariance
  - **Rotating** - Random rotations with background changes
  - **Cropping** - Random crops with zoom effects
  - **Quantization** - Color channel bit reduction
  - **Gaussian Blur** - Convolution-based blurring
  - **Gaussian Noise** - Random noise injection
- **Output**: `pokemon_data/{pokemon}/images_aug/` with 150 total images per species

### Step 3: ViT Fine-tuning 🤖
- **Script**: `finetune_vit.py`
- **Purpose**: Fine-tune pre-trained Vision Transformer model
- **Base Model**: `google/vit-base-patch16-224-in21k` (ImageNet-21K pre-trained)
- **Architecture**: Transformer encoder with 16x16 pixel patches
- **Training**: 3 epochs with early stopping and cosine learning rate scheduling
- **Output**: Complete classifier model in `pokemon_classifier/`

## 🛠️ Available Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| **`build_pokemon_classifier.py`** | **Main orchestrator** | `python training/classic/build_pokemon_classifier.py` |
| `download_training_images.py` | Download diverse training images | `python training/classic/download_training_images.py` |
| `augment_training_images.py` | 6-technique augmentation | `python training/classic/augment_training_images.py` |
| `finetune_vit.py` | ViT fine-tuning | `python training/classic/finetune_vit.py` |
| `predict_vit.py` | Run inference on images | `python training/classic/predict_vit.py --input image.jpg` |
| `clip_filter_images.py` | Basic image filtering | `python training/classic/clip_filter_images.py` |
| `advanced_augment_training_images.py` | Extended augmentation | `python training/classic/advanced_augment_training_images.py` |
| `training_utils.py` | Utilities (standalone) | `python training/classic/training_utils.py` |

## 🎛️ Command Line Options

### `build_pokemon_classifier.py` Options

```bash
# Full training pipeline
python training/classic/build_pokemon_classifier.py

# Preview training without modifying files
python training/classic/build_pokemon_classifier.py --dry-run

# Overwrite existing model
python training/classic/build_pokemon_classifier.py --overwrite

# Custom training parameters
python training/classic/build_pokemon_classifier.py --epochs 5 --batch-size 32 --learning-rate 1e-4

# Skip expensive steps for testing
python training/classic/build_pokemon_classifier.py --skip-download --skip-augmentation

# Use fewer images for faster training
python training/classic/build_pokemon_classifier.py --num-images 100 --num-augmented 50
```

### Data Collection Options

| Flag | Description | Default |
|------|-------------|---------|
| `--num-images` | Images to download per Pokémon | 300 |
| `--engines` | Search engines (`ddg`, `brave`, `all`) | `all` |
| `--concurrency` | Concurrent download threads | 8 |

### Training Options

| Flag | Description | Default |
|------|-------------|---------|
| `--epochs` | Number of training epochs | 3 |
| `--batch-size` | Training batch size | 16 |
| `--learning-rate` | Learning rate | 5e-5 |
| `--fp16` | Enable mixed precision training | False |
| `--no-aug` | Don't use augmented images | False |

## 🔍 Dry Run Mode

The `--dry-run` flag provides complete preview functionality without making any changes:

- **📥 Downloads**: Shows image URLs that would be downloaded without fetching files
- **🎨 Augmentation**: Shows augmented images that would be created without saving files  
- **🤖 Training**: Shows training configuration without executing the model
- **💾 Files**: No model files, images, or directories are created or modified
- **🔍 Output**: All scripts print `[dry-run]` prefixed messages to clearly indicate preview mode

```bash
# Preview complete pipeline
python training/classic/build_pokemon_classifier.py --dry-run

# Preview with custom settings
python training/classic/build_pokemon_classifier.py --dry-run --num-images 500 --epochs 5
```

## 📁 Output Structure

### Training Data Structure
```
pokemon_data/
├── bulbasaur/
│   ├── images/              # Downloaded training images
│   │   ├── af3d2e1.jpg     # Diverse images from search engines
│   │   ├── 9f4e7b8.png     # Multiple formats and sources
│   │   └── manifest.jsonl  # Download metadata
│   └── images_aug/          # Augmented training images
│       ├── 1a5f9c2.png     # Transformed images
│       └── 8d3e4f1.png     # Multiple augmentation types
└── ...
```

### Model Output Structure
```
pokemon_classifier/
├── config.json              # Model configuration (42KB)
├── preprocessor_config.json # Image processor settings (259B)
└── pytorch_model.bin        # Trained weights (330MB)
```

## 🤖 Model Architecture

### Vision Transformer Details
- **Base Architecture**: ViT-Base with 16x16 patches
- **Pre-training**: ImageNet-21K (14M images) + ImageNet-1K fine-tuning
- **Input Resolution**: 224x224 pixels
- **Patch Size**: 16x16 pixels (196 patches per image)
- **Hidden Size**: 768 dimensions
- **Attention Heads**: 12 heads
- **Layers**: 12 transformer encoder layers

### Training Configuration
- **Optimizer**: AdamW with weight decay (0.05)
- **Learning Rate Schedule**: Cosine annealing
- **Early Stopping**: 2 epoch patience on validation accuracy
- **Data Split**: 90% training, 10% validation
- **Evaluation Metric**: Top-1 accuracy

## 📊 Expected Results

Based on the original Medium tutorial:

- **Training Accuracy**: >95% on augmented dataset
- **Validation Accuracy**: >92-95% on sprite-based validation
- **Training Time**: ~30-60 minutes on modern GPU
- **Model Size**: 330MB (86M parameters)
- **Inference Speed**: ~50ms per image on CPU

## 🔗 Usage with Scanner App

The trained model integrates seamlessly with the Pokémon Scanner app:

```bash
# Test the trained model
python training/classic/predict_vit.py --input path/to/pokemon/image.jpg

# Use in scanner app (automatic)
python launcher.py  # Select "Pokémon Scanner"
```

## 🚨 Troubleshooting

### Common Issues

1. **Missing Dependencies**
   ```bash
   pip install torch transformers pillow aiohttp scikit-learn
   ```

2. **CUDA Out of Memory**
   ```bash
   # Reduce batch size
   python training/classic/build_pokemon_classifier.py --batch-size 8
   
   # Disable mixed precision
   python training/classic/build_pokemon_classifier.py --fp16 false
   ```

3. **Slow Downloads**
   ```bash
   # Reduce concurrency
   python training/classic/build_pokemon_classifier.py --concurrency 4
   
   # Use single search engine
   python training/classic/build_pokemon_classifier.py --engines ddg
   ```

4. **Insufficient Training Data**
   ```bash
   # First ensure you have pokemon_data/
   python scripts/build_pokemon_data.py
   
   # Then run training
   python training/classic/build_pokemon_classifier.py
   ```

## 🆚 Modern vs Classic

For **better accuracy and modern techniques**, consider using the **[modern training pipeline](../modern/README.md)**:

| Aspect | Classic (2021) | Modern (2024) | Improvement |
|--------|----------------|---------------|-------------|
| **Augmentation** | 6 basic techniques | RandAugment/TrivialAugment | +3-8% accuracy |
| **Models** | ViT-Base only | Swin/ConvNeXt/ViT variants | +5-10% accuracy |
| **Training** | Basic cross-entropy | Label smoothing + advanced | +2-5% accuracy |
| **Quality** | Filename filtering | CLIP-based filtering | +3-5% efficiency |

```bash
# Switch to modern pipeline
python -m training.modern.build_classifier
```

## 📚 References

- **[Original Medium Tutorial](https://medium.com/@imjeffhi4/tutorial-using-vision-transformer-vit-to-create-a-pok%C3%A9mon-classifier-cb3f26ff2c20)** - The inspiration for this implementation
- **[ViT Paper](https://arxiv.org/abs/2010.11929)** - "An Image is Worth 16x16 Words: Transformers for Image Recognition at Scale"
- **[Hugging Face Transformers](https://huggingface.co/docs/transformers)** - Framework documentation
- **[ImageNet-21K](https://www.image-net.org/)** - Pre-training dataset information

## 📄 License

The trained model is for educational and personal use. Pokémon is a trademark of The Pokémon Company, Nintendo, Game Freak, and Creatures Inc.

---

**📈 For state-of-the-art results, consider upgrading to the [modern training pipeline](../modern/README.md) with 10-25% higher accuracy!**
