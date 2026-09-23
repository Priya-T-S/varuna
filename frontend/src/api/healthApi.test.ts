import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiClient } from "./client";
import { getHealth } from "./healthApi";
import { getActiveAlerts } from "./alertsApi";

describe("healthApi", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("returns the health object", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      data: { status: "ok", service: "VARUNA AI", version: "0.1.0", environment: "development" },
    });
    await expect(getHealth()).resolves.toEqual({
      status: "ok",
      service: "VARUNA AI",
      version: "0.1.0",
      environment: "development",
    });
  });
});

describe("alertsApi", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("returns an empty list when the backend has no alerts", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({ data: [] });
    await expect(getActiveAlerts()).resolves.toEqual([]);
  });
});
