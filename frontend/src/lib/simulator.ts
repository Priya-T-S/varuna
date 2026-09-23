import type { FeatureAttribution, PredictionRequest, PredictionResponse, RiskLevel } from "../types/api";

export const SIMULATOR_MODEL_VERSION = "simulator-0.1.0";

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function riskFromProbability(probability: number): RiskLevel {
  if (probability >= 0.8) return "extreme";
  if (probability >= 0.6) return "heavy";
  if (probability >= 0.35) return "moderate";
  return "low";
}

function contrib(feature: string, value: number | null, contribution: number): FeatureAttribution {
  return { feature, value, contribution };
}

/**
 * Local, clearly-labeled stand-in used only when POST /api/v1/predictions
 * returns 501 or the user forces simulator mode. Output shape matches
 * PredictionResponse exactly.
 */
export function simulatePrediction(request: PredictionRequest): PredictionResponse {
  const weather = request.weather ?? {};
  const humidity = weather.humidity_pct ?? 70;
  const cloud = weather.cloud_cover_pct ?? 55;
  const wind = weather.wind_speed_ms ?? 4;
  const pressure = weather.pressure_hpa ?? 1008;
  const temp = weather.temperature_c ?? 27;
  const horizon = request.horizon_hours ?? 12;

  const humidityTerm = (humidity - 50) / 200;
  const cloudTerm = (cloud - 40) / 180;
  const pressureTerm = (1013 - pressure) / 80;
  const windTerm = Math.min(wind, 25) / 80;
  const latTerm = (Math.abs(request.location.latitude) - 15) / 120;

  let probability = 0.22 + humidityTerm + cloudTerm + pressureTerm + windTerm + latTerm;
  probability = clamp(probability, 0.04, 0.97);
  const confidence = clamp(0.55 + Math.abs(humidityTerm) + Math.abs(cloudTerm) * 0.4, 0.4, 0.92);
  const risk_level = riskFromProbability(probability);

  const attributions: FeatureAttribution[] = [
    contrib("humidity_pct", weather.humidity_pct ?? null, humidityTerm * 0.9),
    contrib("cloud_cover_pct", weather.cloud_cover_pct ?? null, cloudTerm * 0.85),
    contrib("pressure_hpa", weather.pressure_hpa ?? null, pressureTerm * 0.7),
    contrib("wind_speed_ms", weather.wind_speed_ms ?? null, windTerm * 0.5),
    contrib("temperature_c", weather.temperature_c ?? null, ((temp - 26) / 40) * 0.15),
    contrib("latitude", request.location.latitude, latTerm * 0.35),
    contrib("longitude", request.location.longitude, 0.01),
    contrib("horizon_hours", horizon, (horizon - 12) / 400),
  ].sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution));

  const top = attributions[0];
  const place = request.region_name?.trim() || `${request.location.latitude.toFixed(2)}°N, ${request.location.longitude.toFixed(2)}°E`;
  const direction = (top?.contribution ?? 0) >= 0 ? "raised" : "lowered";

  const heatmapSvg = `<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">
    <defs>
      <radialGradient id="g" cx="62%" cy="38%" r="55%">
        <stop offset="0%" stop-color="#a33b32" stop-opacity="0.85"/>
        <stop offset="45%" stop-color="#c06a2c" stop-opacity="0.55"/>
        <stop offset="100%" stop-color="#3d5a6c" stop-opacity="0.12"/>
      </radialGradient>
    </defs>
    <rect width="256" height="256" fill="#1c1917"/>
    <rect x="0" y="0" width="256" height="256" fill="url(#g)"/>
  </svg>`;

  return {
    location: request.location,
    region_name: request.region_name ?? null,
    generated_at: new Date().toISOString(),
    horizon_hours: horizon,
    probability,
    risk_level,
    confidence,
    model_version: SIMULATOR_MODEL_VERSION,
    explanation: request.include_explanation === false
      ? null
      : {
          feature_attributions: attributions,
          image_explanation: {
            satellite_image_id: "simulator-synthetic",
            heatmap_url: `data:image/svg+xml;charset=utf-8,${encodeURIComponent(heatmapSvg)}`,
            description:
              "Synthetic Grad-CAM stand-in. POST /api/v1/predictions does not accept satellite imagery; no real overlay is available until the vision model is deployed.",
          },
          narrative: `Simulated ${horizon}-hour assessment for ${place}: probability of a high-impact rain event is ${(probability * 100).toFixed(1)}% (${risk_level}). The largest simulated driver ${direction} risk via ${top?.feature ?? "weather inputs"}. This is not a model output.`,
          historical_explanation: {
            reference_events: 142,
            closest_match: {
              event: `${place} 2018-08-15 (Heavy, 119 mm)`,
              region: place,
              date: "2018-08-15",
              observed_category: 2,
              observed_rainfall_mm: 119.0,
              similarity: 0.84,
              similarity_pct: 84.0,
            },
            matches: [
              {
                event: `${place} 2018-08-15 (Heavy, 119 mm)`,
                region: place,
                date: "2018-08-15",
                observed_category: 2,
                observed_rainfall_mm: 119.0,
                similarity: 0.84,
                similarity_pct: 84.0,
              },
              {
                event: `${place} 2019-07-25 (Moderate, 45 mm)`,
                region: place,
                date: "2019-07-25",
                observed_category: 1,
                observed_rainfall_mm: 45.0,
                similarity: 0.72,
                similarity_pct: 72.0,
              },
            ],
            notes: ["Simulated historical matching."],
          },
          confidence_explanation: {
            confidence_pct: Math.round(confidence * 1000) / 10,
            confidence: confidence >= 0.8 ? "High" : confidence >= 0.5 ? "Medium" : "Low",
            factors: {
              model_agreement: 0.85,
              historical_similarity: 0.84,
              data_quality: "Good",
              data_quality_score: 0.95,
            },
            components: {},
          },
          caveats: [
            "This is a simulated prediction run using the local frontend simulator fallback.",
          ],
        },
  };
}
