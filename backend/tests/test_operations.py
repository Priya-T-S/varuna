"""Operational features: timeline, modelled river rise, recommended actions, lifecycle
audit trail, additive DB migration, honest system status / faults, model performance, demo."""

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect

from app.main import app
from app.services import actions, geo_data, hydrology_service, system_state
from app.services.hydrology_service import RainEvent
from app.services.notifications.dispatcher import AlertDispatcher, set_dispatcher
from app.services.notifications.providers import ConsoleProvider, InAppProvider

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_state():
    system_state.state.reset()
    set_dispatcher(AlertDispatcher(providers={"inapp": InAppProvider(), "console": ConsoleProvider()}, backoff_seconds=0))
    yield
    system_state.state.reset()
    set_dispatcher(None)


def _village(name):
    return geo_data.find_village(name)


# --- Hydrology: timeline + river rise -----------------------------------------
def test_timeline_rises_during_rain_and_recedes_after():
    event = RainEvent(total_mm=300, duration_days=1, antecedent="saturated")
    tl = hydrology_service.project_timeline(_village("Chengannur"), event)
    assert [p["offset_h"] for p in tl] == [0, 6, 12, 24, 48]
    probs = [p["probability"] for p in tl]
    assert probs[:4] == sorted(probs[:4])            # rising while it rains (0-24 h)
    assert probs[4] < probs[3]                        # receding after the rain stops


def test_long_spell_adds_end_of_rain_point_matching_the_full_assessment():
    event = RainEvent(total_mm=350, duration_days=3)
    v = _village("Kuttanad")
    tl = hydrology_service.project_timeline(v, event)
    assert tl[-1]["offset_h"] == 72 and tl[-1]["beyond_window"]
    assert tl[-1]["probability"] >= hydrology_service.assess(v, event).probability - 0.02


def test_good_drainage_recedes_faster_than_poor():
    event = RainEvent(total_mm=250, duration_days=1)
    poor = hydrology_service.project_timeline(_village("Kuttanad"), event)
    good = hydrology_service.project_timeline(_village("Colaba"), event)
    drop = lambda tl: tl[3]["probability"] - tl[4]["probability"]  # +24 h -> +48 h
    assert drop(good) > 0 and drop(poor) >= 0
    assert drop(good) / good[3]["probability"] > drop(poor) / poor[3]["probability"]


def test_river_rise_is_monotonic_and_boosted_by_dam_release():
    v = _village("Aluva")
    rises = [hydrology_service.river_rise_m(v, RainEvent(total_mm=p, duration_days=3)) for p in (50, 150, 300, 600)]
    assert rises == sorted(rises) and rises[-1] <= 6.0
    with_dam = hydrology_service.river_rise_m(v, RainEvent(total_mm=300, duration_days=3, dam_release=True))
    assert with_dam > rises[2]


# --- Recommended actions -----------------------------------------------------
def test_actions_scale_with_level_and_include_context():
    severe = actions.recommend("severe", actions.ActionContext(dam_release=True, dam_names=("Idukki",), landslide=True))
    texts = " | ".join(a["text"] for a in severe)
    assert "Emergency Operations Centre" in texts and "Idukki" in texts and "slopes" in texts
    assert severe[-1]["text"].endswith("30 minutes")
    assert actions.recommend("moderate")[-1]["text"].endswith("3 hours")
    assert all({"text", "priority", "owner"} <= a.keys() for a in severe)


# --- Alert content + lifecycle ------------------------------------------------
def _demo():
    r = client.post("/api/v1/demo/run", json={"scenario": "kerala_extreme"})
    assert r.status_code == 200, r.text
    return r.json()


def test_demo_alert_carries_why_timeline_actions_confidence_and_freshness():
    demo = _demo()
    assert [s["key"] for s in demo["stages"]] == ["data", "ai", "risk", "explain", "villages", "alert"]
    alert = client.get(f"/api/v1/alerts/{demo['top_alert_id']}").json()
    assert alert["data_mode"] == "demo" and alert["data_as_of"]
    assert alert["horizon_hours"] == 24 and alert["confidence_label"] in {"High", "Medium", "Low"}
    assert 3 <= len(alert["why"]) <= 6
    river = [w for w in alert["why"] if w["icon"] == "river"]
    assert river and river[0]["modelled"] and "modelled" in river[0]["text"]
    assert [p["offset_h"] for p in alert["timeline"]][:5] == [0, 6, 12, 24, 48]
    assert alert["actions"] and alert["actions"][-1]["text"].startswith("Re-evaluate")
    assert alert["model_drivers"]
    stages = [e["stage"] for e in alert["events"]]
    assert stages[:4] == ["detected", "generated", "reviewed", "sent"]
    assert "Auto-approved" in alert["events"][2]["detail"]


