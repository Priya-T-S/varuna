import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "../../test/render";
import { PredictionMeta } from "../../components/ui/PredictionMeta";
import { ProvenanceList } from "../../components/ui/ProvenanceList";
import { RiskTimeline } from "../../components/ui/RiskTimeline";
import type { AlertResponse } from "../../types/api";
import { AlertLifecycle } from "./AlertLifecycle";
import { RecommendedActions } from "./RecommendedActions";
import { WhyThisAlert } from "./WhyThisAlert";

vi.mock("../../api/alertsApi", () => ({
  addAlertNote: vi.fn().mockResolvedValue({}),
  reviewAlert: vi.fn().mockResolvedValue({}),
  changeAlertSeverity: vi.fn().mockResolvedValue({}),
  resolveAlert: vi.fn().mockResolvedValue({}),
}));
vi.mock("../../api/systemApi", () => ({ runDemo: vi.fn() }));

import { addAlertNote, changeAlertSeverity } from "../../api/alertsApi";
import { runDemo } from "../../api/systemApi";
import { DemoScenarioModal } from "../demo/DemoScenarioModal";
import { useOperator } from "../../lib/operator";

const now = new Date().toISOString();

const alert: AlertResponse = {
  id: 7, region_name: "Alappuzha, Kerala", location: { latitude: 9.5, longitude: 76.3 }, risk_level: "extreme",
  probability: 0.91, valid_from: now, valid_until: now, message: "m", issued_at: now, is_active: true,
  region: "Kerala", district: "Alappuzha", flood_level: "severe", title: "SEVERE flood risk: Alappuzha (Kerala)",
  rain_probability: 0.53, rain_event_mm: 350, rain_duration_days: 3, top_drivers: [], affected_villages: [],
  similar_incident: null, source: "demo", deliveries: [],
  confidence_label: "Medium", confidence_pct: 51.6, horizon_hours: 24, data_mode: "demo", data_as_of: now,
  why: [
    { icon: "rain", text: "350 mm rain expected over 3 day(s)" },
    { icon: "river", text: "River about 3.1 m above normal (modelled estimate)", modelled: true },
  ],
  timeline: [
    { offset_h: 0, band: "moderate", probability: 0.4 },
    { offset_h: 6, band: "high", probability: 0.53 },
    { offset_h: 12, band: "high", probability: 0.65 },
    { offset_h: 24, band: "severe", probability: 0.79 },
    { offset_h: 48, band: "severe", probability: 0.88 },
    { offset_h: 72, band: "severe", probability: 0.91, beyond_window: true },
  ],
  actions: [
    { text: "Activate the district Emergency Operations Centre", priority: "immediate", owner: "District Collector" },
    { text: "Re-evaluate the situation in 30 minutes", priority: "scheduled", owner: "Control room" },
  ],
  status: "active",
  events: [
    { id: 1, stage: "detected", at: now, actor: "system", detail: "Flood risk reached SEVERE" },
    { id: 2, stage: "generated", at: now, actor: "system", detail: "Warning generated" },
    { id: 3, stage: "reviewed", at: now, actor: "system", detail: "Auto-approved by the default rule" },
    { id: 4, stage: "sent", at: now, actor: "system", detail: "Shown on the dashboard" },
  ],
};

describe("Prediction metadata & timeline", () => {
  it("always shows probability, confidence, freshness and horizon", () => {
    render(<PredictionMeta confidenceLabel="High" dataAsOf={now} dataMode="demo" horizon="Next 24 hours" probability={0.82} />);
    expect(screen.getByText("82%")).toBeInTheDocument();
    expect(screen.getByText("High")).toBeInTheDocument();
    expect(screen.getByText("just now")).toBeInTheDocument();
    expect(screen.getByText("Demo data")).toBeInTheDocument();
    expect(screen.getByText("Next 24 hours")).toBeInTheDocument();
  });

  it("renders Now → +48 h, marks the peak and the end-of-rain point", () => {
    render(<RiskTimeline points={alert.timeline!} />);
    const list = screen.getByRole("list", { name: /risk timeline/i });
    expect(within(list).getByText("Now")).toBeInTheDocument();
    expect(within(list).getByText("+48 h")).toBeInTheDocument();
    expect(within(list).getByText(/\+72 h · rain ends/)).toBeInTheDocument();
    expect(within(list).getByText("Peak")).toBeInTheDocument();
    expect(screen.getByText(/Hydrological projection/)).toBeInTheDocument();
  });
});

