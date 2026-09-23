# VARUNA AI — Presentation Content (SIH260006/ISRO)

---

## Proposed Solution (Idea/Solution/Prototype)

**VARUNA AI** is an explainable AI-based extreme rainfall intelligence and early warning system using satellite data. The system ingests ISRO INSAT satellite imagery (via MOSDAC) and NASA Earth observation data, combined with meteorological time series, to predict high-impact rain events (1–72 hour lead time) classified from Low → Extreme with confidence scores. Every prediction includes explainability via SHAP (weather drivers), Grad-CAM (satellite cloud structures), and plain-language narrative generation. The platform generates human-readable early-warning alerts displayed on an interactive India risk map.

---

## Detailed Explanation of the Proposed Solution

VARUNA AI operates on a 6-layer architecture:

1. **Data Ingestion Layer** – Collects INSAT satellite imagery (MOSDAC) and NASA POWER/GIBS meteorological data
2. **Preprocessing & Feature Engineering** – Cleans/resamples 70,128 weather records + 4,999 labelled satellite scene-days (24 years, 4 regions: Mumbai, Kerala, Assam, Chennai)
3. **AI Prediction Engine** – Hybrid fusion of tabular (Random Forest, TabPFN, FT-Transformer) and vision models (custom CNN, Swin-Tiny, ViT); weighted fusion (w=0.85)
4. **Explainability Layer** – Exact TreeSHAP for weather feature attribution, Captum Grad-CAM for satellite heatmaps, historical analogue matching, narrative generation
5. **Risk Classification** – Probability + risk class + confidence score per region
6. **Application Layer** – React dashboard with India map, risk zones, satellite visualization, explanation panels, historical analysis, and early-warning alerts with audit trail

---

## How It Addresses the Problem

**Problem:** High-impact rainfall events (cloudbursts, extreme monsoon spells) cause floods/landslides/loss of life. Existing forecasts are either too coarse or act as black boxes—disaster management authorities receive numbers without reasoning, undermining trust and slowing response.

**Solution:** VARUNA AI provides not just "what may happen" but "why it may happen." The system delivers:
- Rainfall-risk forecast (1–72h) with Low/Medium/Heavy/Extreme classification
- Confidence score for every prediction
- SHAP-based weather driver explanations (humidity, pressure, wind speed, temperature)
- Grad-CAM heatmaps showing which cloud structures drove the prediction
- Historical similarity comparison with past events
- Plain-language narrative generator

This transforms alerts from opaque warnings into evidence-based decisions.

---

## Innovation and Uniqueness

| Aspect | VARUNA AI | Typical Systems |
|---|---|---|
| **Explainability** | Exact TreeSHAP + Grad-CAM + historical analogue + narrative on every prediction | Black-box models with no explanation |
| **Data Architecture** | 24-year archive (69,888 weather records + 4,999 satellite scene-days) with IMD-aligned labels | Real-time only, no historical depth |
| **Fusion Approach** | Weather + satellite hybrid with chronological validation | Single-modality models |
| **Honesty Protocol** | HTTP 501 when models undeployed; CAVEATS block on every report | Fabricated predictions |
| **Deployment** | ~30 MB model path, laptop-trained, no GPU cluster needed | Requires GPU clusters |
| **Differentiation** | Closes "time-to-decision" loop; ground-segment clubs close "time-to-data" loop | Focuses on one half |

**Key differentiator:** Explains every prediction—not as a feature, but as the core product. A 20-minute-old black-box score still gets second-guessed; VARUNA AI's explanations enable immediate action.

---

## Technologies to Be Used

| Layer | Technology |
|---|---|
| **Backend API** | Python, FastAPI, Pydantic |
| **ML / DL** | PyTorch (vision), scikit-learn, TabPFN, FT-Transformer, XGBoost, Random Forest |
| **Explainability** | SHAP (TreeSHAP), Captum (Grad-CAM), narrative generation |
| **Database** | PostgreSQL + PostGIS |
| **Frontend** | React, Tailwind CSS, Leaflet |
| **Data Sources** | ISRO INSAT (MOSDAC), NASA Earthdata (POWER, GIBS), IMD gridded rainfall, GPM IMERG |
| **Deployment** | Docker, docker-compose |
| **Processing** | OpenCV, pandas, NumPy |

---

## Methodology and Process for Implementation

1. **Data Collection** – Acquire INSAT satellite imagery via MOSDAC; fetch NASA POWER/GIBS meteorological data; collect IMD historical rainfall records
2. **Preprocessing** – Resample to common grid; extract 22 fusion features (13 weather + 7 satellite + 2 branch risk scores); align labels with IMD thresholds (Heavy ≥ 64.5 mm/24h, Extreme ≥ 204.4 mm/24h)
3. **Model Training** – 
   - Tabular branch: Random Forest (300 trees, balanced) → macro-F1 63.4%
   - Satellite branch: Custom CNN → 68.9%; Swin-Tiny (HuggingFace) → 72.8% (best)
   - Fusion: Weighted (w=0.85) → macro-F1 68.8%
