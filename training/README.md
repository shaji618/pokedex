# Pokémon Vision Transformer Training Pipeline

This directory contains complete machine learning pipelines for training a Pokémon image classifier using Vision Transformer (ViT) technology.

## 🎯 Overview

**Two training approaches are available:**

- **🚀 [Modern (2024)](modern/README.md)** - State-of-the-art pipeline with 10-25% higher accuracy
- **📚 [Classic (2021)](classic/README.md)** - Original tutorial implementation

## 🚀 Quick Start

### ⭐ Recommended: Modern Pipeline (2024)
```bash
# Best results with modern techniques
python -m training.modern.build_classifier

# Preview modern improvements
python -m training.modern.build_classifier --dry-run
```

### 📚 Classic Pipeline (2021)
```bash
# Original tutorial approach
python training/classic/build_pokemon_classifier.py

# Preview classic approach
python training/classic/build_pokemon_classifier.py --dry-run
```

## 📋 Training Approaches

### 🚀 Modern Pipeline (2024) - **Recommended**

The modern approach implements state-of-the-art computer vision techniques from 2022-2024:

- **🎨 Advanced Augmentation**: RandAugment, TrivialAugment, AutoAugment
- **🤖 Modern Architectures**: Swin Transformer, ConvNeXt, larger ViT models  
- **🔍 CLIP Filtering**: AI-powered image quality assessment
- **🏋️ Advanced Training**: Label smoothing, gradient clipping, mixed precision
- **📊 Expected Improvement**: 10-25% higher accuracy vs classic

**See [modern/README.md](modern/README.md) for complete documentation.**

### 📚 Classic Pipeline (2021) - **Educational**

The classic approach follows the original Medium tutorial methodology:

- **📥 Data Collection**: Multi-engine image downloading
- **🎨 Basic Augmentation**: 6 traditional techniques (mirror, rotate, crop, etc.)
- **🤖 ViT Fine-tuning**: Standard Vision Transformer training
- **📖 Tutorial Faithful**: Exact implementation of original approach

**See [classic/README.md](classic/README.md) for complete documentation.**

## 🛠️ Directory Structure

```
training/
├── README.md                    # This overview (you are here)
├── modern/                      # 🚀 Modern pipeline (2024)
│   ├── README.md               # Complete modern documentation
│   ├── build_classifier.py    # Main modern orchestrator
│   ├── augment_images.py       # RandAugment/TrivialAugment
│   ├── finetune_vit.py        # Swin/ConvNeXt training
│   ├── clip_quality_filter.py # CLIP-based filtering
│   └── training_utils.py      # Modern utilities
└── classic/                     # 📚 Classic pipeline (2021)
    ├── README.md               # Classic tutorial documentation
    ├── build_pokemon_classifier.py  # Original orchestrator
    ├── download_training_images.py  # Multi-engine downloads
    ├── augment_training_images.py   # 6 basic techniques
    ├── finetune_vit.py             # Standard ViT training
    ├── predict_vit.py              # Model inference
    └── training_utils.py           # Classic utilities
```

## 🎯 Quick Reference

### Modern Pipeline (Recommended)
```bash
# Complete training with best techniques
python -m training.modern.build_classifier

# High-quality training
python -m training.modern.build_classifier --model swin-large --epochs 8

# Quick testing
python -m training.modern.build_classifier --dry-run
```

### Classic Pipeline (Educational)
```bash
# Original tutorial approach
python training/classic/build_pokemon_classifier.py

# Preview without changes
python training/classic/build_pokemon_classifier.py --dry-run

# Custom parameters
python training/classic/build_pokemon_classifier.py --epochs 5 --batch-size 32
```

## 📈 Modern vs Classic Comparison

| Aspect | Classic (2021) | Modern (2024) | Improvement |
|--------|----------------|---------------|-------------|
| **Augmentation** | 6 basic techniques | RandAugment/TrivialAugment | +3-8% accuracy |
| **Quality Filtering** | Filename checking | CLIP-based filtering | +3-5% efficiency |
| **Model Architecture** | ViT-Base only | Swin/ConvNeXt/ViT variants | +5-10% accuracy |
| **Training Techniques** | Basic cross-entropy | Label smoothing + advanced | +2-5% accuracy |
| **LR Scheduling** | Linear decay | Cosine annealing with warmup | +1-3% accuracy |
| **Dependencies** | Mixed approach | Fully standalone subdirs | Better modularity |

