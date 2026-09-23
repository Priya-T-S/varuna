import type { AxiosError } from "axios";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "./client";
import { createPrediction, getModelInfo } from "./predictionsApi";
import { ApiError } from "./errors";

function axiosError(status: number, data: unknown): AxiosError {
  return {
    isAxiosError: true,
    name: "AxiosError",
    message: "Request failed",
    response: { status, data, statusText: "", headers: {}, config: {} as never },
    toJSON: () => ({}),
  } as AxiosError;
}

describe("predictionsApi", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("returns PredictionResponse on 200", async () => {
    const payload = {
      location: { latitude: 10, longitude: 76.3 },
      region_name: "Kerala",
      generated_at: "2026-08-21T12:00:00Z",
      horizon_hours: 12,
      probability: 0.4,
      risk_level: "moderate",
      confidence: 0.7,
      model_version: "v1",
      explanation: null,
    };
    vi.spyOn(apiClient, "post").mockResolvedValue({ data: payload });
    const result = await createPrediction({ location: { latitude: 10, longitude: 76.3 } });
    expect(result.risk_level).toBe("moderate");
    expect(apiClient.post).toHaveBeenCalledWith("/api/v1/predictions", {
      location: { latitude: 10, longitude: 76.3 },
    });
  });

  it("maps HTTP 501 to MODEL_NOT_DEPLOYED", async () => {
    vi.spyOn(apiClient, "post").mockRejectedValue(
      axiosError(501, {
        detail:
          "No trained rainfall model is deployed yet. Model integration is scheduled for Phases 3-6; this endpoint intentionally does not return fabricated predictions.",
      }),
    );
    await expect(createPrediction({ location: { latitude: 10, longitude: 76.3 } })).rejects.toMatchObject({
      code: "MODEL_NOT_DEPLOYED",
      status: 501,
    } satisfies Partial<ApiError>);
  });

  it("maps 422 validation errors", async () => {
    vi.spyOn(apiClient, "post").mockRejectedValue(
      axiosError(422, {
        detail: [{ loc: ["body", "location", "latitude"], msg: "Input should be less than or equal to 90", type: "less_than_equal" }],
      }),
    );
    await expect(
      createPrediction({ location: { latitude: 200, longitude: 0 } }),
    ).rejects.toMatchObject({ code: "VALIDATION" });
  });

  it("loads model-info", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: {
        model_loaded: false,
        artifact_dir: "../ai_models/artifacts",
        expected_models: { tabular: "t", vision: "v", hybrid: "h" },
      },
    });
    const info = await getModelInfo();
    expect(info.model_loaded).toBe(false);
  });
});