4. **Chronological Split** – Train/val/test chronological splits (no random shuffling); 6-fold walk-forward out-of-fold validation
5. **Explainability Integration** – 
   - TreeSHAP: baseline + attributions reconstruct risk score exactly
   - Grad-CAM via Captum: heatmaps saved per prediction
   - Historical analogue: nearest past event matching (≥ 66% similarity)
   - Narrative generator: plain-language explanation
6. **Dashboard Development** – React + Leaflet interactive map; 6 modules: Overview, Alerts, Analysis, Explainability, History, System Status
7. **Audit Trail** – Every warning scored against ground truth next day; POD/FAR/CSI metrics published

**Flow:** Data sources → satellite_processing → data/ + PostGIS → ai_models (tabular/vision/hybrid) → explainability (SHAP/Grad-CAM/narrative) → backend (FastAPI) → frontend (React dashboard)

---

## Analysis of Feasibility

**Strengths:**
- ✅ 24 years of data (70k weather records + 4,999 satellite scene-days) already gathered
- ✅ Phases 1–6 complete: pipeline, tabular model, vision model, fusion engine, explainability layer, dashboard
- ✅ Chronological validation prevents data leakage
- ✅ Walk-forward scoring (6 folds) detected in-sample memorization (AUC 1.000 rejected)
- ✅ ~30 MB model path, laptop-trained (Apple MPS/CPU)—deployable at district control rooms
- ✅ Source-agnostic collector interface; provider-neutral 22-feature schema
- ✅ Honest-by-design: HTTP 501 when models not deployed; CAVEATS blocks on reports

**Limitations:**
- ⚠️ Only 3 Extreme rainfall samples in 4,999 scenes—class unmeasurable
- ⚠️ Fusion (+0.5% vs weather-only) not beating weather baseline on held-out test
- ⚠️ Satellite branch sees day T for day T+1 target (one polar pass/day limitation)
- ⚠️ No sub-daily imagery currently; cloudburst timescale (≤ 100 mm/h) averaged away in 24h aggregates

**Verdict:** Highly feasible as a modular, explainable early-warning system for regions with moderate-high rainfall frequency. Extreme class requires sub-daily data—feasible with ground station integration.

---

## Potential Challenges and Risks

1. **Trust Gap** – Disaster managers may distrust AI warnings without human expertise validation
2. **Extreme Class Scarcity** – Only 3 Extreme samples in 4,999 scenes; 0 in test set
3. **Satellite Temporal Resolution** – One polar pass/day limits convective storm monitoring
4. **Data Alignment** – Satellite imagery (day T) vs. rainfall target (day T+1) mismatch
5. **Class Imbalance** – 98.8% accuracy achievable by predicting "normal" every time; macro-F1 more meaningful (68.8%)
6. **Hardware Constraints** – Laptop-trained; scalability to production unknown
7. **Ground-Segment Dependency** – Current reliance on 4-day-delayed public archives

---

## Strategies for Overcoming Challenges

1. **Build Trust via Explainability** – Every prediction includes TreeSHAP attribution, Grad-CAM heatmap, confidence score, and historical analogue narrative. Audit trail scores warnings against ground truth next day.
2. **Fix Extreme Class Scarcity** – Integrate sub-daily observations: 
   - Ground-based AWS network (Bengaluru pilot: 10 stations × 15-min cadence = 350,400 obs/year ≈ 5× our 24-year archive)
   - GPM IMERG sub-daily precipitation
   - IMD gridded rainfall at cloudburst timescale (≥ 100 mm/h)
3. **Improve Temporal Resolution** – Replace NASA GIBS/POWER with own ground station network: pass-to-image from ~4 days → under 20 minutes. Varuna AI's data layer is source-agnostic—collector swap only, no architecture change.
4. **Address Timing Mismatch** – With sub-hourly imagery, satellite branch weight rises above current 0.15; fusion should overtake weather-only baseline (69.3% macro-F1).
5. **Redefine Selection Metric** – Replace macro-F1 with recall- or cost-weighted criterion; currently flagged in reports as limitation.
6. **Scale Deployment** – ~30 MB decision path sits at edge next to local ground stations; no GPU cluster needed.
7. **Joint Pilot with Ground-Segment Club** – Bengaluru as region #5: ingest AWS feed, evaluate sub-daily imagery, re-label at ≥ 100 mm/h thresholds, auto-verify warnings against AWS ground truth.

