import { describe, expect, it } from "vitest";
import { validatePredictionRequest } from "./validation";
import { simulatePrediction } from "./simulator";

const emptyWeather = {
  temperature_c: "",
  humidity_pct: "",
  pressure_hpa: "",
  wind_speed_ms: "",
  cloud_cover_pct: "",
};

describe("validatePredictionRequest", () => {
  it("requires latitude and longitude", () => {
    const { errors, request } = validatePredictionRequest({
      latitude: "",
      longitude: "",
      region_name: "",
      horizon_hours: "12",
      weather: emptyWeather,
    });
    expect(request).toBeNull();
    expect(errors.some((e) => e.field === "latitude")).toBe(true);
  });

  it("enforces humidity 0–100", () => {
    const { errors } = validatePredictionRequest({
      latitude: "10",
      longitude: "76",
      region_name: "Kerala",
      horizon_hours: "12",
      weather: { ...emptyWeather, humidity_pct: "140" },
    });
    expect(errors.some((e) => e.field === "humidity_pct")).toBe(true);
  });

  it("builds a PredictionRequest with optional weather omitted when blank", () => {
    const { errors, request } = validatePredictionRequest({
      latitude: "10",
      longitude: "76.3",
      region_name: "Kerala",
      horizon_hours: "24",
      weather: emptyWeather,
    });
    expect(errors).toEqual([]);
    expect(request).toMatchObject({
      location: { latitude: 10, longitude: 76.3 },
      region_name: "Kerala",
      horizon_hours: 24,
      include_explanation: true,
    });
    expect(request?.weather).toBeUndefined();
  });
});

describe("simulatePrediction", () => {
  it("returns a PredictionResponse-shaped object", () => {
    const result = simulatePrediction({
      location: { latitude: 19.07, longitude: 72.87 },
      region_name: "Mumbai",
      horizon_hours: 12,
      weather: { humidity_pct: 90, cloud_cover_pct: 80 },
    });
    expect(result.model_version).toBe("simulator-0.1.0");
    expect(result.probability).toBeGreaterThanOrEqual(0);
    expect(result.probability).toBeLessThanOrEqual(1);
    expect(["low", "moderate", "heavy", "extreme"]).toContain(result.risk_level);
    expect(result.explanation?.feature_attributions?.length).toBeGreaterThan(0);
  });
});
