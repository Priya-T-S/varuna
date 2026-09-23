import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { addAlertNote, changeAlertSeverity, resolveAlert, reviewAlert } from "../../api/alertsApi";
import { Button } from "../../components/ui/Button";
import { IconCheck } from "../../components/ui/Icons";
import { fieldClass } from "../../components/ui/Input";
import { cn } from "../../lib/cn";
import { formatDateTime, formatRelative } from "../../lib/format";
import { operatorOrDefault, useOperator } from "../../lib/operator";
import type { AlertEvent, AlertResponse, FloodLevel } from "../../types/api";

const STEPS: { stage: string; label: string }[] = [
  { stage: "detected", label: "Detected" },
  { stage: "generated", label: "Generated" },
  { stage: "reviewed", label: "Reviewed" },
  { stage: "sent", label: "Sent" },
  { stage: "acknowledged", label: "Acknowledged" },
  { stage: "resolved", label: "Resolved" },
];

const STAGE_LABEL: Record<string, string> = {
  detected: "Detected",
  generated: "Generated",
  reviewed: "Reviewed",
  sent: "Sent",
  acknowledged: "Acknowledged",
  severity_changed: "Severity changed",
  note: "Note",
  resolved: "Resolved",
};

const STAGE_DOT: Record<string, string> = {
  severity_changed: "bg-orange-500",
  note: "bg-stone-400",
  resolved: "bg-emerald-600",
  acknowledged: "bg-emerald-500",
};

type Panel = null | "review" | "severity" | "resolve" | "note";

/** Detected → Generated → Reviewed → Sent → Acknowledged → Resolved, with the full audit log. */
export function AlertLifecycle({ alert }: { alert: AlertResponse }) {
  const events = alert.events ?? [];
  const first = (stage: string): AlertEvent | undefined => events.find((e) => e.stage === stage);
  const resolved = alert.status === "resolved";

  return (
    <section>
      <h4 className="text-[14px] font-semibold text-stone-900">Lifecycle & audit trail</h4>
      <ol className="mt-3 grid grid-cols-3 gap-y-3 sm:grid-cols-6">
        {STEPS.map((step, i) => {
          const ev = first(step.stage);
          return (
            <li className="relative flex flex-col items-center text-center" key={step.stage}>
              {i > 0 && (
                <span
                  aria-hidden
                  className={cn("absolute right-1/2 top-3 h-0.5 w-full -translate-y-1/2", ev ? "bg-brand-500" : "bg-stone-200")}
                />
              )}
              <span
                className={cn(
                  "relative z-10 grid h-6 w-6 place-items-center rounded-full border-2 text-[11px] font-semibold",
                  ev ? "border-brand-600 bg-brand-600 text-white" : "border-stone-300 bg-white text-stone-400",
                )}
              >
                {ev ? <IconCheck size={12} /> : i + 1}
              </span>
              <span className={cn("mt-1 text-[11.5px] font-medium", ev ? "text-stone-900" : "text-stone-400")}>{step.label}</span>
              <span className="text-[10.5px] text-stone-400" title={ev ? formatDateTime(ev.at) : undefined}>
                {ev ? formatRelative(ev.at) : "pending"}
              </span>
            </li>
          );
        })}
      </ol>

      {!resolved && <LifecycleActions alert={alert} />}

      <ul className="mt-4 space-y-0">
        {[...events].reverse().map((e) => (
          <li className="relative flex gap-3 pb-3 pl-1" key={e.id}>
            <span className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", STAGE_DOT[e.stage] ?? "bg-brand-500")} />
            <div className="min-w-0">
              <p className="text-[12.5px] text-stone-500">
                <span className="font-semibold text-stone-800">{STAGE_LABEL[e.stage] ?? e.stage}</span>
                {" · "}
                <span title={formatDateTime(e.at)}>{formatDateTime(e.at)}</span>
                {" · "}
                <span className="text-stone-600">{e.actor}</span>
              </p>
              <p className="text-[13px] leading-5 text-stone-700">{e.detail}</p>
            </div>
          </li>
        ))}
        {events.length === 0 && (
          <li className="text-[12.5px] text-stone-500">No audit events recorded (this alert was created before auditing was enabled).</li>
        )}
      </ul>
    </section>
  );
}

function LifecycleActions({ alert }: { alert: AlertResponse }) {
  const queryClient = useQueryClient();
  const { name, setName } = useOperator();
  const [panel, setPanel] = useState<Panel>(null);
  const [text, setText] = useState("");
  const [level, setLevel] = useState<FloodLevel>(alert.flood_level);
  const by = operatorOrDefault(name);

  const act = useMutation({
    mutationFn: async () => {
      if (panel === "review") return reviewAlert(alert.id, by, text);
      if (panel === "severity") return changeAlertSeverity(alert.id, by, level, text);
      if (panel === "resolve") return resolveAlert(alert.id, by, text);
      return addAlertNote(alert.id, by, text);
    },
    onSuccess: () => {
      setPanel(null);
      setText("");
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
      queryClient.invalidateQueries({ queryKey: ["alerts-recent"] });
    },
  });

  const needsText = panel === "severity" || panel === "note";
  return (
    <div className="mt-4 rounded-lg border border-stone-200 bg-stone-50/70 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-1.5 text-[12.5px] text-stone-600">
          Acting as
          <input
            aria-label="Your name for the audit trail"
            className="w-44 rounded-md border border-stone-300 bg-white px-2 py-1 text-[12.5px] outline-none focus:border-brand-500"
            onChange={(e) => setName(e.target.value)}
            placeholder="Your name / role"
            value={name}
          />
        </label>
        <span className="flex-1" />
        {(["review", "severity", "note", "resolve"] as Panel[]).map((p) => (
          <Button
            key={p}
            onClick={() => setPanel(panel === p ? null : p)}
            size="sm"
            type="button"
            variant={p === "resolve" ? "primary" : "secondary"}
          >
            {{ review: "Mark reviewed", severity: "Change severity", note: "Add note", resolve: "Resolve" }[p!]}
          </Button>
        ))}
      </div>
      {panel && (
        <form
          className="mt-3 flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            act.mutate();
          }}
        >
          {panel === "severity" && (
            <select
              aria-label="New severity"
              className={cn(fieldClass, "w-auto py-1.5")}
              onChange={(e) => setLevel(e.target.value as FloodLevel)}
              value={level}
            >
              <option value="moderate">Moderate</option>
              <option value="high">High</option>
              <option value="severe">Severe</option>
            </select>
          )}
          <input
            aria-label="Details"
            className={cn(fieldClass, "min-w-[14rem] flex-1 py-1.5")}
            onChange={(e) => setText(e.target.value)}
            placeholder={{
              review: "Optional note, e.g. verified with Tahsildar",
              severity: "Reason (required), e.g. river gauge confirms rise",
              resolve: "Optional note, e.g. water receding, all clear",
              note: "Note, e.g. shelters opened at Chengannur",
            }[panel]}
            required={needsText}
            value={text}
          />
          <Button disabled={act.isPending || (needsText && text.trim().length < 3)} size="sm" type="submit">
            {act.isPending ? "Saving…" : "Save"}
          </Button>
        </form>
      )}
      {act.isError && <p className="mt-2 text-[12px] text-red-700">{(act.error as Error).message}</p>}
    </div>
  );
}
