"""
Rainfall prediction endpoints.

POST /api/v1/predictions               — run the hybrid model (weather inputs)
POST /api/v1/predictions/explain-image — run real Grad-CAM on a satellite image
GET  /api/v1/predictions/model-info    — loaded-model metadata

The /explain-image endpoint accepts a multipart upload so the browser can
supply an INSAT satellite scene directly.  Grad-CAM is then run against
the trained satellite_model_v1.pt (CustomCNN, Captum LayerGradCam) and the
result is returned as base64 PNG data URLs — no static file server is needed.

Nothing here fabricates results: if the satellite checkpoint is missing or
the image cannot be read, the endpoint raises 422 rather than returning a
plausible-looking heatmap.
"""

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.schemas.prediction import GradCamResponse, PredictionRequest, PredictionResponse
from app.services.prediction_service import ModelNotAvailableError, get_prediction_service

router = APIRouter()

_service = get_prediction_service()


@router.post("", response_model=PredictionResponse)
def predict_rainfall(request: PredictionRequest) -> PredictionResponse:
    """Run the rainfall risk model for a location and forecast horizon.

    Returns a probability-based risk assessment with an attached
    explanation payload (SHAP feature attributions; Grad-CAM overlays when
    satellite imagery is part of the input).
    """
    try:
        return _service.predict(request)
    except ModelNotAvailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=str(exc),
        ) from exc


@router.post("/explain-image", response_model=GradCamResponse)
def explain_image(
    image: UploadFile = File(
        ...,
        description=(
            "Satellite scene image (PNG, JPEG, or TIFF). "
            "The file is passed through the trained satellite CNN "
            "(satellite_model_v1.pt) and Grad-CAM attribution is computed "
            "on the final convolutional layer (features.3 for CustomCNN). "
            "The result is real — nothing is synthesised."
        ),
    ),
) -> GradCamResponse:
    """Compute real Grad-CAM attribution for a satellite image.

    Accepts any image format readable by OpenCV/PIL.  Returns:
    - `heatmap_data_url` — pure attribution map (red = high, blue = low)
    - `overlay_data_url` — original scene blended with the heatmap
    - `regions` — named high-attention blobs extracted by connected-component analysis
    - `source: "real"` — always present to distinguish from simulated Grad-CAM

    Raises **422** if the image cannot be decoded or the checkpoint is absent.
    """
    try:
        image_bytes = image.file.read()
        filename = image.filename or "upload.png"
        return _service.explain_image(image_bytes, filename)
    except Exception as exc:
        # Surface the underlying error text so the UI can display it honestly.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Grad-CAM failed: {exc}",
        ) from exc


def _captum_available() -> bool:
    import importlib.util

    return importlib.util.find_spec("captum") is not None


