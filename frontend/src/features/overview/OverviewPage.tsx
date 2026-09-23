import { useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { getActiveAlerts } from "../../api/alertsApi";
import { getModelInfo } from "../../api/predictionsApi";
import { LayeredMap } from "../../components/map/LayeredMap";
import { Button } from "../../components/ui/Button";
import { FloodBandChip } from "../../components/ui/FloodBandChip";
import { PredictionMeta } from "../../components/ui/PredictionMeta";
import { RiskTimeline } from "../../components/ui/RiskTimeline";
import { DemoScenarioModal } from "../demo/DemoScenarioModal";
import {
  IconAlertTriangle,
  IconArrowRight,
  IconBell,
  IconCpu,
  IconMapPin,
  IconPlay,
  IconSparkles,
  IconTarget,
} from "../../components/ui/Icons";
import { PageHeader, Panel, StatCard } from "../../components/ui/Panel";
import { RiskChip } from "../../components/ui/RiskChip";
import { EmptyState, ErrorState, Skeleton } from "../../components/ui/States";
import { horizonText } from "../../lib/format";
import { useUiStore } from "../../store/uiStore";
import type { AlertResponse } from "../../types/api";

const LEVEL_ORDER: Record<string, number> = { severe: 0, high: 1, moderate: 2 };

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

export function OverviewPage() {
  const navigate = useNavigate();
  const setSelectedAlertId = useUiStore((s) => s.setSelectedAlertId);
  const selectedAlertId = useUiStore((s) => s.selectedAlertId);
  const [demoOpen, setDemoOpen] = useState(false);

  const alertsQuery = useQuery({ queryKey: ["alerts"], queryFn: getActiveAlerts, refetchInterval: 30000 });
  const modelQuery = useQuery({ queryKey: ["model-info"], queryFn: getModelInfo, refetchInterval: 30000 });

  const alerts = alertsQuery.data ?? [];
  const count = (level: string) => alerts.filter((a) => a.flood_level === level).length;
  const ranked = [...alerts].sort(
    (a, b) => (LEVEL_ORDER[a.flood_level] ?? 9) - (LEVEL_ORDER[b.flood_level] ?? 9) || b.probability - a.probability,
  );
  const villagesAtRisk = new Set(alerts.flatMap((a) => (a.affected_villages ?? []).map((v) => v.name))).size;
  const regions = new Set(alerts.map((a) => a.region)).size;

  function openAlert(alert: AlertResponse) {
    setSelectedAlertId(alert.id);
    navigate("/alerts");
  }

  return (
    <div className="space-y-6">
      <PageHeader
        actions={
          <>
            <Link className="inline-flex items-center gap-1.5 rounded-lg border border-stone-300 bg-white px-3.5 py-2 text-[13.5px] font-medium text-stone-800 shadow-sm hover:bg-stone-50" to="/alerts">
              <IconBell /> View alerts
            </Link>
            <Link className="inline-flex items-center gap-1.5 rounded-lg bg-brand-700 px-3.5 py-2 text-[13.5px] font-medium text-white shadow-sm hover:bg-brand-800" to="/what-if">
              <IconSparkles /> Run a what-if
            </Link>
          </>
        }
        description="Flood and extreme-rainfall risk for Kerala, Mumbai, Chennai and Assam, evaluated on operator-provided, simulated or estimated conditions. Every warning explains why it was generated."
        eyebrow={greeting()}
        title="Situation overview"
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          icon={<IconAlertTriangle />}
          label="Active warnings"
          sub={
            alerts.length
              ? `${count("severe")} severe · ${count("high")} high · ${count("moderate")} moderate`
              : "All districts below alert thresholds"
          }
          tone={count("severe") ? "danger" : alerts.length ? "warn" : "ok"}
          value={alertsQuery.isLoading ? "…" : alerts.length}
        />
        <StatCard
          icon={<IconMapPin />}
          label="Villages at risk"
          sub={alerts.length ? `across ${new Set(alerts.map((a) => a.district)).size} districts in ${regions} region${regions === 1 ? "" : "s"}` : "No village flagged right now"}
          tone={villagesAtRisk ? "warn" : "default"}
          value={villagesAtRisk}
        />
        <StatCard
          icon={<IconTarget />}
          label="Monitored area"
          sub="4 regions · 32 districts · 64 villages & wards"
          tone="brand"
          value="4"
        />
        <StatCard
          icon={<IconCpu />}
          label="AI rainfall model"
          sub={modelQuery.data?.model_loaded ? "Fusion model loaded with SHAP explanations" : "Not loaded: using simulator"}
          tone={modelQuery.data?.model_loaded ? "ok" : "warn"}
          value={<span className="text-[20px]">{modelQuery.isLoading ? "…" : modelQuery.data?.model_loaded ? "Online" : "Offline"}</span>}
        />
      </div>

      <section className="flex flex-col gap-3 rounded-xl border border-brand-200 bg-gradient-to-r from-brand-50 via-white to-white px-5 py-4 shadow-card sm:flex-row sm:items-center sm:gap-4">
        <div className="flex min-w-0 flex-1 items-center gap-4">
          <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-brand-700 text-white"><IconPlay size={20} /></span>
          <div className="min-w-0">
            <p className="text-[15px] font-semibold text-stone-900">Run demo scenario: Extreme Kerala rainfall</p>
            <p className="text-[13px] text-stone-600">350 mm over 3 days on saturated soil. Watch the full pipeline: data → AI → risk → explanation → villages → alert.</p>
          </div>
        </div>
        <Button className="w-full shrink-0 sm:w-auto" onClick={() => setDemoOpen(true)} type="button">
          <IconPlay size={15} /> Run demo scenario
        </Button>
      </section>
      {demoOpen && <DemoScenarioModal onClose={() => setDemoOpen(false)} />}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.55fr)_minmax(20rem,0.8fr)]">
        <LayeredMap
          alerts={alerts}
          className="min-h-[26rem] lg:min-h-[36rem]"
          onSelectAlert={(alert) => setSelectedAlertId(alert.id)}
          selectedAlertId={selectedAlertId}
        />

        <Panel
          actions={
            <Link className="inline-flex items-center gap-1 text-[13px] font-medium text-brand-700 hover:underline" to="/alerts">
              All alerts <IconArrowRight size={14} />
            </Link>
          }
          bodyClassName="p-0"
          description="Most serious first. Click one for details and delivery status."
          title="Active warnings"
        >
          {alertsQuery.isLoading && <div className="p-5"><Skeleton className="h-40" /></div>}
          {alertsQuery.isError && (
            <div className="p-5">
              <ErrorState
                body={alertsQuery.error instanceof Error ? alertsQuery.error.message : "Request failed"}
                title="Warnings could not be loaded"
              />
            </div>
          )}
          {alertsQuery.isSuccess && alerts.length === 0 && (
            <div className="p-5">
              <EmptyState
                action={<Link className="text-[13px] font-medium text-brand-700 hover:underline" to="/what-if">Explore a what-if scenario →</Link>}
                body="No evaluated district is above its flood-alert threshold. The automatic monitor re-evaluates each region on its monthly climatology; enter rainfall or run the demo to evaluate a situation."
                icon={<IconBell />}
                title="All clear"
              />
            </div>
          )}
          {ranked.length > 0 && (
            <ul className="scroll-quiet max-h-[30rem] divide-y divide-stone-100 overflow-y-auto">
              {ranked.slice(0, 10).map((alert) => (
                <li key={alert.id}>
                  <button
                    className="flex w-full items-start gap-3 px-5 py-3.5 text-left transition-colors hover:bg-stone-50"
                    onClick={() => openAlert(alert)}
                    type="button"
                  >
                    <span
                      className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full"
                      style={{ background: { severe: "#b3342b", high: "#c8612a", moderate: "#b08a1f" }[alert.flood_level] ?? "#78716c" }}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center justify-between gap-2">
                        <span className="truncate text-[14px] font-semibold text-stone-900">{alert.district ?? alert.region_name}</span>
                        {alert.flood_level ? <FloodBandChip band={alert.flood_level} /> : <RiskChip level={alert.risk_level} />}
                      </span>
                      <PredictionMeta
                        className="mt-1"
                        compact
                        confidenceLabel={alert.confidence_label}
                        dataAsOf={alert.data_as_of ?? alert.issued_at}
                        dataMode={alert.data_mode}
                        horizon={horizonText(alert.timeline, alert.horizon_hours ?? 24)}
                        probability={alert.probability}
                      />
                      {alert.timeline && alert.timeline.length > 0 && <RiskTimeline className="mt-1.5" compact points={alert.timeline} />}
                      {alert.why && alert.why.length > 0 ? (
                        <span className="mt-1.5 block space-y-0.5">
                          {alert.why.slice(0, 3).map((w) => (
                            <span className="block truncate text-[12.5px] text-stone-600" key={w.text}>• {w.text}</span>
                          ))}
                        </span>
                      ) : alert.affected_villages?.length > 0 && (
                        <span className="mt-1 block truncate text-[12.5px] text-stone-600">
                          {alert.affected_villages.slice(0, 3).map((v) => v.name).join(", ")}
                        </span>
                      )}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <QuickAction
          body="Describe a situation like “20% more rain in Kerala”. See which villages would flood, why, and when it happened before."
          icon={<IconSparkles size={20} />}
          title="Ask the flood advisor"
          to="/what-if"
        />
        <QuickAction
          body="Add district collectors, choose Telegram, e-mail, SMS or WhatsApp, and set when they are alerted."
          icon={<IconBell size={20} />}
          title="Set up alert recipients"
          to="/alerts/settings"
        />
        <QuickAction
          body="Pick any point on the map and get the AI's heavy-rain forecast with a full explanation."
          icon={<IconTarget size={20} />}
          title="Analyse a location"
          to="/analysis"
        />
      </div>
    </div>
  );
}

function QuickAction({ title, body, icon, to }: { title: string; body: string; icon: ReactNode; to: string }) {
  return (
    <Link
      className="group flex gap-4 rounded-xl border border-stone-200/80 bg-paper p-5 shadow-card transition-all hover:-translate-y-0.5 hover:border-brand-200 hover:shadow-lift"
      to={to}
    >
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand-600 transition-colors group-hover:bg-brand-700 group-hover:text-white">
        {icon}
      </span>
      <span>
        <span className="flex items-center gap-1 text-[15px] font-semibold text-stone-900">
          {title}
          <IconArrowRight className="opacity-0 transition-opacity group-hover:opacity-100" size={14} />
        </span>
        <span className="mt-1 block text-[13px] leading-relaxed text-stone-500">{body}</span>
      </span>
    </Link>
  );
}
