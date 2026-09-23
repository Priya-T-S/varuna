# VARUNA AI

**An Explainable AI-Based Extreme Rainfall Intelligence & Early Warning
System Using Satellite Data**

Built for Smart India Hackathon — problem statement **SIH260006 (ISRO)**:
*"Explainable AI model to predict high-impact rain events using satellite data."*

---

## Problem

High-impact rainfall events (cloudbursts, extreme monsoon spells) cause
floods, landslides, and loss of life across India. Existing forecasts are
either too coarse or act as black boxes — disaster management authorities
receive a number without the reasoning behind it, which undermines trust
and slows response.

## Solution

VARUNA AI is a disaster intelligence platform that:

1. **Uses** NASA POWER weather series and NASA GIBS MODIS satellite scenes
   (training data); INSAT scenes can be uploaded for on-demand analysis.
2. **Predicts** the probability of a high-impact rain event per region for the
   **next 24 hours**, classified low → extreme with a confidence score.
3. **Explains every prediction** — SHAP feature attributions, Grad-CAM heatmaps
   showing *which cloud structures* in the satellite image drove it, and a
   plain-language narrative.
4. **Translates rainfall into impact** — village-level flood risk with a
   Now → +48 h projection, built on terrain, runoff and drainage.
5. **Warns** — threshold alerts to district collectors with recommended actions,
   delivery and lifecycle audit trail, on an interactive map.

Explainability is the core differentiator: the platform answers not just
*"will it rain heavily?"* but *"why does the AI believe that?"*.

## Features

- AI rainfall prediction engine (probability + risk class + confidence)
- Satellite image intelligence (cloud density, formation, movement)
- Explainable AI layer (SHAP + Grad-CAM + narrative)
- Interactive disaster monitoring dashboard (India map, risk zones,
  satellite visualisation, explanation panels, historical analysis)