@router.get("/model-performance")
def model_performance() -> dict:
    """Evaluation results exactly as recorded in ai_models/saved_models/model_info.json,
    plus warning-oriented metrics derived from the test confusion matrix (heavy-rain class)."""
    import json
    import os

    from app.services.geo_data import REPO_ROOT

    path = REPO_ROOT / "ai_models" / "saved_models" / "model_info.json"
    if not path.exists():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No evaluation report (model_info.json) found")
    info = json.loads(path.read_text(encoding="utf-8"))
    metrics = info.get("performance_metrics", {})

    def warning_metrics(block: dict) -> dict | None:
        cm = block.get("confusion_matrix")
        if not cm or len(cm) < 2:
            return None
        tn, fp = cm[0][0], cm[0][1] + (cm[0][2] if len(cm[0]) > 2 else 0)
        heavy_row = cm[1]
        tp = heavy_row[1] + (heavy_row[2] if len(heavy_row) > 2 else 0)
        fn = heavy_row[0]
        return {
            "true_positives": tp, "false_positives": fp, "false_negatives": fn, "true_negatives": tn,
            "heavy_recall": tp / (tp + fn) if tp + fn else None,          # share of heavy-rain days warned
            "heavy_precision": tp / (tp + fp) if tp + fp else None,       # share of warnings that were right
            "missed_event_rate": fn / (tp + fn) if tp + fn else None,
            "false_alarm_rate": fp / (fp + tn) if fp + tn else None,      # normal days wrongly flagged
            "heavy_days": tp + fn,
            "normal_days": tn + fp,
        }

    from app.core.config import settings as app_settings

    weather_only = (metrics.get("single_modality_test") or {}).get("weather_only") or {}
    satellite_only = (metrics.get("single_modality_test") or {}).get("satellite_only") or {}
    components = [
        {
            "name": "Weather model", "kind": "trained", "method": "Random Forest classifier (scikit-learn)",
            "artifact": "ai_models/saved_models/rainfall_model_v1.pkl",
            "runs": "Every forecast, what-if and alert, on the supplied weather and rainfall.",
            "evidence": f"Test macro-F1 {weather_only.get('f1_macro', 0):.3f} on its own." if weather_only else None,
            "loaded": _service.model_loaded,
        },
        {
            "name": "Satellite model", "kind": "trained", "method": "Convolutional neural network (PyTorch)",
            "artifact": "ai_models/saved_models/satellite_model_v1.pt",
            "runs": "Only when a satellite image is uploaded (Analysis page). Without an image, the satellite "
                    "branch is estimated from cloud cover and humidity.",
            "evidence": f"Test macro-F1 {satellite_only.get('f1_macro', 0):.3f} on its own." if satellite_only else None,
            "loaded": (_service._predictor is not None),
        },
        {
            "name": "Fusion", "kind": "tuned", "method": "Weighted average of the two branches' probabilities "
                                                          "(0.85 × weather + 0.15 × satellite)",
            "artifact": "ai_models/saved_models/varuna_fusion_model_v1.pkl",
            "runs": "Every prediction. Only the 0.85 weight was chosen, by sweeping it on validation data; "
                    "nothing else is learned.",
            "evidence": f"Test macro-F1 {metrics.get('test', {}).get('f1_macro', 0):.3f}.",
            "loaded": _service.model_loaded,
        },
        {
            "name": "SHAP explanation", "kind": "algorithmic", "method": "Shapley additive explanations of the fused probability",
            "artifact": "explainability/shap_explainer",
            "runs": "Every prediction: per-input contributions shown in explanations and alerts.",
            "evidence": None, "loaded": _service._explainer is not None,
        },
        {
            "name": "Grad-CAM", "kind": "algorithmic", "method": "Gradient-weighted class activation map (Captum) on the CNN",
            "artifact": "explainability/gradcam_explainer",
            "runs": "When a satellite image is uploaded: heatmap of the image areas that drove the CNN.",
            "evidence": None, "loaded": _captum_available(),
        },
        {
            "name": "Historical comparison", "kind": "algorithmic", "method": "Nearest-neighbour search over past high-impact region-days",
            "artifact": "stored inside the fusion bundle",
            "runs": "Every prediction: the most similar recorded days.", "evidence": None, "loaded": _service.model_loaded,
        },
        {
            "name": "Village flood risk", "kind": "rule-based", "method": "SCS runoff + terrain + drainage scoring (hand-set weights)",
            "artifact": "backend/app/services/hydrology_service.py",
            "runs": "What-if, alerts, map. Not machine-learned and not validated against observed floods.",
            "evidence": None, "loaded": True,
        },
        {
            "name": "Flood advisor chat", "kind": "llm", "method": "Claude (Anthropic API) calling the simulator tools",
            "artifact": app_settings.CHAT_MODEL,
            "runs": "Optional. Explains simulator output in plain language and never invents numbers.",
            "evidence": None, "loaded": bool(app_settings.ANTHROPIC_API_KEY or os.environ.get("ANTHROPIC_API_KEY")),
        },
    ]

    return {
        "components": components,
        "model_name": info.get("model_name"),
        "model_version": info.get("model_version"),
        "approach": info.get("approach"),
        "training_date": info.get("training_date"),
        "task": "Next-day (T+1) region rainfall category (Normal / Heavy ≥64.5 mm / Extreme ≥204.4 mm)",
        "validation": metrics.get("validation"),
        "test": metrics.get("test"),
        "single_modality_test": metrics.get("single_modality_test"),
        "warning_metrics": {
            "validation": warning_metrics(metrics.get("validation", {})),
            "test": warning_metrics(metrics.get("test", {})),
        },
        "dataset": info.get("dataset"),
        "caveats": info.get("caveats", []),
    }


@router.get("/model-info")
def model_info() -> dict:
    """Metadata about the currently loaded model (version, training window,
    feature set). Used by the dashboard's transparency panel."""
    return _service.model_info()

