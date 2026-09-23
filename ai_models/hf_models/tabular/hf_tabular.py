"""
HuggingFace tabular model adapters — implements the project-wide RainfallModel interface.

Two strategies are supported, selected via the registry key:

    "tabpfn"        — TabPFN (prior-labs/TabPFN)
        A zero-shot tabular foundation model. No training loop needed at all:
        call fit() once with your training data and it works immediately.
        Ideal for this project's small, imbalanced dataset (~2 700 train rows).

    "fttransformer"  — FT-Transformer (custom PyTorch, no HF backbone)
        A Feature-Tokenizer Transformer that tokenises each numeric column
        independently, then applies multi-head self-attention. Needs a short
        fine-tuning run (~5–15 min on CPU for this dataset size).

Both adapters save/load artifacts with joblib in the same saved_models directory
used by the existing baseline pipeline, so they are interchangeable with
BaselineRainfallModel in the backend and fusion model.

CLI
---
    # List all available tabular models
    python -m ai_models.hf_models.tabular.hf_tabular --list

    # Smoke-test (generates random data, no real dataset needed)
    python -m ai_models.hf_models.tabular.hf_tabular --smoke-test --model tabpfn
    python -m ai_models.hf_models.tabular.hf_tabular --smoke-test --model fttransformer
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import joblib
import numpy as np
import pandas as pd

from ai_models.base import ModelOutput, RainfallModel
from ai_models.baseline.config import BaselineConfig

if TYPE_CHECKING:
    from ai_models.hf_models.registry import _ModelEntry

logger = logging.getLogger(__name__)

# Artifact filename — versioned alongside existing baseline bundles
_HF_TAB_BUNDLE_TEMPLATE = "hf_tabular_{key}_{version}.pkl"

# Feature names identical to the baseline pipeline
_FEATURE_NAMES: list[str] = [
    "temperature_c",
    "humidity_pct",
    "pressure_hpa",
    "wind_speed_ms",
    "wind_direction_deg",
    "cloud_cover_pct",
    "rain_sum_1d",
    "rain_sum_3d",
    "rain_sum_7d",
    "rain_sum_30d",
    "rain_trend_3d",
    "season_sin",
    "season_cos",
]

_RISK_BY_CATEGORY: dict[int, str] = {0: "low", 1: "heavy", 2: "extreme"}
_LABEL_NAMES: dict[int, str] = {0: "Normal Rainfall", 1: "Heavy Rainfall", 2: "Extreme Rainfall"}


# ---------------------------------------------------------------------------
# Internal strategy classes
# ---------------------------------------------------------------------------

class _TabPFNStrategy:
    """
    Wraps the TabPFN classifier from prior-labs.

    TabPFN is a *prior-data fitted network* — it was meta-trained on millions
    of synthetic tabular datasets and can classify new data zero-shot after
    seeing your training rows once via fit().  No gradient descent is run on
    your data; fit() just stores the training set in memory.

    Docs / paper: https://huggingface.co/prior-labs/TabPFN
    """

    name = "tabpfn"

    def __init__(self) -> None:
        self._clf: Any = None

    def fit(self, x: np.ndarray, y: np.ndarray) -> "_TabPFNStrategy":
        try:
            from tabpfn import TabPFNClassifier  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "TabPFN is not installed. Run: pip install tabpfn"
            ) from exc

        # TabPFN v2 is a gated HuggingFace model. Authenticate via:
        #   Option 1: hf auth login (one-time browser login)
        #   Option 2: export HF_TOKEN=<your_read_token>
        #   Get a token at: https://huggingface.co/settings/tokens
        #   Accept terms at: https://huggingface.co/Prior-Labs/tabpfn_3
        import os
        hf_token = os.environ.get("HF_TOKEN")
        try:
            if hf_token:
                self._clf = TabPFNClassifier()
            else:
                self._clf = TabPFNClassifier()
            logger.info("[TabPFN] Fitting (zero-shot — just storing training set) …")
            self._clf.fit(x, y)
        except Exception as exc:
            exc_str = str(exc)
            if "gated" in exc_str.lower() or "license" in exc_str.lower() or "auth" in exc_str.lower():
                raise RuntimeError(
                    "TabPFN requires two one-time setup steps:\n"
                    "\n"
                    "Step 1 — Accept HuggingFace terms:\n"
                    "  Visit: https://huggingface.co/Prior-Labs/tabpfn_3\n"
                    "  Click 'Agree and access repository'\n"
                    "\n"
                    "Step 2 — Accept PriorLabs license (separate system):\n"
                    "  Visit: https://ux.priorlabs.ai\n"
                    "  Log in → Licenses tab → Accept\n"
                    "  Copy your API key from https://ux.priorlabs.ai/account\n"
                    "  Then run: export TABPFN_TOKEN=\"<your-api-key>\"\n"
                    "\n"
                    "Alternatively, use --model fttransformer (no auth needed).\n"
                    f"\nOriginal error: {exc}"
                ) from exc
            raise
        logger.info("[TabPFN] Ready.")
        return self

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        if self._clf is None:
            raise RuntimeError("TabPFN not fitted — call fit() first")
        return np.asarray(self._clf.predict_proba(x), dtype=np.float64)

    def state(self) -> dict[str, Any]:
        return {"clf": self._clf}

    def load_state(self, state: dict[str, Any]) -> None:
        self._clf = state["clf"]


class _FTTransformerStrategy:
    """
    Feature-Tokenizer Transformer for tabular data (Gorishniy et al. 2021).

    Each numeric feature is projected to a d-dimensional embedding via a
    dedicated linear "tokenizer". The resulting sequence of tokens is then
    processed by standard Transformer encoder blocks. A [CLS]-style appended
    token produces the final class logits.

    Architecture is implemented in pure PyTorch here (no HF backbone) to
    keep the dependency surface small; the key innovations (per-feature
    tokenisation + attention) are what matter for tabular data.
    """

    name = "fttransformer"

    def __init__(
        self,
        d_token: int = 64,
        n_heads: int = 8,
        n_layers: int = 3,
        dropout: float = 0.1,
        lr: float = 1e-3,
        weight_decay: float = 1e-5,
        n_epochs: int = 50,
        batch_size: int = 256,
        seed: int = 42,
        num_classes: int = 3,
    ) -> None:
        self.d_token = d_token
        self.n_heads = n_heads
        self.n_layers = n_layers
        self.dropout = dropout
        self.lr = lr
        self.weight_decay = weight_decay
        self.n_epochs = n_epochs
        self.batch_size = batch_size
        self.seed = seed
        self.num_classes = num_classes
        self._model: Any = None
        self._scaler_mean: np.ndarray | None = None
        self._scaler_std: np.ndarray | None = None
        self._n_features: int = 0

    # ------------------------------------------------------------------
    def fit(self, x: np.ndarray, y: np.ndarray) -> "_FTTransformerStrategy":
        import torch
        from torch import nn
        from torch.utils.data import DataLoader, TensorDataset
        from sklearn.utils.class_weight import compute_class_weight

        torch.manual_seed(self.seed)
        self._n_features = x.shape[1]

        # z-score normalise (tabular transformers are sensitive to scale)
        self._scaler_mean = x.mean(axis=0)
        self._scaler_std = x.std(axis=0) + 1e-8
        x_scaled = (x - self._scaler_mean) / self._scaler_std

        x_t = torch.tensor(x_scaled, dtype=torch.float32)
        y_t = torch.tensor(y, dtype=torch.long)

        self._model = _FTTransformerNet(
            n_features=self._n_features,
            d_token=self.d_token,
            n_heads=self.n_heads,
            n_layers=self.n_layers,
            dropout=self.dropout,
            num_classes=self.num_classes,
        )

        # Class-weighted cross-entropy to counter imbalance
        classes = np.unique(y)
        raw_weights = compute_class_weight("balanced", classes=np.arange(self.num_classes), y=y)
        weights = torch.tensor(raw_weights, dtype=torch.float32)

        optimizer = torch.optim.AdamW(
            self._model.parameters(), lr=self.lr, weight_decay=self.weight_decay
        )
        criterion = nn.CrossEntropyLoss(weight=weights)
        loader = DataLoader(
            TensorDataset(x_t, y_t), batch_size=self.batch_size, shuffle=True
        )

        self._model.train()
        for epoch in range(1, self.n_epochs + 1):
            epoch_losses = []
            for xb, yb in loader:
                optimizer.zero_grad()
                loss = criterion(self._model(xb), yb)
                loss.backward()
                optimizer.step()
                epoch_losses.append(float(loss.item()))
            if epoch % 10 == 0 or epoch == 1:
                logger.info(
                    "[FTTransformer] epoch %d/%d  loss %.4f",
                    epoch, self.n_epochs, float(np.mean(epoch_losses)),
                )
        self._model.eval()
        return self

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        import torch

        if self._model is None or self._scaler_mean is None:
            raise RuntimeError("FTTransformer not fitted — call fit() first")
        x_scaled = (x - self._scaler_mean) / self._scaler_std
        with torch.no_grad():
            logits = self._model(torch.tensor(x_scaled, dtype=torch.float32))
            return torch.softmax(logits, dim=1).numpy().astype(np.float64)

    def state(self) -> dict[str, Any]:
        import torch
        import io
        buf = io.BytesIO()
        torch.save(self._model.state_dict(), buf)
        return {
            "state_dict_bytes": buf.getvalue(),
            "n_features": self._n_features,
            "d_token": self.d_token,
            "n_heads": self.n_heads,
            "n_layers": self.n_layers,
            "dropout": self.dropout,
            "num_classes": self.num_classes,
            "scaler_mean": self._scaler_mean,
            "scaler_std": self._scaler_std,
        }

    def load_state(self, state: dict[str, Any]) -> None:
        import torch
        import io
        self._n_features = state["n_features"]
        self.d_token = state["d_token"]
        self.n_heads = state["n_heads"]
        self.n_layers = state["n_layers"]
        self.dropout = state["dropout"]
        self.num_classes = state["num_classes"]
        self._scaler_mean = state["scaler_mean"]
        self._scaler_std = state["scaler_std"]
        self._model = _FTTransformerNet(
            n_features=self._n_features,
            d_token=self.d_token,
            n_heads=self.n_heads,
            n_layers=self.n_layers,
            dropout=self.dropout,
            num_classes=self.num_classes,
        )
        buf = io.BytesIO(state["state_dict_bytes"])
        self._model.load_state_dict(torch.load(buf, map_location="cpu", weights_only=True))
        self._model.eval()


def _FTTransformerNet(
    *,
    n_features: int,
    d_token: int,
    n_heads: int,
    n_layers: int,
    dropout: float,
    num_classes: int,
) -> "Any":
    """Build the FT-Transformer network (defined lazily so torch stays optional)."""
    import torch
    from torch import nn

    class _Net(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            # Per-feature linear tokenizers (no shared weights)
            self.tokenizers = nn.ModuleList(
                [nn.Linear(1, d_token) for _ in range(n_features)]
            )
            # Learnable [CLS] token appended to the token sequence
            self.cls_token = nn.Parameter(torch.zeros(1, 1, d_token))
            encoder_layer = nn.TransformerEncoderLayer(
                d_model=d_token,
                nhead=n_heads,
                dim_feedforward=d_token * 4,
                dropout=dropout,
                batch_first=True,
                norm_first=True,
            )
            self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=n_layers)
            self.norm = nn.LayerNorm(d_token)
            self.head = nn.Linear(d_token, num_classes)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            # x: (batch, n_features)
            tokens = torch.stack(
                [tok(x[:, i : i + 1]) for i, tok in enumerate(self.tokenizers)],
                dim=1,
            )  # (batch, n_features, d_token)
            cls = self.cls_token.expand(x.size(0), -1, -1)
            tokens = torch.cat([cls, tokens], dim=1)
            out = self.transformer(tokens)
            cls_out = self.norm(out[:, 0])  # use [CLS] position
            return self.head(cls_out)

    return _Net()


# ---------------------------------------------------------------------------
# Public adapter — implements RainfallModel
# ---------------------------------------------------------------------------

class HFTabularModel(RainfallModel):
    """
    RainfallModel adapter for HuggingFace / custom tabular models.

    Works as a drop-in replacement for BaselineRainfallModel in the backend
    and fusion pipeline.
    """

    def __init__(self, key: str, entry: "_ModelEntry") -> None:
        self.key = key
        self.entry = entry
        self._strategy: _TabPFNStrategy | _FTTransformerStrategy | None = None
        self._feature_medians: dict[str, float] = {}
        self._artifact_path: Path | None = None
        self.version = "unversioned"

    # ------------------------------------------------------------------
    # RainfallModel interface
    # ------------------------------------------------------------------

    def load(self, artifact_dir: Path) -> None:
        """Load a previously saved artifact from *artifact_dir*."""
        config = BaselineConfig()
        path = Path(artifact_dir) / _HF_TAB_BUNDLE_TEMPLATE.format(
            key=self.key, version=config.model_version
        )
        if not path.exists():
            raise FileNotFoundError(
                f"No HF tabular artifact at {path}. "
                f"Run `python -m ai_models.hf_models.tabular.train --model {self.key}` first."
            )
        bundle = joblib.load(path)
        strategy = _make_strategy(self.key)
        strategy.load_state(bundle["strategy_state"])
        self._strategy = strategy
        self._feature_medians = bundle.get("feature_medians", {})
        self.version = bundle.get("version", "v1")
        logger.info("Loaded HF tabular model '%s' v%s from %s", self.key, self.version, path)

    def predict(self, features: dict[str, float] | None, image: np.ndarray | None) -> ModelOutput:
        if self._strategy is None:
            raise RuntimeError("Model not loaded — call load() first")
        if features is None:
            raise ValueError(f"HF tabular model '{self.key}' requires tabular features (features dict)")
        x = self._build_feature_row(features)
        probabilities = self._strategy.predict_proba(x)[0]
        category = int(np.argmax(probabilities))
        return ModelOutput(
            probability=float(probabilities[1:].sum()),
            risk_level=_RISK_BY_CATEGORY[category],
            confidence=float(probabilities.max()),
            model_version=f"hf-tabular-{self.key}-{self.version}",
            explanation_context={
                "feature_vector": {
                    name: float(v) for name, v in zip(_FEATURE_NAMES, x[0])
                },
                "class_probabilities": {
                    _LABEL_NAMES[i]: float(p) for i, p in enumerate(probabilities)
                },
            },
        )

    def feature_names(self) -> list[str]:
        return list(_FEATURE_NAMES)

    # ------------------------------------------------------------------
    # Training / saving helpers (called by train.py)
    # ------------------------------------------------------------------

    def fit_and_save(
        self,
        x_train: np.ndarray,
        y_train: np.ndarray,
        feature_medians: dict[str, float],
        artifact_dir: Path,
        version: str = "v1",
    ) -> Path:
        """Fit the strategy on training data and persist a bundle."""
        strategy = _make_strategy(self.key)
        strategy.fit(x_train, y_train)
        self._strategy = strategy
        self._feature_medians = feature_medians
        self.version = version

        bundle = {
            "key": self.key,
            "version": version,
            "strategy_state": strategy.state(),
            "feature_names": _FEATURE_NAMES,
            "feature_medians": feature_medians,
            "label_names": _LABEL_NAMES,
            "trained_at": datetime.now(timezone.utc).isoformat(),
        }
        artifact_dir.mkdir(parents=True, exist_ok=True)
        path = artifact_dir / _HF_TAB_BUNDLE_TEMPLATE.format(key=self.key, version=version)
        joblib.dump(bundle, path)
        logger.info("Saved HF tabular bundle: %s", path)
        return path

    def predict_proba_batch(self, x: np.ndarray) -> np.ndarray:
        """Used internally by train.py for evaluation loops."""
        if self._strategy is None:
            raise RuntimeError("Model not fitted")
        return self._strategy.predict_proba(x)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_feature_row(self, features: dict[str, float]) -> np.ndarray:
        row = np.array(
            [features.get(name, self._feature_medians.get(name, 0.0)) for name in _FEATURE_NAMES],
            dtype=np.float64,
        )
        return row.reshape(1, -1)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def _make_strategy(key: str) -> _TabPFNStrategy | _FTTransformerStrategy:
    if key == "tabpfn":
        return _TabPFNStrategy()
    if key == "fttransformer":
        return _FTTransformerStrategy()
    raise ValueError(f"Unknown tabular strategy key: {key!r}")


# ---------------------------------------------------------------------------
# Smoke-test / CLI entry-point
# ---------------------------------------------------------------------------

def _smoke_test(key: str) -> None:
    """Run a quick sanity-check with synthetic data — no real dataset needed."""
    from ai_models.hf_models.registry import build_tabular_model

    print(f"\n[smoke-test] HF tabular model: {key}")
    n_train, n_test = 100, 20
    rng = np.random.default_rng(0)
    x_train = rng.normal(size=(n_train, len(_FEATURE_NAMES))).astype(np.float64)
    y_train = rng.integers(0, 3, size=n_train)
    x_test = rng.normal(size=(n_test, len(_FEATURE_NAMES))).astype(np.float64)

    model = build_tabular_model(key)
    medians = {name: float(x_train[:, i].mean()) for i, name in enumerate(_FEATURE_NAMES)}

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = model.fit_and_save(x_train, y_train, medians, Path(tmp))
        print(f"  Saved to: {path}")

        loaded = build_tabular_model(key)
        loaded.load(Path(tmp))

    proba = loaded.predict_proba_batch(x_test)
    print(f"  predict_proba shape: {proba.shape}")
    assert proba.shape == (n_test, 3), "Expected (n_test, 3)"
    assert np.allclose(proba.sum(axis=1), 1.0, atol=1e-5), "Probabilities must sum to 1"

    features_dict = {name: float(x_test[0, i]) for i, name in enumerate(_FEATURE_NAMES)}
    out = loaded.predict(features_dict, image=None)
    print(f"  ModelOutput: risk_level={out.risk_level!r}  confidence={out.confidence:.3f}")
    print("[smoke-test] PASSED ✓\n")


def main(argv: list[str] | None = None) -> int:
    from ai_models.hf_models.registry import list_models, tabular_keys

    parser = argparse.ArgumentParser(description="HuggingFace tabular model utilities")
    parser.add_argument("--list", action="store_true", help="List available tabular models")
    parser.add_argument("--smoke-test", action="store_true", dest="smoke")
    parser.add_argument(
        "--model", default="tabpfn",
        choices=tabular_keys(),
        help="Model key to smoke-test",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")

    if args.list:
        list_models(modality="tabular")
        return 0
    if args.smoke:
        _smoke_test(args.model)
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
