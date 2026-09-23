/** Display labels only — API field names stay as-is in payloads. */
export const FEATURE_LABELS: Record<string, string> = {
  temperature_c: "Surface air temperature",
  humidity_pct: "Relative humidity",
  pressure_hpa: "Mean sea-level pressure",
  wind_speed_ms: "Wind speed",
  cloud_cover_pct: "Total cloud cover",
  wind_direction_deg: "Wind direction",
  rain_sum_1d: "Rainfall, past 24 h",
  rain_sum_3d: "Rainfall, past 3 days",
  rain_sum_7d: "Rainfall, past 7 days",
  rain_sum_30d: "Rainfall, past 30 days",
  rain_trend_3d: "3-day rainfall trend",
  season_sin: "Season (sin)",
  season_cos: "Season (cos)",
  weather_risk_score: "Weather-branch risk",
  satellite_risk_score: "Satellite-branch risk",
  latitude: "Latitude",
  longitude: "Longitude",
  horizon_hours: "Forecast horizon",
};

export const FEATURE_UNITS: Record<string, string> = {
  temperature_c: "°C",
  humidity_pct: "%",
  pressure_hpa: "hPa",
  wind_speed_ms: "m/s",
  cloud_cover_pct: "%",
  wind_direction_deg: "°",
  rain_sum_1d: "mm",
  rain_sum_3d: "mm",
  rain_sum_7d: "mm",
  rain_sum_30d: "mm",
  latitude: "°",
  longitude: "°",
  horizon_hours: "h",
};

export function featureLabel(feature: string): string {
  return FEATURE_LABELS[feature] ?? feature;
}

export function featureUnit(feature: string): string {
  return FEATURE_UNITS[feature] ?? "";
}