---

## Potential Impact on Target Audience

**Primary Users:**
- State and district disaster-management authorities
- Flood-control teams
- Urban-planning teams

**Impact Dimensions:**
- **Faster Decisions** – Authorities get risk score + drivers + heatmap + confidence + similar past event in one dashboard vs. manually checking 5+ weather sources
- **Better Preparedness** – 72-hour forecast lead time + confidence score enables proactive resource pre-positioning
- **Reduced Risk** – Explainability builds trust; audit trail enables post-event analysis and model improvement
- **Safer Communities** – Evacuation planning faster; rescue teams positioned earlier; resources allocated more efficiently
- **Saved Lives** – Evidence-based warnings vs. opaque alerts lead to better compliance and action

**Quantified Benefit:** District authorities can justify alerts with evidence; rescue team deployment optimized; evacuation plans based on demonstrated risk drivers rather than arbitrary color codes.

---

## Benefits of the Solution

| Category | Benefits |
|---|---|
| **Social** | Lives saved through timely evacuations; reduced displacement; faster rescue operations; increased public trust in AI-assisted warnings |
| **Economic** | Reduced property damage from better-preparedness; optimized resource allocation (no over-deployment); lower disaster recovery costs; deployable on district budgets (~30 MB, laptop-trained) |
| **Environmental** | More efficient emergency response = fewer unnecessary evacuations (reduced fuel/emissions); targeted resource deployment minimizes ecological disruption |
| **Operational** | 72-hour forecast lead time; interactive India risk map; audit trail for every warning; modular architecture enables region-wise expansion; honest-by-design prevents false confidence |
| **Innovation** | First explainable AI system for extreme rainfall with SHAP + Grad-CAM + historical analogue on every prediction; source-agnostic collector interface; hybrid fusion with chronological validation; honest metrics (reports name limitations openly) |

---

## Details / Links of Reference and Research Work

**Project Documentation:**
- `README.md` – Full project overview, architecture, getting started
- `docs/system_architecture.md` – Detailed system architecture
- `docs/dataset_schema.md` – Dataset schema and label thresholds
- `docs/development_roadmap.md` – 10-phase development plan

**Reports & Metrics:**
- `reports/model_report_v1.txt` – Model report with macro-F1, accuracy, recall per class
- `reports/satellite_model_report_v1.txt` – Satellite model metrics
- `reports/data_expansion_retrain_report_2026-08-16.md` – Data expansion from 1,215 → 4,999 scene-days
- `reports/xai_report_v1.txt` – Explainability report (TreeSHAP, Grad-CAM, narratives)
- `reports/hf_vision_swin-tiny_report_v1.txt` – Swin-Tiny HuggingFace fine-tune report
- `reports/hybrid_model_report_v1.txt` – Fusion model report

**Code & Models:**
- `ai_models/` – ML models: tabular, vision, hybrid (+ base interfaces `base.py`)
- `explainability/` – SHAP, Grad-CAM, narrative generation
- `satellite_processing/` – Data acquisition (MOSDAC, NASA) & preprocessing
- `backend/` – FastAPI application (api, core, schemas, services, db)
- `frontend/` – React + Tailwind + Leaflet dashboard
- `ai_models/saved_models/model_info.json` – Model registry with 8 models (3 trained)

**Key Metrics Summary:**
- 70,128 weather records (69,888 used for training, 24-year span 2001–2024)
- 4,999 labelled satellite scene-days (294 MB on disk, 311 MB total data)
- 4 regions: Mumbai, Kerala, Assam, Chennai
- 22 fusion features: 13 weather + 7 satellite + 2 branch risk scores
- Best model: Swin-Tiny (satellite) macro-F1 72.8%; Fusion weighted w=0.85 macro-F1 68.8%
- Heavy-class recall: Custom CNN 93.8% > Swin-Tiny 85.0% > Fusion 52.9%
- 5 REST endpoints: `POST /predictions`, `POST /predictions/explain-image`, `GET /predictions/model-info`, `GET /alerts`, `GET /health`
- 12 test suites; 39 frontend TS/TSX files (~2,800 lines); 116 Python modules (~13,900 lines)

**Research References:**
- SHAP (TreeSHAP) for exact feature attribution
- Grad-CAM (Captum) for satellite heatmap generation
- IMD rainfall thresholds: Heavy ≥ 64.5 mm/24h, Extreme ≥ 204.4 mm/24h
- MOSDAC INSAT satellite data
- NASA Earthdata POWER/GIBS meteorological datasets
- GPM IMERG sub-daily precipitation (for future extreme class improvement)
- Chronicological validation best practices (walk-forward, out-of-fold)