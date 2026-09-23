"""
HuggingFace tabular model training & evaluation pipeline.

    load dataset (same parquet as Phase 3 baseline)
    → engineer features (same logic as baseline/data.py)
    → chronological split
    → fit HF model (TabPFN: zero-shot in seconds, FTTransformer: ~5-15 min)
    → evaluate on validation + test
    → save bundle + report

Run (from repo root, using backend venv):
    backend/.venv/bin/python -m ai_models.hf_models.tabular.train --model tabpfn
    backend/.venv/bin/python -m ai_models.hf_models.tabular.train --model fttransformer
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

from ai_models.baseline import data as data_prep
from ai_models.baseline.config import BaselineConfig
from ai_models.baseline.evaluate import evaluate_model
from ai_models.hf_models.registry import build_tabular_model, list_models, tabular_keys
from ai_models.hf_models.tabular.hf_tabular import _FEATURE_NAMES, HFTabularModel

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Evaluation helpers (model-agnostic — works with predict_proba_batch)
# ---------------------------------------------------------------------------

def evaluate_hf_tabular(
    model: HFTabularModel,
    x: np.ndarray,
    y: np.ndarray,
    num_classes: int = 3,
) -> dict[str, Any]:
    """Compute metrics from the HF tabular adapter."""
    from sklearn.metrics import (
        accuracy_score,
        classification_report,
        confusion_matrix,
        f1_score,
        precision_score,
        recall_score,
    )

    probabilities = model.predict_proba_batch(x)
    predictions = probabilities.argmax(axis=1)

    labels = list(range(num_classes))
    report = classification_report(y, predictions, labels=labels, output_dict=True, zero_division=0)

    return {
        "accuracy": float(accuracy_score(y, predictions)),
        "precision_macro": float(precision_score(y, predictions, average="macro", zero_division=0)),
        "recall_macro": float(recall_score(y, predictions, average="macro", zero_division=0)),
        "f1_macro": float(f1_score(y, predictions, average="macro", zero_division=0)),
        "per_class": {
            str(c): {
                "precision": float(report[str(c)]["precision"]),
                "recall": float(report[str(c)]["recall"]),
                "f1": float(report[str(c)]["f1-score"]),
                "support": int(report[str(c)]["support"]),
            }
            for c in labels
            if str(c) in report
        },
        "confusion_matrix": confusion_matrix(y, predictions, labels=labels).tolist(),
    }


def render_report(
    key: str,
    val_metrics: dict[str, Any],
    test_metrics: dict[str, Any],
    dataset_info: dict[str, Any],
    needs_training: bool,
) -> str:
    lines = [
        "=" * 70,
        f"  VARUNA AI — HuggingFace Tabular Model Report",
        f"  Model: {key}",
        f"  Date:  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "=" * 70,
        "",
        f"Training required: {'Yes' if needs_training else 'No (zero-shot)'}",
        f"Dataset rows: {dataset_info.get('records', '?')}  |  "
        f"Train: {dataset_info.get('splits', {}).get('train', '?')}  "
        f"Val: {dataset_info.get('splits', {}).get('val', '?')}  "
        f"Test: {dataset_info.get('splits', {}).get('test', '?')}",
        "",
        "── Validation ─────────────────────────────────────────────────",
        f"  Accuracy:         {val_metrics['accuracy']:.4f}",
        f"  Macro Precision:  {val_metrics['precision_macro']:.4f}",
        f"  Macro Recall:     {val_metrics['recall_macro']:.4f}",
        f"  Macro F1:         {val_metrics['f1_macro']:.4f}",
        "",
        "── Test (held-out) ─────────────────────────────────────────────",
        f"  Accuracy:         {test_metrics['accuracy']:.4f}",
        f"  Macro Precision:  {test_metrics['precision_macro']:.4f}",
        f"  Macro Recall:     {test_metrics['recall_macro']:.4f}",
        f"  Macro F1:         {test_metrics['f1_macro']:.4f}",
        "",
        "── Per-class Test ──────────────────────────────────────────────",
    ]
    class_names = {0: "Normal", 1: "Heavy", 2: "Extreme"}
    for c, name in class_names.items():
        cls = test_metrics.get("per_class", {}).get(str(c), {})
        lines.append(
            f"  {name:<10}  P={cls.get('precision', 0):.3f}  "
            f"R={cls.get('recall', 0):.3f}  F1={cls.get('f1', 0):.3f}  "
            f"n={cls.get('support', 0)}"
        )
    lines += [
        "",
        "── vs. Existing Baseline (weighted_fusion_w0.85) ───────────────",
        "  Baseline test macro-F1:  0.6878",
        f"  This model test macro-F1: {test_metrics['f1_macro']:.4f}",
        f"  Delta: {(test_metrics['f1_macro'] - 0.6878):+.4f}",
        "",
        "=" * 70,
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

# TabPFN's recommended maximum training size. Inference cost scales as
# O(n_train × n_test) so beyond ~10K rows it becomes impractically slow.
_TABPFN_MAX_TRAIN_ROWS = 8_000
_TABPFN_MAX_EVAL_ROWS  = 2_000


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Train / evaluate a HuggingFace tabular model for rainfall prediction"
    )
    parser.add_argument(
        "--model",
        default="tabpfn",
        choices=tabular_keys(),
        help="HuggingFace tabular model to train/evaluate (default: tabpfn)",
    )
    parser.add_argument("--list", action="store_true", help="List available models and exit")
    parser.add_argument(
        "--version", default="v1", help="Artifact version tag (default: v1)"
    )
    parser.add_argument(
        "--tabpfn-max-rows", type=int, default=_TABPFN_MAX_TRAIN_ROWS, dest="tabpfn_max_rows",
        help=f"Max training rows for TabPFN (default: {_TABPFN_MAX_TRAIN_ROWS}). "
             "Higher = slower inference. TabPFN sweet spot is <10K.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )

    if args.list:
        list_models(modality="tabular")
        return 0

    config = BaselineConfig()
    config.ensure_output_dirs()

    # ── Load and engineer features (reuse Phase 3 pipeline) ──────────────
    logger.info("Loading dataset from %s …", config.dataset_path)
    dataset = data_prep.load_dataset(config)
    frame = data_prep.build_supervised_frame(dataset, config)
    splits = data_prep.time_based_split(frame, config)

    feature_cols = [f for f in _FEATURE_NAMES if f in splits.x_train.columns]
    missing = [f for f in _FEATURE_NAMES if f not in splits.x_train.columns]
    if missing:
        logger.warning("Features not found in dataset (will be filled with 0): %s", missing)

    def _to_array(df: "Any") -> np.ndarray:
        rows = df.reindex(columns=feature_cols, fill_value=0.0)
        return rows.to_numpy(dtype=np.float64)

    x_train = _to_array(splits.x_train)
    y_train = splits.y_train.to_numpy()
    x_val = _to_array(splits.x_val)
    y_val = splits.y_val.to_numpy()
    x_test = _to_array(splits.x_test)
    y_test = splits.y_test.to_numpy()

    feature_medians = {
        name: float(splits.x_train[name].median()) if name in splits.x_train.columns else 0.0
        for name in _FEATURE_NAMES
    }

    # TabPFN: cap training rows to keep inference tractable.
    # Strategy: take the most recent rows (end of time series) so temporal
    # proximity to the val/test period gives the best signal.
    if args.model == "tabpfn" and len(x_train) > args.tabpfn_max_rows:
        logger.info(
            "TabPFN: capping train rows %d → %d (most recent, chronological tail). "
            "Use --tabpfn-max-rows to change.",
            len(x_train), args.tabpfn_max_rows,
        )
        x_train = x_train[-args.tabpfn_max_rows:]
        y_train = y_train[-args.tabpfn_max_rows:]

    # TabPFN: cap eval rows too — inference is O(n_train × n_eval).
    x_val_eval, y_val_eval = x_val, y_val
    x_test_eval, y_test_eval = x_test, y_test
    if args.model == "tabpfn":
        if len(x_val) > _TABPFN_MAX_EVAL_ROWS:
            x_val_eval  = x_val[-_TABPFN_MAX_EVAL_ROWS:]
            y_val_eval  = y_val[-_TABPFN_MAX_EVAL_ROWS:]
            logger.info("TabPFN: capping val eval rows %d → %d", len(x_val), _TABPFN_MAX_EVAL_ROWS)
        if len(x_test) > _TABPFN_MAX_EVAL_ROWS:
            x_test_eval = x_test[-_TABPFN_MAX_EVAL_ROWS:]
            y_test_eval = y_test[-_TABPFN_MAX_EVAL_ROWS:]
            logger.info("TabPFN: capping test eval rows %d → %d", len(x_test), _TABPFN_MAX_EVAL_ROWS)

    logger.info(
        "Data ready — train: %d  val: %d  test: %d", len(x_train), len(x_val), len(x_test)
    )

    # ── Fit ──────────────────────────────────────────────────────────────
    model = build_tabular_model(args.model)
    logger.info("Fitting model: %s …", args.model)
    artifact_path = model.fit_and_save(
        x_train, y_train, feature_medians, config.saved_models_dir, version=args.version
    )

    # ── Evaluate ─────────────────────────────────────────────────────────
    logger.info("Evaluating on validation set …")
    val_metrics = evaluate_hf_tabular(model, x_val_eval, y_val_eval)
    logger.info(
        "Validation — macro-F1: %.4f  macro-Recall: %.4f",
        val_metrics["f1_macro"],
        val_metrics["recall_macro"],
    )

    logger.info("Evaluating on test set …")
    test_metrics = evaluate_hf_tabular(model, x_test_eval, y_test_eval)
    logger.info(
        "Test — macro-F1: %.4f  macro-Recall: %.4f  accuracy: %.4f",
        test_metrics["f1_macro"],
        test_metrics["recall_macro"],
        test_metrics["accuracy"],
    )

    # ── Report ───────────────────────────────────────────────────────────
    entry = model.entry
    dataset_info = {
        "records": len(frame),
        "splits": {
            "train": len(x_train),
            "val": len(x_val),
            "test": len(x_test),
        },
        "class_counts": {str(k): int(v) for k, v in
                         zip(*np.unique(y_train, return_counts=True))},
    }
    report_text = render_report(
        args.model, val_metrics, test_metrics, dataset_info, entry.needs_training
    )

    report_path = config.reports_dir / f"hf_tabular_{args.model}_report_{args.version}.txt"
    report_path.write_text(report_text + "\n", encoding="utf-8")

    experiment_path = (
        config.experiments_dir
        / f"hf_tabular_{args.model}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    )
    experiment_path.write_text(
        json.dumps(
            {
                "model": args.model,
                "hf_id": entry.hf_id,
                "needs_training": entry.needs_training,
                "version": args.version,
                "date": datetime.now(timezone.utc).isoformat(),
                "validation": val_metrics,
                "test": test_metrics,
                "dataset": dataset_info,
                "artifact": str(artifact_path),
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    print(report_text)
    print(f"\nBundle:     {artifact_path}")
    print(f"Report:     {report_path}")
    print(f"Experiment: {experiment_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
