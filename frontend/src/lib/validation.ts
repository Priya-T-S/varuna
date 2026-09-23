import type { PredictionRequest, WeatherFeatures } from "../types/api";

export interface FieldError {
  field: string;
  message: string;
}

function isNum(value: unknown): value is number {
  return typeof value === "number" && !Number.isNaN(value);
}

export function validatePredictionRequest(input: {
  latitude: string;
  longitude: string;
  region_name: string;
  horizon_hours: string;
  weather: Record<keyof WeatherFeatures, string>;
}): { errors: FieldError[]; request: PredictionRequest | null } {
  const errors: FieldError[] = [];
  const lat = Number(input.latitude);
  const lon = Number(input.longitude);

  if (input.latitude.trim() === "" || Number.isNaN(lat)) {
    errors.push({ field: "latitude", message: "Latitude is required." });
  } else if (lat < -90 || lat > 90) {
    errors.push({ field: "latitude", message: "Latitude must be between −90 and 90." });
  }

  if (input.longitude.trim() === "" || Number.isNaN(lon)) {
    errors.push({ field: "longitude", message: "Longitude is required." });
  } else if (lon < -180 || lon > 180) {
    errors.push({ field: "longitude", message: "Longitude must be between −180 and 180." });
  }

  const horizon = input.horizon_hours.trim() === "" ? 12 : Number(input.horizon_hours);
  if (Number.isNaN(horizon) || !Number.isInteger(horizon) || horizon < 1 || horizon > 72) {
    errors.push({ field: "horizon_hours", message: "Horizon must be an integer from 1 to 72 hours." });
  }

  const weather: WeatherFeatures = {};
  const ranges: Array<{
    key: keyof WeatherFeatures;
    min?: number;
    max?: number;
    label: string;
  }> = [
    { key: "temperature_c", label: "Temperature" },
    { key: "humidity_pct", min: 0, max: 100, label: "Relative humidity" },
    { key: "pressure_hpa", label: "Pressure" },
    { key: "wind_speed_ms", min: 0, label: "Wind speed" },
    { key: "cloud_cover_pct", min: 0, max: 100, label: "Cloud cover" },
  ];

  for (const range of ranges) {
    const raw = input.weather[range.key].trim();
    if (raw === "") continue;
    const value = Number(raw);
    if (Number.isNaN(value)) {
      errors.push({ field: range.key, message: `${range.label} must be a number.` });
      continue;
    }
    if (range.min !== undefined && value < range.min) {
      errors.push({ field: range.key, message: `${range.label} must be ≥ ${range.min}.` });
    }
    if (range.max !== undefined && value > range.max) {
      errors.push({ field: range.key, message: `${range.label} must be ≤ ${range.max}.` });
    }
    weather[range.key] = value;
  }

  if (errors.length) return { errors, request: null };

  const request: PredictionRequest = {
    location: { latitude: lat, longitude: lon },
    horizon_hours: horizon,
    include_explanation: true,
  };

  const region = input.region_name.trim();
  if (region) request.region_name = region;
  if (Object.values(weather).some((v) => isNum(v))) request.weather = weather;

  return { errors, request };
}
