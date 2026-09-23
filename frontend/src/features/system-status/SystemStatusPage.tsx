import type { ReactNode } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { getDataSources, getSystemStatus, setFault } from "../../api/systemApi";
import { IconActivity, IconAlertTriangle, IconBell, IconCpu, IconDrop } from "../../components/ui/Icons";
import { PageHeader, Panel } from "../../components/ui/Panel";
import { ErrorState, Skeleton } from "../../components/ui/States";
import { cn } from "../../lib/cn";
import { formatRelative } from "../../lib/format";
import { useLiveFeed } from "../alerts/LiveAlertFeed";
import { useUiStore } from "../../store/uiStore";
import type { SimulatorMode } from "../../store/uiStore";
import type { DataSource, FaultComponent, SystemComponent } from "../../types/api";

type Tone = "ok" | "warn" | "down" | "info";

const STATE_TONE: Record<string, Tone> = {
  online: "ok", ok: "ok", observed: "ok", running: "ok",
  demo: "info", scenario: "info", simulated: "info", climatology: "warn", limited: "warn", starting: "warn",
  delayed: "warn", degraded: "warn", none: "warn", disabled: "warn",
  unavailable: "down", error: "down",
};

const MODE_BADGE: Record<DataSource["mode"], { label: string; cls: string; desc: string }> = {
  live: { label: "Live", cls: "bg-emerald-50 text-emerald-800 ring-emerald-600/20", desc: "Streamed automatically from a real-time feed" },
  manual: { label: "Manual", cls: "bg-emerald-50 text-emerald-800 ring-emerald-600/20", desc: "Real figures entered by an operator" },
  cached: { label: "Cached", cls: "bg-sky-50 text-sky-800 ring-sky-600/20", desc: "Last real value, kept while the feed is down" },
  historical: { label: "Historical", cls: "bg-stone-100 text-stone-700 ring-stone-400/30", desc: "Past observations (training data, records, normals)" },
  static: { label: "Static", cls: "bg-stone-100 text-stone-700 ring-stone-400/30", desc: "Fixed reference data" },
  modelled: { label: "Modelled", cls: "bg-amber-50 text-amber-800 ring-amber-600/20", desc: "Derived by a model from other inputs" },
  simulated: { label: "Simulated", cls: "bg-violet-50 text-violet-800 ring-violet-600/20", desc: "Estimated in place of a real measurement" },
  demo: { label: "Demo", cls: "bg-violet-50 text-violet-800 ring-violet-600/20", desc: "Preset scenario for demonstrations" },
  unavailable: { label: "Unavailable", cls: "bg-red-50 text-red-800 ring-red-600/20", desc: "Nothing received" },
};

const FAULTS: { key: FaultComponent; label: string; desc: string }[] = [
  { key: "rainfall_feed", label: "Rainfall feed goes stale", desc: "Latest observation appears 47 minutes old" },
  { key: "ai_model", label: "AI model unavailable", desc: "Flood risk falls back to a rainfall-only proxy" },
  { key: "notifications", label: "Notification provider down", desc: "Telegram / e-mail / SMS / WhatsApp deliveries fail" },
];

