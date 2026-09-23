import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { getActiveAlerts, getRecentAlerts } from "../../api/alertsApi";
import { LayeredMap } from "../../components/map/LayeredMap";
import { Button } from "../../components/ui/Button";
import { FLOOD_BAND_COLOR, FloodBandChip } from "../../components/ui/FloodBandChip";
import { IconBell, IconCheck, IconSettings } from "../../components/ui/Icons";
import { fieldClass } from "../../components/ui/Input";
import { PageHeader, Panel } from "../../components/ui/Panel";
import { RiskTimeline } from "../../components/ui/RiskTimeline";
import { EmptyState, ErrorState, Skeleton } from "../../components/ui/States";
import { cn } from "../../lib/cn";
import { formatDateTime, formatRelative } from "../../lib/format";
import { useUiStore } from "../../store/uiStore";
import type { AlertResponse, FloodLevel } from "../../types/api";
import { AlertDetail } from "./AlertDetail";
import { useLiveFeed } from "./LiveAlertFeed";

type LevelFilter = FloodLevel | "all";
type Scope = "active" | "history";
const LEVEL_RANK: Record<string, number> = { severe: 3, high: 2, moderate: 1 };

function StatusCell({ alert }: { alert: AlertResponse }) {
  const status = alert.status ?? (alert.acknowledged_at ? "acknowledged" : "active");
  if (status === "resolved")
    return <span className="text-[12.5px] font-medium text-stone-500">Resolved{alert.resolved_by ? ` · ${alert.resolved_by}` : ""}</span>;
  if (status === "acknowledged")
    return <span className="inline-flex items-center gap-1 text-[12.5px] font-medium text-emerald-700"><IconCheck size={14} /> Acknowledged</span>;
  return <span className="text-[12.5px] font-medium text-amber-700">Awaiting response</span>;
}

