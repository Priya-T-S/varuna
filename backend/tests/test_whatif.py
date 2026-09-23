"""What-if simulator: hydrology physics, scenario engine, incidents, API."""

from fastapi.testclient import TestClient

from app.main import app
from app.services import geo_data, hydrology_service, incident_service
from app.services.hydrology_service import RainEvent

client = TestClient(app)


def _village(name: str) -> dict:
    village = geo_data.find_village(name)
    assert village is not None, name
    return village


# --- Hydrology ---------------------------------------------------------------
def test_scs_runoff_is_zero_below_initial_abstraction_and_monotonic():
    cn = 80.0
    assert hydrology_service.scs_runoff(5.0, cn) == 0.0
    depths = [hydrology_service.scs_runoff(p, cn) for p in (50, 100, 200, 400, 800)]
    assert depths == sorted(depths) and depths[-1] < 800


def test_saturated_soil_raises_curve_number():
    v = _village("Kuttanad")
    assert (
        hydrology_service.curve_number(v, "dry")
        < hydrology_service.curve_number(v, "normal")
        < hydrology_service.curve_number(v, "saturated")
    )


def test_flood_probability_increases_with_rainfall():
    v = _village("Chengannur")
    probs = [hydrology_service.assess(v, RainEvent(total_mm=p, duration_days=3)).probability for p in (50, 150, 300, 600)]
    assert probs == sorted(probs)


def test_low_lying_riverside_village_ranks_above_hill_town():
    event = RainEvent(total_mm=250, duration_days=3)
    low = hydrology_service.assess(_village("Kuttanad"), event)
    hill = hydrology_service.assess(_village("Munnar"), event)
    assert low.probability > hill.probability
    assert low.band in {"high", "severe"}
    assert hill.landslide_risk and not low.landslide_risk


def test_dam_release_only_affects_downstream_villages():
    base = RainEvent(total_mm=200, duration_days=3)
    dam = RainEvent(total_mm=200, duration_days=3, dam_release=True)
    downstream = _village("Aluva")            # below Idamalayar / Idukki
    not_downstream = _village("Thiruvalla")
    assert hydrology_service.assess(downstream, dam).probability > hydrology_service.assess(downstream, base).probability
    assert hydrology_service.assess(not_downstream, dam).probability == hydrology_service.assess(not_downstream, base).probability


def test_factor_contributions_explain_the_log_odds():
    a = hydrology_service.assess(_village("Velachery"), RainEvent(total_mm=300, duration_days=2))
    import math
    z = hydrology_service.INTERCEPT + sum(f.contribution for f in a.factors)
    assert abs(1 / (1 + math.exp(-z)) - a.probability) < 0.01
    assert a.reasons, "high-risk villages must carry human-readable reasons"


# --- Incidents ---------------------------------------------------------------
def test_incident_matching_prefers_same_region_and_causes():
    matches = incident_service.find_similar(
        "Kerala", 330, 3, causes={"extreme_rainfall", "saturated_soil", "dam_release"},
        villages=["Chengannur", "Aluva"],
    )
    assert matches[0].id == "KL-2018-08"
    assert any("dam release" in w for w in matches[0].why_similar)


def test_incident_search_filters():
    results = incident_service.search(region="Chennai", cause="dam_release")
    assert results and all(r["region"] == "Chennai" and "dam_release" in r["causes"] for r in results)


# --- Scenario API ----------------------------------------------------------------
def test_simulate_plus_20_percent_kerala():
    response = client.post("/api/v1/scenarios/simulate", json={"region": "Kerala", "rainfall_change_pct": 20})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["scenario_rain"]["event_total_mm"] > body["baseline_rain"]["event_total_mm"]
    villages = body["villages"]
    assert len(villages) == len(geo_data.villages_in("Kerala"))
    # physics: more rain never lowers a village's flood probability
    assert all(v["flood_probability"] >= v["baseline_probability"] for v in villages)
    assert villages == sorted(villages, key=lambda v: -v["flood_probability"])
    assert body["similar_incidents"] and body["similar_incidents"][0]["region"] == "Kerala"
    assert body["summary"]["headline"]
    assert body["baseline_model"] is not None and body["driver_changes"], "fusion model + SHAP delta expected"


def test_simulate_absolute_rainfall_with_tide_matches_2005_deluge():
    response = client.post(
        "/api/v1/scenarios/simulate",
        json={"region": "Mumbai", "rainfall_mm": 900, "duration_days": 1, "high_tide": True},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["similar_incidents"][0]["id"] == "MH-2005-07"
    assert body["summary"]["villages_high_or_severe"] >= 5


def test_simulate_district_name_resolves_region():
    response = client.post("/api/v1/scenarios/simulate", json={"region": "Alappuzha", "district": "Alappuzha"})
    assert response.status_code == 200
    body = response.json()
    assert body["region"] == "Kerala"
    assert {v["district"] for v in body["villages"]} == {"Alappuzha"}


def test_simulate_unknown_region_is_404():
    response = client.post("/api/v1/scenarios/simulate", json={"region": "Atlantis"})
    assert response.status_code == 404


def test_geo_endpoints():
    assert len(client.get("/api/v1/geo/regions").json()) == 4
    assert client.get("/api/v1/geo/villages", params={"region": "Assam"}).json()
    assert client.get("/api/v1/geo/incidents", params={"region": "Mumbai"}).json()