**🎯 Total Expected Improvement: 10-25% higher accuracy with modern approach**

## 🔍 Dry Run Mode

Both pipelines support `--dry-run` for safe preview:

```bash
# Preview modern pipeline
python -m training.modern.build_classifier --dry-run

# Preview classic pipeline  
python training/classic/build_pokemon_classifier.py --dry-run
```

**Dry run shows:**
- 📥 Downloads that would happen (without fetching files)
- 🎨 Augmentations that would be created (without saving files)  
- 🤖 Training configuration (without executing model)
- 💾 No actual files are created or modified

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

Based on the Medium tutorial and our implementation:

- **Training Accuracy**: >95% on augmented dataset
- **Validation Accuracy**: >95% on sprite-based validation
- **Training Time**: ~30-60 minutes on modern GPU
- **Model Size**: 330MB (86M parameters)
- **Inference Speed**: ~50ms per image on CPU

## 🔗 Usage with Scanner App

The trained models integrate seamlessly with the Pokémon Scanner app:

```bash
# Test modern model
python training/modern/finetune_vit.py --predict --input path/to/pokemon/image.jpg

# Test classic model  
python training/classic/predict_vit.py --input path/to/pokemon/image.jpg

# Use in scanner app (automatic detection of best available model)
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
   # Modern: Reduce batch size or use smaller model
   python -m training.modern.build_classifier --batch-size 8 --model vit-base
   
   # Classic: Reduce batch size
   python training/classic/build_pokemon_classifier.py --batch-size 8
   ```

3. **Slow Downloads**
   ```bash
   # Classic: Reduce concurrency or use single engine
   python training/classic/build_pokemon_classifier.py --concurrency 4 --engines ddg
   ```

4. **Insufficient Training Data**
   ```bash
   # First ensure you have pokemon_data/
   python scripts/build_pokemon_data.py
   
   # Then run training (modern recommended)
   python -m training.modern.build_classifier
   ```

5. **Import Errors**
   ```bash
   # If you see import errors, ensure you're in project root:
   cd /path/to/pokedex
   python -m training.modern.build_classifier
   ```

### Performance Optimization

- **GPU Training**: Automatically detected and used if available
- **Mixed Precision**: Use `--fp16` for faster training on modern GPUs
- **Batch Size**: Increase for better GPU utilization (if memory allows)
- **Data Loading**: Adjust `--num-workers` based on CPU cores

## 🎯 Development

### Testing Individual Components

```bash
# Modern components
python -m training.modern.augment_images --dry-run
python -m training.modern.clip_quality_filter --dry-run

# Classic components  
python training/classic/download_training_images.py --pokemon "Pikachu" --dry-run
python training/classic/augment_training_images.py --pokemon "Charizard" --dry-run
python training/classic/predict_vit.py --model-dir pokemon_classifier --input test_image.jpg
```

### Custom Training

```bash
# Modern custom training
python -m training.modern.build_classifier \
    --model swin-large \
    --epochs 10 \
    --batch-size 8 \
    --learning-rate 1e-5

# Classic custom training
python training/classic/finetune_vit.py \
    --model-name google/vit-large-patch16-224-in21k \
    --epochs 10 \
    --batch-size 8 \
    --learning-rate 1e-5 \
    --use-aug
```

## 📚 References

- **[Medium Tutorial](https://medium.com/@imjeffhi4/tutorial-using-vision-transformer-vit-to-create-a-pok%C3%A9mon-classifier-cb3f26ff2c20)** - Original inspiration and methodology
- **[ViT Paper](https://arxiv.org/abs/2010.11929)** - "An Image is Worth 16x16 Words: Transformers for Image Recognition at Scale"
- **[Hugging Face Transformers](https://huggingface.co/docs/transformers)** - Framework documentation
- **[ImageNet-21K](https://www.image-net.org/)** - Pre-training dataset information

## 📄 Model License

The trained model is for educational and personal use. Pokémon is a trademark of The Pokémon Company, Nintendo, Game Freak, and Creatures Inc.
