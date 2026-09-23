import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AnalysisPage } from "./AnalysisPage";
import { renderWithProviders } from "../../test/render";
import { useUiStore } from "../../store/uiStore";
import { ApiError } from "../../api/errors";
import { ExplainabilityPage } from "../explainability/ExplainabilityPage";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";

vi.mock("../../components/map/IndiaMap", () => ({
  IndiaMap: () => <div data-testid="map" />,
}));

vi.mock("../../api/predictionsApi", () => ({
  createPrediction: vi.fn(),
}));

import { createPrediction } from "../../api/predictionsApi";

describe("Analysis workflow", () => {
  beforeEach(() => {
    vi.mocked(createPrediction).mockReset();
    useUiStore.setState({
      simulatorMode: "auto",
      lastModelUnavailableDetail: null,
      activeAnalysis: null,
      analysisDraft: {
        latitude: "19.0760",
        longitude: "72.8777",
        region_name: "Mumbai",
        horizon_hours: "12",
        weather: {
          temperature_c: "",
          humidity_pct: "90",
          pressure_hpa: "",
          wind_speed_ms: "",
          cloud_cover_pct: "80",
        },
      },
      history: [],
    });
  });

  it("blocks submit when latitude is invalid", async () => {
    const user = userEvent.setup();
    renderWithProviders(<AnalysisPage />, { route: "/analysis" });
    await user.clear(screen.getByLabelText(/latitude/i));
    await user.type(screen.getByLabelText(/latitude/i), "999");
    await user.click(screen.getByTestId("run-prediction"));
    expect(await screen.findByText(/Latitude must be between/)).toBeInTheDocument();
    expect(createPrediction).not.toHaveBeenCalled();
  });

  it("falls back to simulator on 501 and labels the result", async () => {
    vi.mocked(createPrediction).mockRejectedValue(
      new ApiError({
        message: "No trained rainfall model is deployed yet.",
        status: 501,
        detail: "No trained rainfall model is deployed yet.",
        code: "MODEL_NOT_DEPLOYED",
      }),
    );
    const user = userEvent.setup();
    renderWithProviders(<AnalysisPage />, { route: "/analysis" });
    await user.click(screen.getByTestId("run-prediction"));
    expect(await screen.findByTestId("simulated-banner")).toBeInTheDocument();
    expect(screen.getByText("Risk level")).toBeInTheDocument();
  });

  it("navigates to explainability with the simulated badge still present", async () => {
    vi.mocked(createPrediction).mockRejectedValue(
      new ApiError({
        message: "No trained rainfall model is deployed yet.",
        status: 501,
        detail: "No trained rainfall model is deployed yet.",
        code: "MODEL_NOT_DEPLOYED",
      }),
    );
    const user = userEvent.setup();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/analysis"]}>
          <Routes>
            <Route element={<AnalysisPage />} path="/analysis" />
            <Route element={<ExplainabilityPage />} path="/explainability" />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await user.click(screen.getByTestId("run-prediction"));
    await screen.findByTestId("simulated-banner");
    await user.click(screen.getByRole("button", { name: "Open explanation" }));
    await waitFor(() => {
      expect(screen.getByText("SHAP feature attributions")).toBeInTheDocument();
    });
    expect(screen.getAllByTestId("simulated-banner").length).toBeGreaterThan(0);
  });
});
