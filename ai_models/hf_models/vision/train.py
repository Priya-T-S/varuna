"""
HuggingFace vision model fine-tuning pipeline.

    load satellite labels (same index as Phase 4)
    → chronological split
    → download HF backbone with pretrained weights
    → replace classification head (3 classes)
    → fine-tune head only for N epochs (backbone frozen)
    → evaluate on validation + test
    → save checkpoint (same format as satellite_model/train.py)
    → batch-extract scene features for the fusion model

Run (from repo root, using backend venv):
    backend/.venv/bin/python -m ai_models.hf_models.vision.train --model swin-tiny
    backend/.venv/bin/python -m ai_models.hf_models.vision.train --model vit-base
    backend/.venv/bin/python -m ai_models.hf_models.vision.train --model convnext-tiny

Options:
    --model        Vision model key (default: swin-tiny)
    --epochs       Fine-tuning epochs for the head (default: 6)
    --batch-size   Batch size (default: 16, reduce if OOM)
    --unfreeze     Number of top backbone layers to unfreeze (default: 0)
    --list         List available vision models and exit
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from typing import Any

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader

from ai_models.satellite_model import dataset as data_mod
from ai_models.satellite_model.config import REPO_ROOT, SatelliteConfig, resolve_device
from ai_models.satellite_model.evaluate import (
    collect_predictions,
    compute_metrics,
    plot_confusion_matrix,
    plot_training_curves,
    render_report,
)
from ai_models.hf_models.registry import build_vision_model, list_models, vision_keys
from ai_models.hf_models.vision.hf_vision import (
    HFVisionModel,
    build_hf_transforms,
    save_hf_checkpoint,
    unfreeze_top_layers,
)

logger = logging.getLogger(__name__)

# Default epochs per model family (reduce for faster experiments)
_DEFAULT_EPOCHS: dict[str, int] = {
    "vit-base": 6,
    "vit-large": 4,
    "swin-tiny": 8,
    "swin-base": 6,
    "beit-base": 6,
    "convnext-tiny": 8,
    "efficientnet-b4": 8,
}

_DEFAULT_BATCH: dict[str, int] = {
    "vit-large": 8,
    "swin-base": 12,
    "beit-base": 12,
    "vit-base": 16,
    "efficientnet-b4": 16,
    "swin-tiny": 16,
    "convnext-tiny": 24,
}


# ---------------------------------------------------------------------------
# Data loading — reuses Phase 4 SatelliteSceneDataset with HF transforms
# ---------------------------------------------------------------------------

class _HFSceneDataset(torch.utils.data.Dataset):
    """
    Wraps Phase 4 SatelliteSceneDataset but applies HuggingFace-compatible
    transforms instead of torchvision defaults, so there's no code duplication.
    """

    def __init__(
        self,
        index: "Any",
        config: SatelliteConfig,
        training: bool,
    ) -> None:
        self._base = data_mod.SatelliteSceneDataset(index, config, training=False)
        self._transform = build_hf_transforms(config.image_size, training=training)

    def __len__(self) -> int:
        return len(self._base)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        # SatelliteSceneDataset already returns (tensor, label) with torchvision
        # transforms. We re-open the raw image and apply HF transforms instead.
        # Faster path: just grab the PIL-convertible tensor from the base dataset
        tensor, label = self._base[idx]
        # Convert back to uint8 numpy, apply HF transform
        img = (tensor.permute(1, 2, 0).numpy() * 255).clip(0, 255).astype(np.uint8)
        return self._transform(img), label


def build_hf_loaders(
    splits: "data_mod.SplitFrames", config: SatelliteConfig, batch_size: int
) -> dict[str, DataLoader]:
    return {
        "train": DataLoader(
            _HFSceneDataset(splits.train, config, training=True),
            batch_size=batch_size, shuffle=True, num_workers=0,
        ),
        "val": DataLoader(
            _HFSceneDataset(splits.val, config, training=False),
            batch_size=batch_size, shuffle=False, num_workers=0,
        ),
        "test": DataLoader(
            _HFSceneDataset(splits.test, config, training=False),
            batch_size=batch_size, shuffle=False, num_workers=0,
        ),
    }


# ---------------------------------------------------------------------------
# Training loop
# ---------------------------------------------------------------------------

def train_hf_vision(
    key: str,
    model: nn.Module,
    loaders: dict[str, DataLoader],
    weights: torch.Tensor,
    device: str,
    epochs: int,
) -> dict[str, list[float]]:
    """Fine-tune *model* on train split; returns training history."""
    trainable_params = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(trainable_params, lr=3e-4, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    criterion = nn.CrossEntropyLoss(weight=weights.to(device))
    history: dict[str, list[float]] = {
        "train_loss": [], "val_loss": [], "val_accuracy": []
    }

    model.to(device)
    for epoch in range(1, epochs + 1):
        model.train()
        t0 = time.time()
        train_losses: list[float] = []
        for images, targets in loaders["train"]:
            optimizer.zero_grad()
            out = model(images.to(device))
            logits = out.logits if hasattr(out, "logits") else out
            loss = criterion(logits, targets.to(device))
            loss.backward()
            optimizer.step()
            train_losses.append(float(loss.item()))

        model.eval()
        val_losses: list[float] = []
        correct = total = 0
        with torch.no_grad():
            for images, targets in loaders["val"]:
                out = model(images.to(device))
                logits = out.logits if hasattr(out, "logits") else out
                val_losses.append(float(criterion(logits, targets.to(device)).item()))
                correct += int((logits.argmax(dim=1).cpu() == targets).sum())
                total += len(targets)

        scheduler.step()
        history["train_loss"].append(float(np.mean(train_losses)))
        history["val_loss"].append(float(np.mean(val_losses)))
        history["val_accuracy"].append(correct / max(total, 1))
        logger.info(
            "[%s] epoch %d/%d  train_loss=%.3f  val_loss=%.3f  val_acc=%.3f  (%.0fs)",
            key, epoch, epochs,
            history["train_loss"][-1], history["val_loss"][-1],
            history["val_accuracy"][-1], time.time() - t0,
        )
    return history


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Fine-tune a HuggingFace vision model on satellite imagery"
    )
    parser.add_argument(
        "--model", default="swin-tiny", choices=vision_keys(),
        help="Model key (default: swin-tiny)",
    )
    parser.add_argument("--list", action="store_true", help="List available vision models and exit")
    parser.add_argument(
        "--epochs", type=int, default=None,
        help="Fine-tuning epochs (default: model-specific, 4-8)",
    )
    parser.add_argument(
        "--batch-size", type=int, default=None, dest="batch_size",
        help="Batch size (default: model-specific, 8-24). Reduce if you see OOM errors.",
    )
    parser.add_argument(
        "--unfreeze", type=int, default=0, metavar="N",
        help="Also unfreeze top N backbone layers in addition to the head (default: 0).",
    )
    parser.add_argument("--version", default="v1", help="Artifact version tag")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )

    if args.list:
        list_models(modality="vision")
        return 0

    config = SatelliteConfig()
    config.ensure_output_dirs()
    device = resolve_device()
    torch.manual_seed(config.random_seed)
    logger.info("Device: %s", device)

    # ── Data ─────────────────────────────────────────────────────────────
    index = data_mod.load_labels(config)
    splits = data_mod.chronological_split(index, config)
    weights = data_mod.class_weights(splits.train, config.num_classes)

    batch_size = args.batch_size or _DEFAULT_BATCH.get(args.model, 16)
    epochs = args.epochs or _DEFAULT_EPOCHS.get(args.model, 6)
    logger.info("Model: %s  epochs: %d  batch_size: %d", args.model, epochs, batch_size)

    loaders = build_hf_loaders(splits, config, batch_size)

    # ── Build backbone ────────────────────────────────────────────────────
    model_adapter: HFVisionModel = build_vision_model(args.model)
    backbone, gradcam_layer = model_adapter.build_for_training(config.num_classes)

    if args.unfreeze > 0:
        unfreeze_top_layers(backbone, model_adapter.entry.hf_id, n_layers=args.unfreeze)
        logger.info("Unfroze top %d backbone layers", args.unfreeze)

    # ── Fine-tune ─────────────────────────────────────────────────────────
    history = train_hf_vision(
        args.model, backbone, loaders, weights, device, epochs
    )

    # ── Evaluate ─────────────────────────────────────────────────────────
    backbone.eval()
    backbone.to(device)

    def _collect(loader: DataLoader) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        all_labels, all_preds, all_probs = [], [], []
        with torch.no_grad():
            for images, targets in loader:
                out = backbone(images.to(device))
                logits = out.logits if hasattr(out, "logits") else out
                probs = torch.softmax(logits, dim=1).cpu().numpy()
                preds = probs.argmax(axis=1)
                all_labels.extend(targets.numpy())
                all_preds.extend(preds)
                all_probs.extend(probs)
        return (
            np.array(all_labels),
            np.array(all_preds),
            np.array(all_probs),
        )

    val_labels, val_preds, _ = _collect(loaders["val"])
    val_metrics = compute_metrics(val_labels, val_preds, config.num_classes)
    logger.info("[%s] val macro-F1: %.4f", args.model, val_metrics["f1_macro"])

    test_labels, test_preds, test_probs = _collect(loaders["test"])
    test_metrics = compute_metrics(test_labels, test_preds, config.num_classes)
    logger.info("[%s] test macro-F1: %.4f  accuracy: %.4f", args.model,
                test_metrics["f1_macro"], test_metrics["accuracy"])

    # ── Save checkpoint ───────────────────────────────────────────────────
    dataset_info = {
        "source": "NASA GIBS MODIS Terra (True Color + Band31 IR), real scenes",
        "scenes": len(index),
        "date_range": (str(index["date"].min()), str(index["date"].max())),
        "class_counts": {str(k): int(v) for k, v in
                         zip(*np.unique(index["label"].to_numpy(), return_counts=True))},
        "splits": {
            "train": len(splits.train),
            "val": len(splits.val),
            "test": len(splits.test),
        },
    }

    checkpoint_path = save_hf_checkpoint(
        key=args.model,
        hf_id=model_adapter.entry.hf_id,
        version=args.version,
        model=backbone,
        metrics={"validation": val_metrics, "test": test_metrics},
        dataset_info=dataset_info,
        gradcam_target_layer=gradcam_layer,
        num_classes=config.num_classes,
        image_size=config.image_size,
        artifact_dir=config.saved_models_dir,
    )

    # ── Report / experiment record ────────────────────────────────────────
    selection_reason = (
        f"HuggingFace pretrained backbone ({model_adapter.entry.hf_id}), "
        f"head fine-tuned for {epochs} epochs, "
        f"val macro-F1 = {val_metrics['f1_macro']:.3f}"
    )
    report_text = render_report(
        config, args.model, test_metrics,
        {args.model: val_metrics}, dataset_info, selection_reason,
    )
    report_path = config.reports_dir / f"hf_vision_{args.model}_report_{args.version}.txt"
    report_path.write_text(report_text + "\n", encoding="utf-8")

    curves_path = plot_training_curves({args.model: history}, config)
    confusion_path = plot_confusion_matrix(test_metrics, config)

    experiment_path = (
        config.experiments_dir
        / f"hf_vision_{args.model}_{args.version}.json"
    )
    experiment_path.write_text(
        json.dumps(
            {
                "model": args.model,
                "hf_id": model_adapter.entry.hf_id,
                "version": args.version,
                "epochs": epochs,
                "batch_size": batch_size,
                "unfreeze_layers": args.unfreeze,
                "device": device,
                "validation": val_metrics,
                "test": test_metrics,
                "dataset": dataset_info,
                "artifacts": {
                    "checkpoint": str(checkpoint_path),
                    "report": str(report_path),
                    "curves": curves_path,
                    "confusion_matrix": confusion_path,
                },
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    print(report_text)
    print(f"\nCheckpoint: {checkpoint_path}")
    print(f"Report:     {report_path}")
    print(f"Experiment: {experiment_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
