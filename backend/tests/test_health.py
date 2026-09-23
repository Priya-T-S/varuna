"""Smoke tests for the API — verify the app boots, the contract holds, and
the real hybrid model is deployed and producing predictions."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "VARUNA AI"


def test_model_info_reports_model_loaded():
    """model-info must report model_loaded=True now that the hybrid model is deployed."""
    response = client.get("/api/v1/predictions/model-info")
    assert response.status_code == 200
    body = response.json()
    assert body["model_loaded"] is True, (
        "The hybrid model should be loaded. "
        "Check startup logs for loading errors."
    )
    assert "loaded_model" in body
    assert body["loaded_model"]["version"] == "v1"


def test_prediction_returns_200_with_real_model():
    """The hybrid model should return a real prediction (not 501) with weather inputs."""
    response = client.post(
        "/api/v1/predictions",
        json={
            "location": {"latitude": 10.0, "longitude": 76.3},
            "region_name": "Kerala",
            "horizon_hours": 24,
            "weather": {
                "temperature_c": 29.4,
                "humidity_pct": 91.0,
                "pressure_hpa": 1002.0,
                "wind_speed_ms": 7.1,
                "cloud_cover_pct": 96.0,
            },
            "include_explanation": True,
        },
    )
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    body = response.json()
    assert "probability" in body
    assert 0.0 <= body["probability"] <= 1.0
    assert body["risk_level"] in {"low", "moderate", "heavy", "extreme"}
    assert 0.0 <= body["confidence"] <= 1.0
    assert "v1" in body["model_version"]
    # Explanation must be present with real SHAP attributions
    assert body["explanation"] is not None
"""Smoke tests for the API — verify the app boots, the contract holds, and
the real hybrid model is deployed and producing predictions."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "VARUNA AI"


def test_model_info_reports_model_loaded():
    """model-info must report model_loaded=True now that the hybrid model is deployed."""
    response = client.get("/api/v1/predictions/model-info")
    assert response.status_code == 200
    body = response.json()
    assert body["model_loaded"] is True, (
        "The hybrid model should be loaded. "
        "Check startup logs for loading errors."
    )
    assert "loaded_model" in body
    assert body["loaded_model"]["version"] == "v1"


def test_prediction_returns_200_with_real_model():
    """The hybrid model should return a real prediction (not 501) with weather inputs."""
    response = client.post(
        "/api/v1/predictions",
        json={
            "location": {"latitude": 10.0, "longitude": 76.3},
            "region_name": "Kerala",
            "horizon_hours": 24,
            "weather": {
                "temperature_c": 29.4,
                "humidity_pct": 91.0,
                "pressure_hpa": 1002.0,
                "wind_speed_ms": 7.1,
                "cloud_cover_pct": 96.0,
            },
            "include_explanation": True,
        },
    )
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    body = response.json()
    assert "probability" in body
    assert 0.0 <= body["probability"] <= 1.0
    assert body["risk_level"] in {"low", "moderate", "heavy", "extreme"}
    assert 0.0 <= body["confidence"] <= 1.0
    assert "v1" in body["model_version"]
    # Explanation must be present with real SHAP attributions
    assert body["explanation"] is not None
    assert len(body["explanation"]["feature_attributions"]) > 0
    assert body["explanation"]["historical_explanation"] is not None
    assert body["explanation"]["confidence_explanation"] is not None
    assert len(body["explanation"]["caveats"]) > 0


def test_alerts_list_returns_active_alerts():
    response = client.get("/api/v1/alerts")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert all(alert["is_active"] for alert in response.json())


def test_prediction_with_image():
    """Verify that predictions accept base64-encoded satellite images and return a real image_explanation."""
    import cv2
    import numpy as np
    import base64

    # Generate 256x256 mock image
    image = np.random.randint(20, 70, size=(256, 256, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".png", image)
    assert ok
    image_bytes = buf.tobytes()
    b64_string = base64.b64encode(image_bytes).decode("ascii")
    b64_data_url = f"data:image/png;base64,{b64_string}"

    response = client.post(
        "/api/v1/predictions",
        json={
            "location": {"latitude": 10.0, "longitude": 76.3},
            "region_name": "Kerala",
            "horizon_hours": 24,
            "weather": {
                "temperature_c": 29.4,
                "humidity_pct": 91.0,
                "pressure_hpa": 1002.0,
                "wind_speed_ms": 7.1,
                "cloud_cover_pct": 96.0,
            },
            "include_explanation": True,
            "satellite_image_b64": b64_data_url,
        },
    )
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    body = response.json()
    assert body["explanation"] is not None
    assert body["explanation"]["image_explanation"] is not None
    assert body["explanation"]["image_explanation"]["satellite_image_id"] == "uploaded_scene.png"
    assert body["explanation"]["image_explanation"]["heatmap_url"].startswith("data:image/png;base64,")
    assert "Real Grad-CAM overlay" in body["explanation"]["image_explanation"]["description"]
    prov = {p["component"]: p for p in body["explanation"]["provenance"]}
    assert prov["Satellite model (CNN)"]["status"] == "ran"   # the CNN really ran on the uploaded image


def test_explain_image_endpoint():
    """Verify explain-image multipart endpoint works on a mock scene."""
    import cv2
    import numpy as np

    # Generate 256x256 mock image
    image = np.random.randint(20, 70, size=(256, 256, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".png", image)
    assert ok
    image_bytes = buf.tobytes()

    response = client.post(
        "/api/v1/predictions/explain-image",
        files={"image": ("test.png", image_bytes, "image/png")}
    )
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    body = response.json()
    assert body["source"] == "real"
    assert body["heatmap_data_url"].startswith("data:image/png;base64,")
    assert body["overlay_data_url"].startswith("data:image/png;base64,")


def test_prediction_without_cloud_cover_uses_typical_satellite_score():
    """Location-only / humidity-only requests used to 500 (no satellite signal)."""
    for body in ({"location": {"latitude": 10.0, "longitude": 76.3}},
                 {"location": {"latitude": 19.07, "longitude": 72.88}, "weather": {"humidity_pct": 90}}):
        response = client.post("/api/v1/predictions", json=body)
        assert response.status_code == 200, response.text
        provenance = response.json()["explanation"]["provenance"]
        satellite = next(p for p in provenance if p["component"].startswith("Satellite"))
        assert "typical (training-median) value" in satellite["detail"]
