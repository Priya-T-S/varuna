# Data Expansion and Retraining Report - 2026-08-16

## What Was Fetched

- Source: NASA GIBS / Worldview MODIS Terra imagery.
- Layers per scene-day:
  - `MODIS_Terra_CorrectedReflectance_TrueColor`
  - `MODIS_Terra_CorrectedReflectance_Bands721`
- Target selected scene-days: 5,000.
- Usable labeled scene-days written: 4,999.
- Raw image files currently on disk: 10,000.
- Raw satellite image folder size: 294 MB.
- Total `data/` folder size: 312 MB.

One selected scene-day had a snapshot failure during fetch, so the final label table has 4,999 rows instead of exactly 5,000.

## Label Data

File: `data/labels/satellite_labels.parquet`

- Rows: 4,999
- Regions: Assam, Chennai, Kerala, Mumbai
- Date range: 2001-01-03 to 2024-12-28
- Class counts:
  - Normal: 4,514
  - Heavy: 482
  - Extreme: 3

## Satellite Feature Data

File: `data/processed/features/satellite_features.parquet`

- Rows: 4,960
- Columns: 10
- Regions: Assam, Chennai, Kerala, Mumbai
- Date range: 2001-01-03 to 2024-12-28
- Class counts:
  - Normal: 4,481
  - Heavy: 476
  - Extreme: 3

Feature rows are lower than label rows because some MODIS scenes were rejected as swath gaps / unusable imagery.

## Satellite Model Retrain

Command run:

```bash
PYTHONPATH=. backend/.venv/bin/python -m ai_models.satellite_model.train
```

Output artifacts:

- Model: `ai_models/saved_models/satellite_model_v1.pt`
- Report: `reports/satellite_model_report_v1.txt`
- Features for fusion: `data/processed/features/satellite_features.parquet`

Result:

- Selected model: `custom_cnn`
- Test accuracy: 80.5%
- Test macro precision: 66.6%
- Test macro recall: 86.3%
- Test macro F1: 68.9%
- Validation macro F1: 72.4%

Important note: ResNet18 and ViT candidates were skipped because pretrained weight downloads tried to write to the blocked Torch cache path under the user home directory. The custom CNN did train and was saved.

## Hybrid / Fusion Model Retrain

Command run:

```bash
PYTHONPATH=. backend/.venv/bin/python -m ai_models.fusion_model.train
```

Output artifacts:

- Fusion bundle: `ai_models/saved_models/varuna_fusion_model_v1.pkl`
- Model info: `ai_models/saved_models/model_info.json`
- Report: `reports/hybrid_model_report_v1.txt`
- Unified dataset: `data/processed/datasets/fusion_dataset.parquet`

Fusion dataset:

- Rows: 3,963
- Columns: 35
- Regions: Assam, Chennai, Kerala, Mumbai
- Date range: 2004-09-01 to 2024-12-28
- Target counts:
  - Normal: 3,793
  - Heavy: 169
  - Extreme: 1
- Split sizes:
  - Train: 2,748
  - Validation: 592
  - Test: 623

Selected fusion:

- Model: `weighted_fusion_w0.85`
- Approach: weighted fusion
- Weather weight: 0.85

Held-out test macro F1:

- Weather-only: 69.3%
- Satellite-only: 53.1%
- Fusion: 68.8%

Honest conclusion: fusion improved a lot over satellite-only, but it did not beat weather-only on the held-out test set. Weather-only scored 69.3% macro F1, fusion scored 68.8% macro F1.

## Main Limitation

The expanded image dataset is much larger now, but Extreme examples are still almost absent:

- Satellite labels have only 3 Extreme samples.
- Fusion dataset has only 1 Extreme sample.
- Held-out fusion test has 0 Extreme samples.

So the model still cannot prove that it handles Extreme rainfall well. For that, the project needs more real extreme-event labels, likely from IMD gridded rainfall or GPM IMERG, not just more normal NASA imagery.