- Early-warning alert generation with audit trail
- **What-if flood advisor**: describe a situation ("rain +20% in Kerala,
  rivers already full") and a Claude-powered assistant simulates it. It reports
  which villages flood and why (runoff, terrain, drainage, dam and tide factors,
  plus SHAP), and lists similar past disasters.
- **Threshold alerting**: alerts are automatically generated when the evaluated district
  risk crosses the configured threshold. Collectors are notified by Telegram, e-mail,
  SMS and WhatsApp (once provider keys are set), with cooldown, escalation, a delivery
  and lifecycle audit trail, one-tap acknowledgement and instant dashboard updates.
  See [docs/whatif_and_alerting.md](docs/whatif_and_alerting.md).

> **Prototype / simulation mode.** No live rain-gauge, IMD or river-gauge feed is
> connected. Weather and river inputs are operator-provided, simulated or estimated;
> AI inference and risk analysis run on the supplied conditions. VARUNA AI
> demonstrates the decision pipeline, not yet an operational real-time deployment.

### How the AI fits together (hybrid decision support)

```
   WEATHER MODEL (trained)            SATELLITE MODEL (trained)
   Random Forest                      CNN / PyTorch
        │                             image uploaded? ── yes → real CNN
        │                                             └─ no  → estimated from cloud & humidity
        └──────────────┬──────────────┘
                       ▼
        FUSION (0.85 × weather + 0.15 × satellite; one weight tuned on validation)
                       ▼
        Heavy-rain probability (next 24 h) ─► SHAP explanation ─► historical comparison
                       ▼
        RULE-BASED VILLAGE FLOOD RISK (SCS runoff + terrain + drainage; not ML)
                       ▼
        64 villages · 48 h timeline · alerts · notifications
```

Every prediction and alert records which of these components actually ran
("How this was computed" in the UI).

## Technology stack

| Layer | Technology |
|---|---|
| Backend API | Python, FastAPI, Pydantic |
| ML | PyTorch (vision), scikit-learn (tabular), pandas, NumPy, OpenCV |
| Explainability | SHAP, Grad-CAM |
| Database | PostgreSQL + PostGIS |
| Frontend | React, Tailwind CSS, Leaflet |
| Deployment | Docker, docker-compose |

## Architecture

```
data sources → satellite_processing → data/ + PostGIS
                                        ↓
                   ai_models (tabular · vision · hybrid)
                                        ↓
                   explainability (SHAP · Grad-CAM · narrative)
                                        ↓
                   backend (FastAPI REST API)
                                        ↓
                   frontend (React dashboard)
```

Strict boundaries: AI packages never import application code; the backend
consumes models only through the `RainfallModel` interface
([ai_models/base.py](ai_models/base.py)). Full details in
[docs/system_architecture.md](docs/system_architecture.md).

## Repository layout

```
VARUNA-AI/
├── backend/               FastAPI application (api / core / schemas / services / db)
├── frontend/              React + Tailwind + Leaflet dashboard
├── ai_models/             ML models: tabular, vision, hybrid (+ base interfaces)
├── explainability/        SHAP, Grad-CAM, narrative generation
├── satellite_processing/  Data acquisition (MOSDAC, NASA) & preprocessing
├── data/                  raw / processed / external datasets (git-ignored)
├── database/              PostGIS schema + migrations
├── notebooks/             EDA and model experiments
├── docs/                  Requirements, architecture, data spec, roadmap
└── deployment/            docker-compose orchestration
```

## Getting started

**Full stack (Docker):**

```bash
cp .env.example .env
docker compose -f deployment/docker-compose.yml up --build
# API:       http://localhost:8000/docs
# Dashboard: http://localhost:3000
```

**Backend only (local dev):**

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload   # http://localhost:8000/docs
pytest                          # run the test suite
```

**Frontend only (local dev):**

```bash
cd frontend
npm install
npm run dev                     # http://localhost:5173
```

> **Honest-by-design:** the platform never fabricates predictions or alerts.
> Every result records which component produced it ("How this was computed":
> trained model / weighted average / explanation algorithm / rule-based, and
> whether it ran or was estimated), and the dashboard shows real system status.
> If the trained models are absent, prediction endpoints return HTTP 501 and any
> fallback output is labelled as simulated.

**Optional keys** (both degrade gracefully when unset): `ANTHROPIC_API_KEY`
for the what-if chat assistant (without it the chat uses a free offline,
rule-based assistant built on the same simulator), and Telegram / SMTP / Twilio credentials for
outbound alerts. Without them the simulator still runs and alerts still reach
the dashboard and the server log. See [.env.example](.env.example).

## Project phases

Phases 1–7 are complete: architecture, data pipeline, baseline tabular model,
satellite vision model, the hybrid fusion engine, the explainability layer, and
the backend API with the React dashboard — including village-level flood impact,
threshold alerting with an audit trail, and the what-if simulator. What remains
is the live input layer (rain-gauge / IMD / river-gauge ingestion) and an
operational deployment. The full ten-phase plan is in
[docs/development_roadmap.md](docs/development_roadmap.md).

| Phase | Deliverable | Trained artifact |
|---|---|---|
| 3 | Tabular model — next-day category from weather | `rainfall_model_v1.pkl` (test macro-F1 0.634) |
| 4 | Satellite CNN — same-day category from a MODIS scene | `satellite_model_v1.pt` (test macro-F1 0.860) |
| 5 | Hybrid fusion — next-day risk from both branches | `varuna_fusion_model_v1.pkl` (see report) |
| 6 | Explainability — SHAP, Grad-CAM, narrative | no artifact; explains 3–5 on demand |

Model artifacts are git-ignored; regenerate them with
`python -m ai_models.<package>.train`, or distribute via releases/DVC.
Every run writes a report to [reports/](reports/) whose CAVEATS block
names what the numbers do not show — currently that Extreme rainfall is
unmeasurable on this data, and that fusion has not yet beaten the weather
branch alone on held-out days.
