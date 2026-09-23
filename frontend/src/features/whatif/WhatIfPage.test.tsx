import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "../../test/render";
import { ApiError } from "../../api/errors";
import { Markdown } from "../../components/ui/Markdown";
import type { ScenarioResult } from "../../types/api";
import { WhatIfPage } from "./WhatIfPage";
import { useWhatIfStore } from "./whatIfStore";

vi.mock("./VillageRiskMap", () => ({ VillageRiskMap: () => <div data-testid="village-map" /> }));
vi.mock("../../api/scenarioApi", () => ({ sendChat: vi.fn(), simulateScenario: vi.fn() }));

import { sendChat, simulateScenario } from "../../api/scenarioApi";

const village = {
  id: "KL-ALP-KUTTANAD", name: "Kuttanad (Kainakary)", district: "Alappuzha", region: "Kerala",
  lat: 9.47, lon: 76.4, population: 21000, baseline_probability: 0.86, flood_probability: 0.88,
  baseline_band: "high" as const, band: "severe" as const, band_increased: true, runoff_mm: 210,
  expected_depth_m: 2.1, landslide_risk: false,
  factors: [{ factor: "runoff", label: "Surface runoff", value: 0.8, contribution: 2.4, detail: "210 mm runs off" }],
  reasons: ["Only 0.5 m above the nearest drainage channel"],
};

const result: ScenarioResult = {
  region: "Kerala",
  scenario: { region: "Kerala", rainfall_change_pct: 20, duration_days: 3, antecedent: "normal" },
  baseline_rain: { rain_1d_mm: 90, rain_3d_mm: 220, rain_7d_mm: 313, rain_30d_mm: 810, event_total_mm: 220, duration_days: 3, change_pct: 0 },
  scenario_rain: { rain_1d_mm: 108, rain_3d_mm: 264, rain_7d_mm: 357, rain_30d_mm: 854, event_total_mm: 264, duration_days: 3, change_pct: 20 },
  baseline_model: { probability: 0.57, risk_level: "moderate", confidence: 0.6, class_probabilities: {} },
  scenario_model: { probability: 0.54, risk_level: "moderate", confidence: 0.6, class_probabilities: {} },
  model_delta: -0.03,
  driver_changes: [{ feature: "rain_sum_3d", label: "Rainfall past 3 days", baseline_value: 220, scenario_value: 264, baseline_contribution: 0.1, scenario_contribution: 0.09, delta: -0.01 }],
  villages: [village],
  summary: { villages_assessed: 16, villages_high_or_severe: 7, newly_at_risk: 2, population_at_risk: 185500, districts_at_risk: ["Alappuzha"], headline: "+20% rain (264 mm over 3 days) puts 7 of 16 Kerala locations at high/severe flood risk." },
  similar_incidents: [{ id: "KL-2018-08", name: "Kerala floods (Great Flood of 2018)", date: "2018-08-15", region: "Kerala", districts: [], villages: [], rainfall_mm: 310, rainfall_window_days: 3, deaths: 480, displaced: 1400000, causes: [], summary: "Dams opened.", source: "PDNA", why_similar: ["same region (Kerala)"] }],
  model_analogues: [],
  assumptions: ["Baseline = reference spell"],
  caveats: ["Indicative only"],
};

describe("What-if page", () => {
  beforeEach(() => {
    vi.mocked(sendChat).mockReset();
    vi.mocked(simulateScenario).mockReset();
    useWhatIfStore.getState().reset();
  });

  it("sends a suggested question and renders the answer, villages and incidents", async () => {
    vi.mocked(sendChat).mockResolvedValue({
      session_id: "s1",
      reply_markdown: "**What could happen**\n- Kuttanad goes severe",
      scenario: result,
      incidents: [],
      villages: [],
      tools_used: ["simulate_flood_scenario"],
      model: "claude-opus-5",
    });
    renderWithProviders(<WhatIfPage />);
    await userEvent.click(screen.getByRole("button", { name: /rainfall increases by 20% in Kerala/i }));

    expect(await screen.findByText("What could happen")).toBeInTheDocument();
    expect(screen.getAllByText(/Kuttanad/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Great Flood of 2018/)).toBeInTheDocument();
    expect(screen.getByText(/ran flood simulation/i)).toBeInTheDocument();
    expect(vi.mocked(sendChat)).toHaveBeenCalledWith({ message: expect.stringContaining("20%"), session_id: null });
    expect(useWhatIfStore.getState().sessionId).toBe("s1");
  });

  it("falls back to the direct simulator when the assistant is not configured", async () => {
    vi.mocked(sendChat).mockRejectedValue(
      new ApiError({ message: "The what-if assistant is not configured.", status: 503, detail: "x", code: "HTTP" }),
    );
    vi.mocked(simulateScenario).mockResolvedValue(result);
    renderWithProviders(<WhatIfPage />);

    await userEvent.type(screen.getByLabelText(/describe a rainfall scenario/i), "Kerala +20%{enter}");
    expect(await screen.findByText(/run the simulation directly/i)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /run simulation/i }));
    await waitFor(() => expect(vi.mocked(simulateScenario)).toHaveBeenCalled());
    expect(await screen.findByText(/7 of 16 Kerala locations/)).toBeInTheDocument();
  });
});

describe("Markdown", () => {
  it("renders formatting as elements and never injects HTML", () => {
    const { container } = render(<Markdown text={"## Title\n**bold** and `code`\n1. one\n2. two\n<img src=x onerror=alert(1)>"} />);
    expect(container.querySelector("strong")?.textContent).toBe("bold");
    expect(container.querySelectorAll("ol li")).toHaveLength(2);
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("<img src=x onerror=alert(1)>");
  });
});