def test_lifecycle_actions_are_audited_with_actor():
    alert_id = _demo()["top_alert_id"]
    base = f"/api/v1/alerts/{alert_id}"
    assert client.post(f"{base}/review", json={"by": "Asha (control room)", "note": "Checked with Tahsildar"}).status_code == 200
    changed = client.post(f"{base}/severity", json={"by": "Asha (control room)", "level": "high", "reason": "Rain eased"}).json()
    assert changed["flood_level"] == "high" and changed["title"].startswith("HIGH")
    client.post(f"{base}/acknowledge", json={"by": "Collector, Alappuzha"})
    client.post(f"{base}/note", json={"by": "Asha", "text": "Shelters opened at Chengannur"})
    resolved = client.post(f"{base}/resolve", json={"by": "Asha", "note": "Water receding"}).json()
    assert resolved["status"] == "resolved" and not resolved["is_active"] and resolved["resolved_by"] == "Asha"

    events = client.get(f"{base}/events").json()
    by_stage = {e["stage"]: e for e in events}
    assert by_stage["severity_changed"]["data"] == {"from": "severe", "to": "high", "reason": "Rain eased"}
    assert by_stage["severity_changed"]["actor"] == "Asha (control room)"
    assert by_stage["acknowledged"]["actor"] == "Collector, Alappuzha"
    assert by_stage["note"]["detail"] == "Shelters opened at Chengannur"
    assert alert_id not in [a["id"] for a in client.get("/api/v1/alerts").json()]
    assert client.post("/api/v1/alerts/999999/resolve", json={"by": "x"}).status_code == 404


def test_escalation_links_previous_alert_and_records_severity_change():
    common = {"region": "Kerala", "duration_days": 3, "ignore_cooldown": True}
    first = client.post("/api/v1/alerts/evaluate", json={**common, "rain_event_mm": 200, "antecedent": "normal"}).json()
    high = [d for d in first["districts"] if d["level"] == "high" and "issued" in d["action"]]
    assert high, first
    district = high[0]["district"]
    second = client.post("/api/v1/alerts/evaluate", json={
        **common, "rain_event_mm": 600, "antecedent": "saturated", "dam_release": True, "ignore_cooldown": False,
    }).json()
    row = next(d for d in second["districts"] if d["district"] == district)
    assert row["level"] == "severe" and "issued" in row["action"]
    new_id = int(row["action"].split("#")[1].split()[0])
    new = client.get(f"/api/v1/alerts/{new_id}").json()
    old_id = new["supersedes_id"]
    assert old_id is not None
    assert any(e["stage"] == "severity_changed" and "Escalated" in e["detail"] for e in new["events"])
    assert client.get(f"/api/v1/alerts/{old_id}").json()["status"] == "resolved"


# --- Migration ----------------------------------------------------------------
def test_additive_migration_adds_new_columns_to_an_old_database(tmp_path):
    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE flood_alerts (id INTEGER PRIMARY KEY, region VARCHAR(40), district VARCHAR(80))")
    con.commit()
    con.close()

    from app.db.models import Base
    from app.db.session import _add_missing_columns

    engine = create_engine(f"sqlite:///{db.as_posix()}")
    _add_missing_columns(engine, Base)
    cols = {c["name"] for c in inspect(engine).get_columns("flood_alerts")}
    assert {"why", "timeline", "actions", "status", "data_mode", "data_as_of", "supersedes_id"} <= cols


# --- System status, faults, data sources ----------------------------------------
def test_status_is_honest_about_data_modes_and_reports_stale_feed():
    status = client.get("/api/v1/system/status").json()
    assert status["components"]["river_data"]["state"] == "simulated"
    assert status["components"]["weather_data"]["state"] == "none"

    _demo()
    status = client.get("/api/v1/system/status").json()
    assert status["components"]["weather_data"]["state"] == "demo"
    assert not [d for d in status["degradations"] if d["component"] == "weather_data"]

    client.post("/api/v1/system/faults", json={"component": "rainfall_feed", "enabled": True})
    status = client.get("/api/v1/system/status").json()
    assert status["components"]["weather_data"]["state"] == "delayed"
    assert any("47 minutes old" in d["message"] for d in status["degradations"])


