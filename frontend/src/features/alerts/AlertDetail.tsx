import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { acknowledgeAlert } from "../../api/alertsApi";
import { Button } from "../../components/ui/Button";
import { FloodBandChip } from "../../components/ui/FloodBandChip";
import { IconCheck } from "../../components/ui/Icons";
import { PredictionMeta } from "../../components/ui/PredictionMeta";
import { ProvenanceList } from "../../components/ui/ProvenanceList";
import { RiskTimeline } from "../../components/ui/RiskTimeline";
import { cn } from "../../lib/cn";
import { formatDateTime, formatRelative, horizonText } from "../../lib/format";
import { operatorOrDefault, useOperator } from "../../lib/operator";
import type { AlertResponse } from "../../types/api";
import { AlertExplanationDrawer } from "./AlertExplanationDrawer";
import { AlertLifecycle } from "./AlertLifecycle";
import { RecommendedActions } from "./RecommendedActions";
import { WhyThisAlert } from "./WhyThisAlert";

const CHANNEL_LABEL: Record<string, string> = {
  telegram: "Telegram", email: "E-mail", sms: "SMS", whatsapp: "WhatsApp", inapp: "Dashboard", console: "Server log",
};
const DELIVERY_STYLE: Record<string, string> = {
  sent: "bg-emerald-50 text-emerald-700",
  failed: "bg-red-50 text-red-700",
  skipped: "bg-stone-100 text-stone-500",
};
const DATA_SOURCE: Record<string, string> = {
  observed: "Operator-entered rainfall",
  demo: "Demo scenario (simulated rainfall)",
  climatology: "Monthly rainfall climatology (estimated, no live feed)",
  scenario: "What-if scenario (simulated)",
  test: "Test data",
};
const STATUS_STYLE: Record<string, string> = {
  active: "bg-amber-50 text-amber-800 ring-amber-600/20",
  acknowledged: "bg-emerald-50 text-emerald-800 ring-emerald-600/20",
  resolved: "bg-stone-100 text-stone-600 ring-stone-400/30",
};

