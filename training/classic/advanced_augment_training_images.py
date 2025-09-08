from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import torchvision.transforms as transforms
from PIL import Image
from torchvision.transforms import AutoAugment, RandAugment, TrivialAugmentWide

from training.scripts import cli as cli_utils


PROJECT_ROOT = Path(__file__).resolve().parents[1]
POKEMON_DATA_DIR = PROJECT_ROOT / "pokemon_data"


class ModernAugmentationPipeline:
    def __init__(
        self,
        image_size: int = 224,
        augmentation_strategy: str = "randaugment",
        severity: int = 2,
    ) -> None:
        self.image_size = image_size
        self.strategy = augmentation_strategy
        self.severity = severity
        self.base_transform = transforms.Compose(
            [
                transforms.Resize((image_size, image_size)),
                transforms.ToTensor(),
            ]
        )
        self.augmentation_transforms = self._build_augmentation()

    def _build_augmentation(self) -> transforms.Compose:
        augs = []
        if self.strategy == "randaugment":
            augs.append(
                RandAugment(
                    num_ops=2,
                    magnitude=self.severity,
                )
            )
        elif self.strategy == "trivialaugment":
            augs.append(TrivialAugmentWide())
        elif self.strategy == "autoaugment":
            augs.append(AutoAugment(policy=transforms.AutoAugmentPolicy.IMAGENET))
        elif self.strategy == "pokemon_custom":
            augs.extend(
                [
                    transforms.RandomChoice(
                        [
                            transforms.RandomRotation(15),
                            transforms.RandomAffine(degrees=0, translate=(0.1, 0.1)),
                            transforms.RandomPerspective(distortion_scale=0.2, p=0.5),
                        ]
                    ),
                    transforms.ColorJitter(brightness=0.3, contrast=0.3, saturation=0.3, hue=0.1),
                    transforms.RandomChoice(
                        [
                            transforms.GaussianBlur(kernel_size=3),
                            transforms.RandomAdjustSharpness(sharpness_factor=2),
                            transforms.Identity(),
                        ]
                    ),
                ]
            )
        augs.extend(
            [
                transforms.RandomHorizontalFlip(p=0.5),
                transforms.Resize((self.image_size, self.image_size)),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ]
        )
        return transforms.Compose(augs)

    def augment_image(self, image: Image.Image) -> Image.Image:
        tensor = self.augmentation_transforms(image)
        tensor = tensor * torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1)
        tensor = tensor + torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1)
        tensor = torch.clamp(tensor, 0, 1)
        to_pil = transforms.ToPILImage()
        return to_pil(tensor)


class MixupCutmixAugmentation:
    def __init__(self, alpha: float = 1.0, cutmix_prob: float = 0.5) -> None:
        self.alpha = alpha
        self.cutmix_prob = cutmix_prob

    def mixup_data(
        self, x: torch.Tensor, y: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, float]:
        lam = np.random.beta(self.alpha, self.alpha) if self.alpha > 0 else 1
        batch_size = x.size(0)
        index = torch.randperm(batch_size)
        mixed_x = lam * x + (1 - lam) * x[index, :]
        y_a, y_b = y, y[index]
        return mixed_x, y_a, y_b, lam

    def cutmix_data(
        self, x: torch.Tensor, y: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, float]:
        lam = np.random.beta(self.alpha, self.alpha) if self.alpha > 0 else 1
        batch_size = x.size(0)
        index = torch.randperm(batch_size)
        W, H = x.size(2), x.size(3)
        cut_rat = np.sqrt(1.0 - lam)
        cut_w = int(W * cut_rat)
        cut_h = int(H * cut_rat)
        cx = np.random.randint(W)
        cy = np.random.randint(H)
        bbx1 = np.clip(cx - cut_w // 2, 0, W)
        bby1 = np.clip(cy - cut_h // 2, 0, H)
        bbx2 = np.clip(cx + cut_w // 2, 0, W)
        bby2 = np.clip(cy + cut_h // 2, 0, H)
        x[:, :, bbx1:bbx2, bby1:bby2] = x[index, :, bbx1:bbx2, bby1:bby2]
        lam = 1 - ((bbx2 - bbx1) * (bby2 - bby1) / (W * H))
        y_a, y_b = y, y[index]
        return x, y_a, y_b, lam


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Advanced augmentation for Pokémon images using modern techniques"
    )
    cli_utils.add_dry_run(parser, help="Preview augmentation without saving files")
    cli_utils.add_pokemon(parser, help="Process only specific Pokémon")
    parser.add_argument(
        "--strategy",
        choices=["randaugment", "trivialaugment", "autoaugment", "pokemon_custom"],
        default="randaugment",
        help="Augmentation strategy to use (default: randaugment)",
    )
    parser.add_argument(
        "--num-augmented",
        type=int,
        default=200,
        help="Target number of total images per Pokémon (default: 200)",
    )
    parser.add_argument(
        "--severity",
        type=int,
        default=2,
        choices=range(1, 10),
        help="Augmentation severity (1-9, default: 2)",
    )
    parser.add_argument(
        "--image-size", type=int, default=224, help="Target image size (default: 224)"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.dry_run:
        pass
    ModernAugmentationPipeline(
        image_size=args.image_size,
        augmentation_strategy=args.strategy,
        severity=args.severity,
    )
    return 0


if __name__ == "__main__":
    import torch

    raise SystemExit(main())