def test_ai_model_fault_uses_fallback_and_is_reported():
    client.post("/api/v1/system/faults", json={"component": "ai_model", "enabled": True})
    status = client.get("/api/v1/system/status").json()
    assert status["components"]["ai_model"]["state"] == "unavailable"
    sim = client.post("/api/v1/scenarios/simulate", json={"region": "Kerala", "rainfall_change_pct": 20}).json()
    assert sim["scenario_model"] is None and any("not loaded" in c for c in sim["caveats"])


def test_data_sources_distinguish_simulated_from_historical():
    modes = {s["input"]: s["mode"] for s in client.get("/api/v1/system/data-sources").json()}
    assert modes["River levels"] == "simulated"
    assert modes["Soil moisture"] == "modelled"
    assert modes["Historical flood records"] == "historical"


def test_current_risk_snapshot_after_demo():
    _demo()
    snaps = client.get("/api/v1/system/current-risk").json()
    kerala = next(s for s in snaps if s["region"] == "Kerala")
    assert kerala["data_mode"] == "demo" and len(kerala["villages"]) == len(geo_data.villages_in("Kerala"))


# --- Model performance ---------------------------------------------------------
def test_model_performance_matches_the_recorded_evaluation():
    body = client.get("/api/v1/predictions/model-performance").json()
    info = json.loads((geo_data.REPO_ROOT / "ai_models/saved_models/model_info.json").read_text(encoding="utf-8"))
    assert body["test"]["f1_macro"] == info["performance_metrics"]["test"]["f1_macro"]
    cm = info["performance_metrics"]["test"]["confusion_matrix"]
    wm = body["warning_metrics"]["test"]
    assert wm["heavy_recall"] == pytest.approx(cm[1][1] / (cm[1][0] + cm[1][1]))
    assert wm["false_alarm_rate"] == pytest.approx(cm[0][1] / (cm[0][0] + cm[0][1]))
    assert body["caveats"] == info["caveats"]


def test_provenance_is_honest_about_what_ran():
    alert = client.get(f"/api/v1/alerts/{_demo()['top_alert_id']}").json()
    prov = {p["component"]: p for p in alert["provenance"]}
    assert prov["Weather model"]["status"] == "ran" and prov["Weather model"]["kind"] == "trained"
    assert prov["Satellite model (CNN)"]["status"] == "estimated"          # no image in alerts
    assert prov["Fusion"]["kind"] == "tuned"                               # weighted average, not a learned model
    assert prov["Village flood risk"]["kind"] == "rule-based"

    client.post("/api/v1/system/faults", json={"component": "ai_model", "enabled": True})
    sim = client.post("/api/v1/scenarios/simulate", json={"region": "Kerala"}).json()
    prov = {p["component"]: p for p in sim["provenance"]}
    assert prov["Weather model"]["status"] == "not_run"


def test_model_page_components_describe_each_part_accurately():
    comps = {c["name"]: c for c in client.get("/api/v1/predictions/model-performance").json()["components"]}
    assert comps["Weather model"]["kind"] == "trained" and "Random Forest" in comps["Weather model"]["method"]
    assert comps["Satellite model"]["kind"] == "trained" and "image" in comps["Satellite model"]["runs"]
    assert comps["Fusion"]["kind"] == "tuned" and "0.85" in comps["Fusion"]["method"]
    assert comps["Village flood risk"]["kind"] == "rule-based"
    assert comps["Grad-CAM"]["loaded"] is True                              # captum installed


def test_status_declares_prototype_mode():
    status = client.get("/api/v1/system/status").json()
    assert status["prototype_mode"] is True and "operator-provided" in status["prototype_notice"]


def test_scenario_result_has_timeline_and_actions():
    sim = client.post("/api/v1/scenarios/simulate", json={"region": "Kerala", "rainfall_change_pct": 40,
                                                          "antecedent": "saturated", "dam_release": True}).json()
    assert [p["offset_h"] for p in sim["timeline"]][:5] == [0, 6, 12, 24, 48]
    assert sim["actions"] and any("dam authority" in a["text"] for a in sim["actions"])
    assert all(v["timeline"] and v["river_rise_m"] >= 0 for v in sim["villages"])
    assert sim["scenario_model"]["confidence_label"] in {"High", "Medium", "Low"}
