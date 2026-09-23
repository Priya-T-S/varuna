import { useMutation, useQueryClient } from "@tanstack/react-query";
import { addAlertNote } from "../../api/alertsApi";
import { IconCheck } from "../../components/ui/Icons";
import { cn } from "../../lib/cn";
import { operatorOrDefault, useOperator } from "../../lib/operator";
import type { AlertResponse, RecommendedAction } from "../../types/api";

const DONE_PREFIX = "Action completed: ";

const PRIORITY_STYLE: Record<string, string> = {
  immediate: "bg-red-50 text-red-700",
  "within 3 h": "bg-orange-50 text-orange-700",
  "within 6 h": "bg-amber-50 text-amber-700",
  continuous: "bg-sky-50 text-sky-700",
  scheduled: "bg-stone-100 text-stone-600",
};

/**
 * Suggested next steps. Decision support only: ticking one records who did
 * what in the alert's audit trail, it never triggers anything by itself.
 */
export function RecommendedActions({
  actions,
  alert,
  readOnly = false,
  hideTitle = false,
}: {
  actions: RecommendedAction[];
  alert?: AlertResponse;
  readOnly?: boolean;
  hideTitle?: boolean;
}) {
  const operator = useOperator((s) => s.name);
  const queryClient = useQueryClient();
  const done = new Set(
    (alert?.events ?? []).filter((e) => e.stage === "note" && e.detail.startsWith(DONE_PREFIX)).map((e) => e.detail.slice(DONE_PREFIX.length)),
  );
  const mark = useMutation({
    mutationFn: (text: string) => addAlertNote(alert!.id, operatorOrDefault(operator), `${DONE_PREFIX}${text}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alerts"] }),
  });

  if (!actions.length) return null;
  return (
    <section>
      {!hideTitle && (
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h4 className="text-[14px] font-semibold text-stone-900">Recommended actions</h4>
          <span className="text-[11.5px] text-stone-500">Decision support for the responsible officer, not automatic commands</span>
        </div>
      )}
      <ul className={cn("divide-y divide-stone-100 rounded-lg border border-stone-200 bg-white", !hideTitle && "mt-2")}>
        {actions.map((a) => {
          const isDone = done.has(a.text);
          const interactive = !readOnly && !!alert && !isDone;
          return (
            <li className="flex items-start gap-3 px-3 py-2.5" key={a.text}>
              <button
                aria-label={isDone ? `Done: ${a.text}` : `Mark done: ${a.text}`}
                className={cn(
                  "mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded border transition-colors",
                  isDone ? "border-emerald-600 bg-emerald-600 text-white" : "border-stone-300 bg-white",
                  interactive ? "hover:border-brand-500" : "cursor-default",
                )}
                disabled={!interactive || mark.isPending}
                onClick={() => mark.mutate(a.text)}
                type="button"
              >
                {isDone && <IconCheck size={13} />}
              </button>
              <span className="min-w-0 flex-1">
                <span className={cn("block text-[13.5px] leading-snug", isDone ? "text-stone-400 line-through" : "text-stone-800")}>{a.text}</span>
                <span className="mt-0.5 block text-[11.5px] text-stone-500">{a.owner}</span>
              </span>
              <span className={cn("shrink-0 rounded-full px-2 py-0.5 text-[11px] font-medium", PRIORITY_STYLE[a.priority] ?? "bg-stone-100 text-stone-600")}>
                {a.priority}
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
