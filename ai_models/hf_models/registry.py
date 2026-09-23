"""
Central registry of all supported HuggingFace models.

Usage
-----
    from ai_models.hf_models.registry import list_models, build_tabular_model, build_vision_model

    list_models()                          # print a table of all available models
    model = build_tabular_model("tabpfn")  # instantiate a tabular adapter
    model = build_vision_model("swin-tiny")# instantiate a vision adapter

Each entry in the registry carries:
  - hf_id        : HuggingFace model-hub identifier (or None for custom architectures)
  - description  : one-liner for the help text / list_models()
  - needs_training: False means pretrained weights are used as-is (e.g. TabPFN zero-shot)
                    True  means the HF backbone is downloaded but the classification head
                    must be fine-tuned on your data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_models.hf_models.tabular.hf_tabular import HFTabularModel
    from ai_models.hf_models.vision.hf_vision import HFVisionModel


# ---------------------------------------------------------------------------
# Registry definitions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _ModelEntry:
    key: str
    hf_id: str | None
    description: str
    needs_training: bool
    modality: str  # "tabular" | "vision"


_REGISTRY: list[_ModelEntry] = [
    # ── Tabular ────────────────────────────────────────────────────────────
    _ModelEntry(
        key="tabpfn",
        hf_id="prior-labs/TabPFN",
        description="TabPFN — zero-shot tabular foundation model (no training needed). "
                    "Excellent on small, imbalanced datasets like this one.",
        needs_training=False,
        modality="tabular",
    ),
    _ModelEntry(
        key="fttransformer",
        hf_id=None,
        description="FT-Transformer — Feature-Tokenizer Transformer for tabular data. "
                    "Requires fine-tuning (~few minutes on CPU).",
        needs_training=True,
        modality="tabular",
    ),
    # ── Vision ─────────────────────────────────────────────────────────────
    _ModelEntry(
        key="vit-base",
        hf_id="google/vit-base-patch16-224",
        description="ViT-Base/16 — Vision Transformer (ImageNet-21k pretrained). "
                    "Fine-tune classification head only.",
        needs_training=True,
        modality="vision",
    ),
    _ModelEntry(
        key="vit-large",
        hf_id="google/vit-large-patch16-224",
        description="ViT-Large/16 — larger ViT, stronger but needs more GPU RAM.",
        needs_training=True,
        modality="vision",
    ),
    _ModelEntry(
        key="swin-tiny",
        hf_id="microsoft/swin-tiny-patch4-window7-224",
        description="Swin-Tiny — hierarchical Swin Transformer. Great accuracy/speed "
                    "trade-off for satellite imagery. ✅ Recommended.",
        needs_training=True,
        modality="vision",
    ),
    _ModelEntry(
        key="swin-base",
        hf_id="microsoft/swin-base-patch4-window7-224",
        description="Swin-Base — stronger Swin, needs more memory.",
        needs_training=True,
        modality="vision",
    ),
    _ModelEntry(
        key="beit-base",
        hf_id="microsoft/beit-base-patch16-224-pt22k-ft22k",
        description="BEiT-Base — BERT-style pre-training on ImageNet-22k.",
        needs_training=True,
        modality="vision",
    ),
    _ModelEntry(
        key="convnext-tiny",
        hf_id="facebook/convnext-tiny-224",
        description="ConvNeXt-Tiny — pure-CNN with transformer design principles. "
                    "Fast fine-tuning, good for limited hardware.",
        needs_training=True,
        modality="vision",
    ),
    _ModelEntry(
        key="efficientnet-b4",
        hf_id="google/efficientnet-b4",
        description="EfficientNet-B4 — compact and accurate CNN backbone.",
        needs_training=True,
        modality="vision",
    ),
]

# Fast lookup maps
_BY_KEY: dict[str, _ModelEntry] = {e.key: e for e in _REGISTRY}
_TABULAR_KEYS: list[str] = [e.key for e in _REGISTRY if e.modality == "tabular"]
_VISION_KEYS: list[str] = [e.key for e in _REGISTRY if e.modality == "vision"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_models(modality: str | None = None) -> None:
    """Print a formatted table of available HuggingFace models.

    Args:
        modality: filter to "tabular" or "vision". None shows all.
    """
    entries = [e for e in _REGISTRY if modality is None or e.modality == modality]
    col_w = 16
    print(f"\n{'Key':<{col_w}} {'Modality':<10} {'Train?':<8} Description")
    print("-" * 90)
    for e in entries:
        train_str = "No (zero-shot)" if not e.needs_training else "Yes (head only)"
        print(f"{e.key:<{col_w}} {e.modality:<10} {train_str:<15} {e.description.split('—')[0].strip()}")
    print()


def get_entry(key: str) -> _ModelEntry:
    """Return registry entry for *key* or raise ValueError."""
    if key not in _BY_KEY:
        valid = ", ".join(_BY_KEY)
        raise ValueError(f"Unknown model key {key!r}. Valid keys: {valid}")
    return _BY_KEY[key]


def tabular_keys() -> list[str]:
    """Ordered list of supported tabular model keys."""
    return list(_TABULAR_KEYS)


def vision_keys() -> list[str]:
    """Ordered list of supported vision model keys."""
    return list(_VISION_KEYS)


def build_tabular_model(key: str) -> "HFTabularModel":
    """Instantiate a tabular model adapter by registry key."""
    entry = get_entry(key)
    if entry.modality != "tabular":
        raise ValueError(f"{key!r} is a vision model, not tabular. Use build_vision_model().")
    from ai_models.hf_models.tabular.hf_tabular import HFTabularModel
    return HFTabularModel(key=key, entry=entry)


def build_vision_model(key: str) -> "HFVisionModel":
    """Instantiate a vision model adapter by registry key."""
    entry = get_entry(key)
    if entry.modality != "vision":
        raise ValueError(f"{key!r} is a tabular model, not vision. Use build_tabular_model().")
    from ai_models.hf_models.vision.hf_vision import HFVisionModel
    return HFVisionModel(key=key, entry=entry)