export function AlertsPage() {
  const navigate = useNavigate();
  const applyAlert = useUiStore((s) => s.applyAlert);
  const selectedAlertId = useUiStore((s) => s.selectedAlertId);
  const setSelectedAlertId = useUiStore((s) => s.setSelectedAlertId);
  const liveConnected = useLiveFeed((s) => s.connected);

  const [scope, setScope] = useState<Scope>("active");
  const [level, setLevel] = useState<LevelFilter>("all");
  const [query, setQuery] = useState("");
  const [notifyPermission, setNotifyPermission] = useState<string>(
    typeof Notification === "undefined" ? "unsupported" : Notification.permission,
  );

  // The live SSE feed refreshes these queries; fall back to polling when it is down.
  const activeQuery = useQuery({ queryKey: ["alerts"], queryFn: getActiveAlerts, refetchInterval: liveConnected ? false : 30000 });
  const historyQuery = useQuery({
    queryKey: ["alerts-recent"],
    queryFn: () => getRecentAlerts(100),
    enabled: scope === "history",
    refetchInterval: liveConnected ? false : 60000,
  });
  const alertsQuery = scope === "active" ? activeQuery : historyQuery;
  const alerts = alertsQuery.data ?? [];

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return alerts
      .filter((a) => level === "all" || a.flood_level === level)
      .filter((a) => !q || a.region_name.toLowerCase().includes(q) || a.affected_villages?.some((v) => v.name.toLowerCase().includes(q)))
      .sort((a, b) =>
        scope === "history"
          ? new Date(b.issued_at).getTime() - new Date(a.issued_at).getTime()
          : (LEVEL_RANK[b.flood_level] ?? 0) - (LEVEL_RANK[a.flood_level] ?? 0) || b.probability - a.probability,
      );
  }, [alerts, level, query, scope]);

  // Default to the most serious visible alert so the detail panel is never blank.
  const selected = alerts.find((a) => a.id === selectedAlertId) ?? filtered[0] ?? null;
  const counts = (l: LevelFilter) => (l === "all" ? alerts.length : alerts.filter((a) => a.flood_level === l).length);

  return (
    <div className="space-y-6">
      <PageHeader
        actions={
          <>
            <span className="flex items-center gap-2 rounded-full border border-stone-200 bg-white px-3 py-1.5 text-[12.5px] text-stone-600">
              <span className={cn("h-2 w-2 rounded-full", liveConnected ? "bg-emerald-500" : "bg-stone-400")} />
              {liveConnected ? "Instant page updates on" : "Refreshing every 30 s"}
            </span>
            {notifyPermission === "default" && (
              <Button onClick={() => Notification.requestPermission().then(setNotifyPermission)} type="button" variant="secondary">
                <IconBell /> Enable desktop notifications
              </Button>
            )}
            <Link
              className="inline-flex items-center gap-1.5 rounded-lg border border-stone-300 bg-white px-3.5 py-2 text-[13.5px] font-medium text-stone-800 shadow-sm hover:bg-stone-50"
              to="/alerts/settings"
            >
              <IconSettings /> Recipients & channels
            </Link>
          </>
        }
        description="Alerts are automatically generated when the evaluated district risk crosses the configured threshold. Inputs are operator-provided, simulated or estimated (see each alert's data source). Each alert explains why, projects the next 48 hours, suggests actions and keeps a full audit trail."
        title="Flood alerts"
      />

      <div className="flex flex-wrap items-center gap-3">
        <div className="inline-flex rounded-lg border border-stone-200 bg-white p-1 shadow-sm">
          {(["active", "history"] as Scope[]).map((s) => (
            <button
              className={cn(
                "rounded-md px-3 py-1.5 text-[13px] font-medium transition-colors",
                scope === s ? "bg-stone-900 text-white" : "text-stone-600 hover:bg-stone-100",
              )}
              key={s}
              onClick={() => setScope(s)}
              type="button"
            >
              {s === "active" ? "Active" : "History (incl. resolved)"}
            </button>
          ))}
        </div>
        <div className="inline-flex max-w-full overflow-x-auto rounded-lg border border-stone-200 bg-white p-1 shadow-sm" role="tablist">
          {(["all", "severe", "high", "moderate"] as LevelFilter[]).map((l) => (
            <button
              aria-selected={level === l}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[13px] font-medium capitalize transition-colors",
                level === l ? "bg-brand-700 text-white" : "text-stone-600 hover:bg-stone-100",
              )}
              key={l}
              onClick={() => setLevel(l)}
              role="tab"
              type="button"
            >
              {l !== "all" && <span className="h-2 w-2 rounded-full" style={{ background: FLOOD_BAND_COLOR[l as FloodLevel] }} />}
              {l === "all" ? "All" : l}
              <span className={cn("rounded-full px-1.5 text-[11px]", level === l ? "bg-white/20" : "bg-stone-100 text-stone-500")}>{counts(l)}</span>
            </button>
          ))}
        </div>
        <input
          aria-label="Search district, region or village"
          className={cn(fieldClass, "max-w-xs py-1.5")}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search district, region or village…"
          value={query}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="min-w-0 space-y-4">
          {alertsQuery.isLoading && <Skeleton className="h-64" />}
          {alertsQuery.isError && (
            <ErrorState body={alertsQuery.error instanceof Error ? alertsQuery.error.message : "Request failed"} title="Alerts could not be loaded" />
          )}
          {alertsQuery.isSuccess && alerts.length === 0 && (
            <EmptyState
              action={<Link className="text-[13px] font-medium text-brand-700 hover:underline" to="/">Run the demo scenario from Overview →</Link>}
              body={scope === "active" ? "No evaluated district is above its alert threshold. Enter rainfall under Recipients & channels → Evaluate now, or run the demo scenario." : "No alerts have been issued yet."}
              icon={<IconBell />}
              title={scope === "active" ? "No active alerts" : "No alert history"}
            />
          )}
          {alerts.length > 0 && filtered.length === 0 && (
            <EmptyState body="Try a different level or search term." title="No alerts match these filters" />
          )}
          {filtered.length > 0 && (
            <div className="overflow-hidden rounded-xl border border-stone-200/80 bg-paper shadow-card">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[40rem] text-left text-[13.5px]">
                  <thead className="border-b border-stone-100 bg-stone-50/70 text-[12px] font-medium text-stone-500">
                    <tr>
                      <th className="px-4 py-3 font-medium">District</th>
                      <th className="px-4 py-3 font-medium">Level</th>
                      <th className="px-4 py-3 font-medium">Next 48 h</th>
                      <th className="px-4 py-3 font-medium">Issued</th>
                      <th className="px-4 py-3 font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-stone-100">
                    {filtered.map((alert) => (
                      <tr
                        className={cn("cursor-pointer transition-colors", selected?.id === alert.id ? "bg-brand-50/70" : "hover:bg-stone-50")}
                        key={alert.id}
                        onClick={() => setSelectedAlertId(alert.id)}
                      >
                        <td className="px-4 py-3">
                          <p className="font-semibold text-stone-900">{alert.district}</p>
                          <p className="text-[12px] text-stone-500">
                            {alert.region} · {(alert.probability * 100).toFixed(0)}%
                            {alert.source === "test" && <span className="ml-1.5 rounded bg-sky-50 px-1.5 py-0.5 text-[11px] font-medium text-sky-700">Test</span>}
                            {alert.source === "demo" && <span className="ml-1.5 rounded bg-violet-50 px-1.5 py-0.5 text-[11px] font-medium text-violet-700">Demo</span>}
                          </p>
                        </td>
                        <td className="px-4 py-3"><FloodBandChip band={alert.flood_level} /></td>
                        <td className="px-4 py-3">
                          {alert.timeline?.length ? <RiskTimeline compact points={alert.timeline} /> : <span className="text-[12px] text-stone-400">—</span>}
                        </td>
                        <td className="px-4 py-3 text-stone-600" title={formatDateTime(alert.issued_at)}>{formatRelative(alert.issued_at)}</td>
                        <td className="px-4 py-3"><StatusCell alert={alert} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          <LayeredMap
            alerts={filtered}
            className="min-h-[20rem]"
            onSelectAlert={(alert) => setSelectedAlertId(alert.id)}
            selectedAlertId={selected?.id ?? null}
          />
        </div>

        <div className="min-w-0">
          <Panel title="Alert details">
            {!selected ? (
              <p className="py-6 text-center text-[13.5px] text-stone-500">Select an alert in the list or on the map to see its details.</p>
            ) : (
              <AlertDetail
                alert={selected}
                key={selected.id}
                onAnalyze={() => {
                  applyAlert(selected);
                  navigate("/analysis");
                }}
              />
            )}
          </Panel>
        </div>
      </div>
    </div>
  );
}