describe("Why this alert / actions / lifecycle", () => {
  beforeEach(() => {
    vi.mocked(addAlertNote).mockClear();
    vi.mocked(changeAlertSeverity).mockClear();
    useOperator.setState({ name: "Asha (control room)" });
  });

  it("lists compact reasons and flags modelled facts", async () => {
    const open = vi.fn();
    render(<WhyThisAlert alert={alert} onOpenExplanation={open} />);
    expect(screen.getByText("Why Severe risk?")).toBeInTheDocument();
    expect(screen.getByText("modelled")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /view full explanation/i }));
    expect(open).toHaveBeenCalled();
  });

  it("ticking an action records it in the audit trail as the current operator", async () => {
    renderWithProviders(<RecommendedActions actions={alert.actions!} alert={alert} />);
    expect(screen.getByText(/not automatic commands/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /mark done: activate/i }));
    await waitFor(() =>
      expect(addAlertNote).toHaveBeenCalledWith(7, "Asha (control room)", "Action completed: Activate the district Emergency Operations Centre"),
    );
  });

  it("shows lifecycle progress and lets an operator change severity with a reason", async () => {
    renderWithProviders(<AlertLifecycle alert={alert} />);
    expect(screen.getAllByText("pending")).toHaveLength(2); // acknowledged + resolved not reached
    await userEvent.click(screen.getByRole("button", { name: "Change severity" }));
    await userEvent.selectOptions(screen.getByLabelText("New severity"), "high");
    await userEvent.type(screen.getByLabelText("Details"), "Gauge readings falling");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(changeAlertSeverity).toHaveBeenCalledWith(7, "Asha (control room)", "high", "Gauge readings falling"));
  });
});

describe("Model provenance", () => {
  it("makes estimated and rule-based steps impossible to mistake for trained-model output", () => {
    render(
      <ProvenanceList
        items={[
          { component: "Weather model", kind: "trained", status: "ran", detail: "Random Forest" },
          { component: "Satellite model (CNN)", kind: "trained", status: "estimated", detail: "No satellite image" },
          { component: "Fusion", kind: "tuned", status: "ran", detail: "0.85 × weather" },
          { component: "Village flood risk", kind: "rule-based", status: "ran", detail: "SCS runoff" },
        ]}
      />,
    );
    expect(screen.getByText("How this was computed")).toBeInTheDocument();
    expect(screen.getByText("Estimated")).toBeInTheDocument();
    expect(screen.getByText("Rule-based (not ML)")).toBeInTheDocument();
    expect(screen.getByText("Weighted average (1 tuned weight)")).toBeInTheDocument();
    expect(screen.getAllByText("Trained ML model")).toHaveLength(2);
  });
});

describe("Demo scenario", () => {
  it("runs the pipeline and reveals every stage with real details", async () => {
    vi.mocked(runDemo).mockResolvedValue({
      scenario: "kerala_extreme", title: "Extreme Kerala rainfall", region: "Kerala", alerts_created: [7], top_alert_id: 7, elapsed_ms: 900,
      stages: [
        { key: "data", label: "Data received", detail: "350 mm over 3 day(s) for Kerala (demo input)" },
        { key: "ai", label: "AI analysing", detail: "Fusion model: 53% chance of heavy rain" },
        { key: "risk", label: "Risk detected", detail: "5 district(s) at high or severe flood risk" },
        { key: "explain", label: "Explanation generated", detail: "Top reason: 350 mm rain" },
        { key: "villages", label: "Villages identified", detail: "14 location(s) at risk" },
        { key: "alert", label: "Alert prepared", detail: "5 alert(s) issued" },
      ],
    });
    renderWithProviders(<DemoScenarioModal onClose={() => undefined} />);
    await userEvent.click(screen.getByRole("button", { name: "Run simulation" }));
    expect(await screen.findByText("5 alert(s) issued", {}, { timeout: 4000 })).toBeInTheDocument();
    expect(screen.getByText("14 location(s) at risk")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /view alert/i })).toBeInTheDocument();
    expect(runDemo).toHaveBeenCalledWith("kerala_extreme");
  });
});
