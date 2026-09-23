import { test, expect } from "@playwright/test";

const health = { status: "ok", service: "VARUNA AI", version: "0.1.0", environment: "development" };
const modelInfo = {
  model_loaded: false,
  artifact_dir: "../ai_models/artifacts",
  expected_models: {
    tabular: "Gradient-boosted classifier on meteorological features (Phase 3)",
    vision: "CNN on INSAT satellite imagery (Phase 4)",
    hybrid: "Fusion of tabular + vision outputs (Phase 5)",
  },
};
const sampleAlert = {
  id: 1,
  region_name: "Kerala",
  location: { latitude: 10.0, longitude: 76.3 },
  risk_level: "heavy",
  probability: 0.72,
  valid_from: "2026-08-21T00:00:00Z",
  valid_until: "2026-08-21T12:00:00Z",
  message: "Heavy rainfall risk for Kerala over the next 12 hours.",
  issued_at: "2026-08-21T00:00:00Z",
  is_active: true,
};

test("Overview → alert → Analysis → prediction → Explainability", async ({ page }) => {
  await page.route("**/api/v1/health", async (route) => {
    await route.fulfill({ json: health });
  });
  await page.route("**/api/v1/predictions/model-info", async (route) => {
    await route.fulfill({ json: modelInfo });
  });
  await page.route("**/api/v1/alerts", async (route) => {
    await route.fulfill({ json: [sampleAlert] });
  });
  await page.route("**/api/v1/predictions", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({
        status: 501,
        contentType: "application/json",
        body: JSON.stringify({
          detail:
            "No trained rainfall model is deployed yet. Model integration is scheduled for Phases 3-6; this endpoint intentionally does not return fabricated predictions.",
        }),
      });
      return;
    }
    await route.fallback();
  });

  await page.goto("/");
  await expect(page.getByRole("banner").getByText("VARUNA AI")).toBeVisible();
  await expect(page.getByRole("button", { name: /Kerala/ })).toBeVisible();
  await page.getByRole("button", { name: /Kerala/ }).click();
  await expect(page).toHaveURL(/\/alerts/);
  await page.getByRole("button", { name: "Open in Analysis" }).click();
  await expect(page).toHaveURL(/\/analysis/);
  await expect(page.getByLabel("Place name")).toHaveValue("Kerala");
  await page.getByTestId("run-prediction").click();
  await expect(page.getByTestId("simulated-banner")).toBeVisible();
  await page.getByRole("button", { name: "Open explanation" }).click();
  await expect(page).toHaveURL(/\/explainability/);
  await expect(page.getByText("SHAP feature attributions")).toBeVisible();
  await expect(page.getByTestId("simulated-banner")).toBeVisible();
});