export function SystemStatusPage() {
  const queryClient = useQueryClient();
  const status = useQuery({ queryKey: ["system-status"], queryFn: getSystemStatus, refetchInterval: 15000 });
  const sources = useQuery({ queryKey: ["data-sources"], queryFn: getDataSources, refetchInterval: 30000 });
  const liveConnected = useLiveFeed((s) => s.connected);
  const simulatorMode = useUiStore((s) => s.simulatorMode);
  const setSimulatorMode = useUiStore((s) => s.setSimulatorMode);

  const fault = useMutation({
    mutationFn: ({ key, enabled }: { key: FaultComponent; enabled: boolean }) => setFault(key, enabled),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["system-status"] });
      queryClient.invalidateQueries({ queryKey: ["data-sources"] });
      queryClient.invalidateQueries({ queryKey: ["current-risk"] });
    },
  });

  const c = status.data?.components;

  return (
    <div className="space-y-6">
      <PageHeader description="Whether every part of VARUNA AI is working, and exactly which data is live, modelled or simulated." eyebrow="Health" title="System status" />

      {status.isError && <ErrorState body="The backend can't be reached. Cached pages stay visible." title="Server offline" />}
      {status.isLoading && <Skeleton className="h-28" />}
      {c && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
          <Tile component={c.ai_model} icon={<IconCpu />} label="AI model" />
          <Tile component={c.weather_data} icon={<IconDrop />} label="Weather / rainfall data" />
          <Tile component={c.river_data} icon={<IconActivity />} label="River data" />
          <Tile component={c.notifications} icon={<IconBell />} label="Notifications" />
          <Tile
            component={{ ...c.monitor, detail: c.monitor.last_run ? `Last run ${formatRelative(c.monitor.last_run)}. ${c.monitor.detail}` : c.monitor.detail }}
            icon={<IconActivity />}
            label="Automatic monitor"
          />
        </div>
      )}
      <p className="-mt-3 text-[12.5px] text-stone-500">
        Live alert feed: <b className={liveConnected ? "text-emerald-700" : "text-amber-700"}>{liveConnected ? "connected" : "reconnecting"}</b>
      </p>

      <Panel description="Every input VARUNA AI uses, where it comes from, and whether it is real, derived or simulated" title="Data sources">
        {sources.isLoading && <Skeleton className="h-40" />}
        {sources.data && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[44rem] text-left text-[13.5px]">
              <thead className="text-[12px] text-stone-500">
                <tr>
                  <th className="pb-2 font-medium">Input</th>
                  <th className="pb-2 font-medium">Source</th>
                  <th className="pb-2 font-medium">Type</th>
                  <th className="pb-2 font-medium">Last update</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100">
                {sources.data.map((s) => (
                  <tr key={s.input}>
                    <td className="py-2.5 pr-3 align-top font-medium text-stone-900">{s.input}</td>
                    <td className="py-2.5 pr-3 align-top">
                      <p className="text-stone-700">{s.source}</p>
                      <p className="text-[12px] text-stone-500">{s.note}</p>
                    </td>
                    <td className="py-2.5 pr-3 align-top">
                      <span className={cn("inline-flex rounded-full px-2 py-0.5 text-[11.5px] font-medium ring-1 ring-inset", MODE_BADGE[s.mode]?.cls)}>
                        {MODE_BADGE[s.mode]?.label ?? s.mode}
                      </span>
                    </td>
                    <td className="py-2.5 align-top text-[12.5px] text-stone-600">{s.last_update ? formatRelative(s.last_update) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="mt-4 flex flex-wrap gap-x-4 gap-y-1.5 border-t border-stone-100 pt-3 text-[12px] text-stone-500">
          {(["live", "manual", "historical", "modelled", "simulated", "demo"] as DataSource["mode"][]).map((m) => (
            <span className="flex items-center gap-1.5" key={m}>
              <span className={cn("rounded-full px-1.5 py-0.5 text-[10.5px] font-medium ring-1 ring-inset", MODE_BADGE[m].cls)}>{MODE_BADGE[m].label}</span>
              {MODE_BADGE[m].desc}
            </span>
          ))}
        </div>
      </Panel>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel
          description="Demo tool: switch on a failure to show how VARUNA AI warns operators and degrades gracefully. Turn it off afterwards."
          icon={<IconAlertTriangle />}
          title="Simulate a failure"
        >
          <ul className="space-y-2">
            {FAULTS.map((f) => {
              const enabled = status.data?.faults[f.key] ?? false;
              return (
                <li className={cn("flex items-center justify-between gap-3 rounded-lg border px-3 py-2.5", enabled ? "border-amber-300 bg-amber-50" : "border-stone-200")} key={f.key}>
                  <span>
                    <span className="block text-[13.5px] font-medium text-stone-900">{f.label}</span>
                    <span className="block text-[12px] text-stone-500">{f.desc}</span>
                  </span>
                  <button
                    aria-checked={enabled}
                    aria-label={f.label}
                    className={cn("relative h-6 w-11 shrink-0 rounded-full transition-colors", enabled ? "bg-amber-500" : "bg-stone-300")}
                    disabled={fault.isPending}
                    onClick={() => fault.mutate({ key: f.key, enabled: !enabled })}
                    role="switch"
                    type="button"
                  >
                    <span className={cn("absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all", enabled ? "left-[1.375rem]" : "left-0.5")} />
                  </button>
                </li>
              );
            })}
          </ul>
          <p className="mt-3 text-[12px] text-stone-500">
            Connection loss is detected automatically: disconnect the network to see the offline banner.
          </p>
        </Panel>

        <Panel description="What the Analysis page does when the AI model isn't available" title="Simulator fallback">
          <fieldset className="space-y-2">
            <legend className="sr-only">Simulator mode</legend>
            {(
              [
                ["auto", "Automatic (recommended)", "Use the AI model. If it's unavailable, show a clearly labelled simulated result."],
                ["forced", "Always simulate", "Never call the AI model. Useful for demos and training."],
                ["off", "Never simulate", "Show an error if the AI model is unavailable."],
              ] as Array<[SimulatorMode, string, string]>
            ).map(([value, label, desc]) => (
              <label
                className={cn(
                  "flex cursor-pointer gap-3 rounded-lg border p-3 transition-colors",
                  simulatorMode === value ? "border-brand-400 bg-brand-50" : "border-stone-200 bg-white hover:border-stone-300",
                )}
                key={value}
              >
                <input checked={simulatorMode === value} className="mt-1 accent-brand-700" name="simulatorMode" onChange={() => setSimulatorMode(value)} type="radio" value={value} />
                <span>
                  <span className="block text-[13.5px] font-semibold text-stone-900">{label}</span>
                  <span className="mt-0.5 block text-[12.5px] leading-5 text-stone-500">{desc}</span>
                </span>
              </label>
            ))}
          </fieldset>
          <p className="mt-3 text-[12.5px] text-stone-500">
            Model accuracy and limitations: <Link className="font-medium text-brand-700 hover:underline" to="/model">Model performance →</Link>
          </p>
        </Panel>
      </div>
    </div>
  );
}

function Tile({ label, component, icon }: { label: string; component: SystemComponent; icon: ReactNode }) {
  const tone = STATE_TONE[component.state] ?? "warn";
  return (
    <div className="rounded-xl border border-stone-200/80 bg-paper p-4 shadow-card">
      <div className="flex items-center justify-between">
        <span className="text-[12.5px] font-medium text-stone-500">{label}</span>
        <span
          className={cn(
            "grid h-8 w-8 place-items-center rounded-lg",
            tone === "ok" && "bg-emerald-50 text-emerald-700",
            tone === "warn" && "bg-amber-50 text-amber-700",
            tone === "down" && "bg-red-50 text-red-700",
            tone === "info" && "bg-violet-50 text-violet-700",
          )}
        >
          {icon}
        </span>
      </div>
      <p className="mt-1.5 flex items-center gap-2 text-[18px] font-semibold text-stone-900">
        <span
          className={cn(
            "h-2.5 w-2.5 rounded-full",
            tone === "ok" ? "bg-emerald-500" : tone === "warn" ? "bg-amber-500" : tone === "info" ? "bg-violet-500" : "bg-red-600",
          )}
        />
        {component.label}
      </p>
      <p className="mt-1.5 text-[12.5px] leading-snug text-stone-500">{component.detail}</p>
    </div>
  );
}
