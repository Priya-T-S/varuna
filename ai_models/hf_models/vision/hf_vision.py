"""
HuggingFace vision model adapter — implements the project-wide RainfallModel interface.

All models are loaded with pretrained ImageNet weights from the HuggingFace Hub.
Only the classification head is replaced with a 3-class linear layer and trained
on your satellite imagery — the backbone stays frozen unless --unfreeze-layers is set.

Supported keys (from registry.py):
    vit-base      google/vit-base-patch16-224
    vit-large     google/vit-large-patch16-224
    swin-tiny     microsoft/swin-tiny-patch4-window7-224  ← recommended
    swin-base     microsoft/swin-base-patch4-window7-224
    beit-base     microsoft/beit-base-patch16-224-pt22k-ft22k
    convnext-tiny facebook/convnext-tiny-224
    efficientnet-b4 google/efficientnet-b4

Checkpoint format:
    Identical to satellite_model/save_checkpoint — same keys, same path convention —
    so the existing fusion pipeline and Grad-CAM explainer work unchanged.

CLI:
    # List models
    python -m ai_models.hf_models.vision.hf_vision --list

    # Smoke-test (downloads pretrained weights, no real imagery needed)
    python -m ai_models.hf_models.vision.hf_vision --smoke-test --model swin-tiny
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import torch
from torch import nn
from torchvision import transforms as T

from ai_models.base import ModelOutput, RainfallModel
from ai_models.satellite_model.config import SatelliteConfig, resolve_device

if TYPE_CHECKING:
    from ai_models.hf_models.registry import _ModelEntry

logger = logging.getLogger(__name__)

_CHECKPOINT_TEMPLATE = "hf_vision_{key}_{version}.pt"

_RISK_BY_CATEGORY: dict[int, str] = {0: "low", 1: "heavy", 2: "extreme"}
_LABEL_NAMES: dict[int, str] = {0: "Normal", 1: "Heavy", 2: "Extreme"}

# ImageNet statistics — all HF vision models expect these
_IMAGENET_MEAN = (0.485, 0.456, 0.406)
_IMAGENET_STD = (0.229, 0.224, 0.225)


# ---------------------------------------------------------------------------
# Backbone factory — download pretrained weights, replace head
# ---------------------------------------------------------------------------

def _build_hf_backbone(hf_id: str, num_classes: int) -> tuple[nn.Module, str]:
    """
    Download *hf_id* from HuggingFace Hub with pretrained weights, replace
    its classification head with a new linear layer for *num_classes* outputs,
    and return (model, gradcam_target_layer_name).

    The backbone parameters are frozen; only the new head is trainable.
    Call unfreeze_top_layers() to open up the last N transformer blocks.
    """
    from transformers import AutoModelForImageClassification, AutoConfig

    logger.info("Loading pretrained backbone: %s …", hf_id)
    config = AutoConfig.from_pretrained(hf_id)
    model = AutoModelForImageClassification.from_pretrained(
        hf_id,
        num_labels=num_classes,
        ignore_mismatched_sizes=True,  # replaces the pre-trained head
    )

    # Freeze all backbone parameters
    for name, param in model.named_parameters():
        param.requires_grad = False

    # The head is already replaced by ignore_mismatched_sizes=True with a
    # freshly initialised linear layer; unfreeze it.
    head = _get_head(model, hf_id)
    for param in head.parameters():
        param.requires_grad = True

    # Best-effort GradCAM target layer (last normalisation / feature block)
    gradcam_layer = _gradcam_layer_name(hf_id, model)

    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    logger.info(
        "Backbone ready — trainable params: %s / %s (%.1f%%)",
        f"{trainable:,}", f"{total:,}", 100 * trainable / max(total, 1),
    )
    return model, gradcam_layer


def _get_head(model: nn.Module, hf_id: str) -> nn.Module:
    """Return the classification head module so we can unfreeze it."""
    for attr in ("classifier", "head", "fc"):
        if hasattr(model, attr):
            return getattr(model, attr)
    # Fallback: return the whole model (fine-tune everything)
    return model


def _gradcam_layer_name(hf_id: str, model: nn.Module) -> str:
    """Best-effort last feature layer name for Grad-CAM."""
    hf_id_lower = hf_id.lower()
    if "swin" in hf_id_lower:
        return "swin.layernorm"
    if "convnext" in hf_id_lower:
        return "convnext.layernorm"
    if "efficientnet" in hf_id_lower:
        return "efficientnet.top_conv"
    if "beit" in hf_id_lower:
        return "beit.layernorm"
    # ViT: use encoder layer norm
    return "vit.layernorm"


def unfreeze_top_layers(model: nn.Module, hf_id: str, n_layers: int = 2) -> None:
    """
    Unfreeze the top *n_layers* transformer blocks of the backbone.

    Call this before fine-tuning if you want the backbone to also adapt
    (recommended for swin-tiny and convnext-tiny when you have enough data).
    """
    hf_id_lower = hf_id.lower()
    if "swin" in hf_id_lower:
        _unfreeze_attr_layers(model, "swin.encoder.layers", n_layers)
    elif "vit" in hf_id_lower:
        _unfreeze_attr_layers(model, "vit.encoder.layer", n_layers)
    elif "beit" in hf_id_lower:
        _unfreeze_attr_layers(model, "beit.encoder.layer", n_layers)
    elif "convnext" in hf_id_lower:
        _unfreeze_attr_layers(model, "convnext.encoder.stages", n_layers)
    else:
        logger.warning("unfreeze_top_layers: unknown model family for %s — skipping", hf_id)
        return
    newly_trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    logger.info("After unfreezing top %d layers — trainable params: %s", n_layers, f"{newly_trainable:,}")


def _unfreeze_attr_layers(model: nn.Module, dotpath: str, n: int) -> None:
    """Walk a dotted attribute path and unfreeze the last n items of the sequence."""
    obj = model
    for part in dotpath.split("."):
        obj = getattr(obj, part, None)
        if obj is None:
            logger.warning("_unfreeze_attr_layers: path %r not found", dotpath)
            return
    try:
        layers = list(obj)
    except TypeError:
        return
    for layer in layers[-n:]:
        for param in layer.parameters():
            param.requires_grad = True


# ---------------------------------------------------------------------------
# Preprocessing — HuggingFace processor OR simple torchvision transforms
# ---------------------------------------------------------------------------

def build_hf_transforms(image_size: int = 224, training: bool = False) -> Any:
    """Build torchvision transforms compatible with all HF vision models.

    We intentionally use torchvision instead of the HF AutoProcessor so the
    transforms compose with the existing SatelliteSceneDataset.
    """
    if training:
        return T.Compose([
            T.ToPILImage(),
            T.RandomResizedCrop(image_size, scale=(0.8, 1.0)),
            T.RandomHorizontalFlip(),
            T.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.1),
            T.ToTensor(),
            T.Normalize(mean=_IMAGENET_MEAN, std=_IMAGENET_STD),
        ])
    return T.Compose([
        T.ToPILImage(),
        T.Resize((image_size, image_size)),
        T.ToTensor(),
        T.Normalize(mean=_IMAGENET_MEAN, std=_IMAGENET_STD),
    ])


# ---------------------------------------------------------------------------
# Checkpoint I/O — identical format to satellite_model/model.py
# ---------------------------------------------------------------------------

def save_hf_checkpoint(
    *,
    key: str,
    hf_id: str,
    version: str,
    model: nn.Module,
    metrics: dict[str, Any],
    dataset_info: dict[str, Any],
    gradcam_target_layer: str,
    num_classes: int,
    image_size: int,
    artifact_dir: Path,
) -> Path:
    payload = {
        "hf_id": hf_id,
        "key": key,
        "version": version,
        "model_name": key,  # mirrors satellite checkpoint 'model_name' key
        "state_dict": {k: v.cpu() for k, v in model.state_dict().items()},
        "num_classes": num_classes,
        "image_size": image_size,
        "label_names": _LABEL_NAMES,
        "gradcam_target_layer": gradcam_target_layer,
        "metrics": metrics,
        "dataset_info": dataset_info,
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / _CHECKPOINT_TEMPLATE.format(key=key, version=version)
    torch.save(payload, path)
    logger.info("Saved HF vision checkpoint: %s (%s)", path, key)
    return path


def load_hf_checkpoint(path: Path, device: str | None = None) -> tuple[nn.Module, dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(
            f"No HF vision checkpoint at {path}. "
            f"Run `python -m ai_models.hf_models.vision.train --model <key>` first."
        )
    device = device or resolve_device()
    payload = torch.load(path, map_location=device, weights_only=False)
    model, _ = _build_hf_backbone(payload["hf_id"], payload["num_classes"])
    model.load_state_dict(payload["state_dict"])
    model.to(device).eval()
    return model, payload


# ---------------------------------------------------------------------------
# Public adapter — implements RainfallModel
# ---------------------------------------------------------------------------

class HFVisionModel(RainfallModel):
    """
    RainfallModel adapter for HuggingFace vision models.

    Drop-in replacement for SatelliteRainfallModel:
      - Same checkpoint format → works with existing fusion pipeline
      - Same gradcam_target_layer field → works with existing Grad-CAM explainer
      - Same predict() signature and ModelOutput structure

    Usage (inference only, after training):
        model = HFVisionModel(key="swin-tiny", entry=registry.get_entry("swin-tiny"))
        model.load(artifact_dir)
        output = model.predict(features=None, image=rgb_array)
    """

    def __init__(self, key: str, entry: "_ModelEntry") -> None:
        self.key = key
        self.entry = entry
        self._model: nn.Module | None = None
        self._meta: dict[str, Any] | None = None
        self._device = resolve_device()
        self._transform: Any = None

    # ------------------------------------------------------------------
    # RainfallModel interface
    # ------------------------------------------------------------------

    def load(self, artifact_dir: Path) -> None:
        config = SatelliteConfig()
        path = Path(artifact_dir) / _CHECKPOINT_TEMPLATE.format(
            key=self.key, version=config.model_version
        )
        self._model, self._meta = load_hf_checkpoint(path, self._device)
        self._transform = build_hf_transforms(
            self._meta.get("image_size", 224), training=False
        )
        self.version = self._meta["version"]
        logger.info("Loaded HF vision model '%s' v%s", self.key, self.version)

    def predict(self, features: dict[str, float] | None, image: np.ndarray | None) -> ModelOutput:
        if self._model is None or self._meta is None:
            raise RuntimeError("Model not loaded — call load() first")
        if image is None:
            raise ValueError(f"HF vision model '{self.key}' requires an image input")

        tensor = self._transform(image.astype(np.uint8)).unsqueeze(0).to(self._device)
        with torch.no_grad():
            logits = self._model(tensor)
            # HF models return a ModelOutput object; get the logits tensor
            if hasattr(logits, "logits"):
                logits = logits.logits
            probabilities = torch.softmax(logits, dim=1)[0].cpu().numpy()

        category = int(np.argmax(probabilities))
        return ModelOutput(
            probability=float(probabilities[1:].sum()),
            risk_level=_RISK_BY_CATEGORY[category],
            confidence=float(probabilities.max()),
            model_version=f"hf-vision-{self.key}-{self._meta['version']}",
            explanation_context={
                "class_probabilities": {
                    _LABEL_NAMES[i]: float(p) for i, p in enumerate(probabilities)
                },
                "gradcam_target_layer": self._meta["gradcam_target_layer"],
            },
        )

    def feature_names(self) -> list[str]:
        return []  # image model — no tabular features

    # ------------------------------------------------------------------
    # Training helpers (called by train.py)
    # ------------------------------------------------------------------

    def build_for_training(
        self, num_classes: int = 3
    ) -> tuple[nn.Module, str]:
        """Download pretrained backbone and return (model, gradcam_layer)."""
        assert self.entry.hf_id is not None, f"No HF ID for {self.key!r}"
        return _build_hf_backbone(self.entry.hf_id, num_classes)


# ---------------------------------------------------------------------------
# Smoke-test / CLI
# ---------------------------------------------------------------------------

def _smoke_test(key: str) -> None:
    """Verify model download and a single forward pass with a random image."""
    from ai_models.hf_models.registry import build_vision_model

    print(f"\n[smoke-test] HF vision model: {key}")
    model_adapter = build_vision_model(key)
    backbone, gradcam_layer = model_adapter.build_for_training(num_classes=3)
    backbone.eval()

    rng = np.random.default_rng(0)
    dummy_image = (rng.integers(0, 256, size=(224, 224, 3))).astype(np.uint8)
    transform = build_hf_transforms(224, training=False)
    tensor = transform(dummy_image).unsqueeze(0)

    with torch.no_grad():
        out = backbone(tensor)
        logits = out.logits if hasattr(out, "logits") else out

    proba = torch.softmax(logits, dim=1)[0].numpy()
    assert proba.shape == (3,), f"Expected (3,) got {proba.shape}"
    assert abs(proba.sum() - 1.0) < 1e-5, "Probabilities must sum to 1"
    print(f"  GradCAM layer: {gradcam_layer}")
    print(f"  Class probabilities: {proba.round(3)}")
    print(f"  Predicted class: {int(proba.argmax())}")
    print("[smoke-test] PASSED ✓\n")


def main(argv: list[str] | None = None) -> int:
    from ai_models.hf_models.registry import list_models, vision_keys

    parser = argparse.ArgumentParser(description="HuggingFace vision model utilities")
    parser.add_argument("--list", action="store_true", help="List available vision models")
    parser.add_argument("--smoke-test", action="store_true", dest="smoke")
    parser.add_argument(
        "--model",
        default="swin-tiny",
        choices=vision_keys(),
        help="Model key to smoke-test (default: swin-tiny)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    if args.list:
        list_models(modality="vision")
        return 0
    if args.smoke:
        _smoke_test(args.model)
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