export function AlertDetail({ alert, onAnalyze }: { alert: AlertResponse; onAnalyze: () => void }) {
  const queryClient = useQueryClient();
  const operator = useOperator((s) => s.name);
  const [explainOpen, setExplainOpen] = useState(false);
  const ack = useMutation({
    mutationFn: () => acknowledgeAlert(alert.id, operatorOrDefault(operator)),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alerts"] }),
  });
  const deliveries = alert.deliveries ?? [];
  const villages = alert.affected_villages ?? [];
  const status = alert.status ?? (alert.acknowledged_at ? "acknowledged" : "active");

  return (
    <div className="space-y-6 text-sm">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <FloodBandChip band={alert.flood_level} />
          <span className={cn("rounded-full px-2 py-0.5 text-[11.5px] font-medium capitalize ring-1 ring-inset", STATUS_STYLE[status] ?? STATUS_STYLE.active)}>
            {status}
          </span>
          {alert.source === "demo" && <span className="rounded-full bg-violet-50 px-2 py-0.5 text-[11.5px] font-medium text-violet-700">Demo</span>}
          <span className="text-[12.5px] text-stone-500">
            #{alert.id} · issued {formatRelative(alert.issued_at)} · valid until {formatDateTime(alert.valid_until)}
          </span>
        </div>
        <h3 className="mt-2 text-[18px] font-semibold text-stone-900">{alert.district}, {alert.region}</h3>
        {alert.supersedes_id && <p className="text-[12.5px] text-stone-500">Replaces alert #{alert.supersedes_id}</p>}
        <p className="mt-1.5 rounded-md bg-stone-50 px-2.5 py-1.5 text-[12.5px] text-stone-600">
          Generated automatically because the evaluated district risk crossed the configured threshold.{" "}
          <b className="font-semibold text-stone-800">Data source:</b> {DATA_SOURCE[alert.data_mode ?? ""] ?? "Not recorded"}
          {" · "}river levels modelled (estimated).
        </p>
      </div>

      <PredictionMeta
        confidenceLabel={alert.confidence_label}
        confidencePct={alert.confidence_pct}
        dataAsOf={alert.data_as_of ?? alert.issued_at}
        dataMode={alert.data_mode}
        horizon={horizonText(alert.timeline, alert.horizon_hours ?? 24)}
        probability={alert.probability}
      />

      <WhyThisAlert alert={alert} onOpenExplanation={() => setExplainOpen(true)} />

      {alert.timeline && alert.timeline.length > 0 && (
        <section>
          <h4 className="mb-2 text-[14px] font-semibold text-stone-900">Risk timeline</h4>
          <RiskTimeline points={alert.timeline} />
        </section>
      )}

      <RecommendedActions actions={alert.actions ?? []} alert={alert} readOnly={status === "resolved"} />

      <ProvenanceList items={alert.provenance} />

      {villages.length > 0 && (
        <section>
          <h4 className="mb-2 text-[14px] font-semibold text-stone-900">Villages at risk</h4>
          <ul className="divide-y divide-stone-100 rounded-lg border border-stone-200">
            {villages.map((v) => (
              <li className="flex flex-wrap items-center justify-between gap-2 px-3 py-2" key={v.name}>
                <span className="flex items-center gap-2 text-[13px] text-stone-800">
                  <FloodBandChip band={v.band as "low" | "moderate" | "high" | "severe"} /> {v.name}
                </span>
                <span className="text-[12.5px] tabular-nums text-stone-500">
                  {(v.probability * 100).toFixed(0)}% · ~{v.depth_m} m deep
                  {v.river_rise_m != null && ` · river +${v.river_rise_m} m*`}
                </span>
              </li>
            ))}
          </ul>
          {villages.some((v) => v.river_rise_m != null) && (
            <p className="mt-1 text-[11px] text-stone-400">* River rise is a modelled estimate, not a gauge reading.</p>
          )}
        </section>
      )}

      {deliveries.length > 0 && (
        <section>
          <h4 className="mb-2 text-[14px] font-semibold text-stone-900">Who was notified</h4>
          <ul className="space-y-1.5">
            {deliveries.map((d) => (
              <li className="flex items-center justify-between gap-2 text-[12.5px]" key={d.id} title={d.error ?? undefined}>
                <span className="min-w-0 truncate text-stone-700">
                  <span className="font-medium text-stone-900">{CHANNEL_LABEL[d.channel] ?? d.channel}</span>
                  {d.recipient_name !== "Dashboard" && <> → {d.recipient_name}</>}
                  {d.target && !["dashboard", "log"].includes(d.target) && <span className="text-stone-400"> ({d.target})</span>}
                </span>
                <span className={cn("shrink-0 rounded-full px-2 py-0.5 text-[11.5px] font-medium capitalize", DELIVERY_STYLE[d.status] ?? "")}>
                  {d.status}{d.attempts > 1 ? ` · ${d.attempts} tries` : ""}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <AlertLifecycle alert={alert} />

      <div className="flex flex-wrap items-center gap-2 border-t border-stone-100 pt-4">
        {alert.acknowledged_at ? (
          <span className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-50 px-3 py-2 text-[13px] font-medium text-emerald-800">
            <IconCheck size={15} /> Acknowledged by {alert.acknowledged_by ?? "operator"} · {formatRelative(alert.acknowledged_at)}
          </span>
        ) : status !== "resolved" ? (
          <Button disabled={ack.isPending} onClick={() => ack.mutate()} type="button">
            <IconCheck /> {ack.isPending ? "Acknowledging…" : "Acknowledge"}
          </Button>
        ) : null}
        <Button onClick={() => setExplainOpen(true)} type="button" variant="secondary">
          Full explanation
        </Button>
        <Button onClick={onAnalyze} type="button" variant="ghost">
          Open in Analysis
        </Button>
      </div>

      {explainOpen && <AlertExplanationDrawer alert={alert} onClose={() => setExplainOpen(false)} />}
    </div>
  );
}
