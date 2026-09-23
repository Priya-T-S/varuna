"""
HuggingFace vision model prediction CLI.

Same input/output interface as ai_models.satellite_model.predict — the backend
can swap to any HF vision model without changes.

CLI:
    backend/.venv/bin/python -m ai_models.hf_models.vision.predict \\
        --model swin-tiny \\
        --input '{"satellite_image_path": "data/raw/satellite/.../kerala_2018-08-15.jpg",
                  "timestamp": "2018-08-15T05:15:00Z",
                  "latitude": 10.0, "longitude": 76.3}'
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import torch

from ai_models.satellite_model.config import REPO_ROOT, SatelliteConfig, resolve_device
from ai_models.satellite_model.preprocessing import (
    ImageLoadError,
    build_transforms,
    extract_scene_features,
    load_rgb,
)
from ai_models.hf_models.registry import build_vision_model, vision_keys
from ai_models.hf_models.vision.hf_vision import (
    _CHECKPOINT_TEMPLATE,
    _LABEL_NAMES,
    build_hf_transforms,
    load_hf_checkpoint,
)

logger = logging.getLogger(__name__)


class InvalidInputError(ValueError):
    """Raised when prediction input is malformed."""


class ModelNotTrainedError(RuntimeError):
    """Raised when no trained HF vision checkpoint exists."""


_PATTERN_BY_CATEGORY = {0: "Low Risk", 1: "High Risk", 2: "Extreme Risk"}


# ---------------------------------------------------------------------------
# Predictor
# ---------------------------------------------------------------------------

class HFVisionPredictor:
    """Loads a trained HF vision checkpoint and serves scene predictions."""

    def __init__(self, model_key: str = "swin-tiny", model_path: Path | None = None) -> None:
        config = SatelliteConfig()
        self._key = model_key
        self._device = resolve_device()

        path = model_path or (
            config.saved_models_dir
            / _CHECKPOINT_TEMPLATE.format(key=model_key, version=config.model_version)
        )
        try:
            self._model, self._meta = load_hf_checkpoint(path, self._device)
        except FileNotFoundError as exc:
            raise ModelNotTrainedError(str(exc)) from exc

        self._transform = build_hf_transforms(
            self._meta.get("image_size", 224), training=False
        )
        logger.info(
            "Loaded HF vision model '%s' v%s", model_key, self._meta.get("version", "?")
        )

    def predict(self, payload: dict[str, Any]) -> dict[str, Any]:
        image_path, ir_path, previous_path = self._validate(payload)
        image = load_rgb(image_path)

        tensor = self._transform(image.astype(np.uint8)).unsqueeze(0).to(self._device)
        with torch.no_grad():
            out = self._model(tensor)
            logits = out.logits if hasattr(out, "logits") else out
            probabilities = torch.softmax(logits, dim=1)[0].cpu().numpy()

        category = int(np.argmax(probabilities))
        max_probability = float(probabilities.max())

        features: dict[str, Any] | None = None
        try:
            features = extract_scene_features(image_path, ir_path, previous_path)
        except ImageLoadError as exc:
            logger.warning("Scene features unavailable: %s", exc)

        return {
            "satellite_risk_score": round(float(probabilities[1:].sum()), 4),
            "cloud_pattern": _PATTERN_BY_CATEGORY[category],
            "cloud_condition": _LABEL_NAMES[category],
            "category": category,
            "class_probabilities": {
                _LABEL_NAMES[i]: round(float(p), 4) for i, p in enumerate(probabilities)
            },
            "confidence": (
                "High" if max_probability >= 0.75
                else "Medium" if max_probability >= 0.5
                else "Low"
            ),
            "scene_features": features,
            "model": f"hf-vision-{self._key}-{self._meta.get('version', 'v1')}",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    def _validate(
        self, payload: dict[str, Any]
    ) -> tuple[Path, Path | None, Path | None]:
        if not isinstance(payload, dict):
            raise InvalidInputError("Input must be a JSON object")
        raw_path = payload.get("satellite_image_path")
        if not raw_path or not isinstance(raw_path, str):
            raise InvalidInputError("Missing required field: satellite_image_path")
        image_path = Path(raw_path)
        if not image_path.is_absolute():
            image_path = REPO_ROOT / image_path
        if not image_path.is_file():
            raise InvalidInputError(f"Satellite image does not exist: {image_path}")

        for field, lo, hi in (("latitude", -90.0, 90.0), ("longitude", -180.0, 180.0)):
            if field in payload and payload[field] is not None:
                try:
                    value = float(payload[field])
                except (TypeError, ValueError) as exc:
                    raise InvalidInputError(f"Field {field} is not numeric") from exc
                if not (lo <= value <= hi):
                    raise InvalidInputError(f"Field {field}={value} outside [{lo}, {hi}]")

        def optional_path(key: str) -> Path | None:
            value = payload.get(key)
            if not value:
                return None
            p = Path(value)
            return p if p.is_absolute() else REPO_ROOT / p

        return image_path, optional_path("ir_image_path"), optional_path("previous_image_path")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="HuggingFace vision model satellite scene prediction"
    )
    parser.add_argument("--input", required=True, help="JSON object (see module docstring)")
    parser.add_argument(
        "--model", default="swin-tiny", choices=vision_keys(),
        help="HF vision model key (default: swin-tiny)",
    )
    parser.add_argument("--model-path", type=Path, default=None)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.WARNING)
    try:
        payload = json.loads(args.input)
        result = HFVisionPredictor(
            model_key=args.model, model_path=args.model_path
        ).predict(payload)
    except (InvalidInputError, ModelNotTrainedError, ImageLoadError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
