import type { ProvenanceItem } from "../../types/api";
import { cn } from "../../lib/cn";

export const KIND_LABEL: Record<string, { label: string; cls: string }> = {
  trained: { label: "Trained ML model", cls: "bg-brand-50 text-brand-800 ring-brand-600/20" },
  tuned: { label: "Weighted average (1 tuned weight)", cls: "bg-sky-50 text-sky-800 ring-sky-600/20" },
  algorithmic: { label: "Explanation algorithm", cls: "bg-stone-100 text-stone-700 ring-stone-400/30" },
  "rule-based": { label: "Rule-based (not ML)", cls: "bg-amber-50 text-amber-800 ring-amber-600/20" },
  llm: { label: "Language model", cls: "bg-violet-50 text-violet-800 ring-violet-600/20" },
};

const STATUS: Record<string, { label: string; cls: string; dot: string }> = {
  ran: { label: "Ran", cls: "text-emerald-700", dot: "bg-emerald-500" },
  estimated: { label: "Estimated", cls: "text-amber-700", dot: "bg-amber-500" },
  not_run: { label: "Did not run", cls: "text-red-700", dot: "bg-red-500" },
};

/**
 * "How this was computed": which AI or rule component produced each part of a
 * result and whether it actually ran, so estimated or rule-based steps are never
 * mistaken for trained-model output.
 */
export function ProvenanceList({
  items,
  compact = false,
  hideTitle = false,
}: {
  items?: ProvenanceItem[] | null;
  compact?: boolean;
  hideTitle?: boolean;
}) {
  if (!items?.length) return null;
  if (compact) {
    return (
      <div className="flex flex-wrap gap-1.5">
        {items.map((p) => {
          const s = STATUS[p.status] ?? STATUS.ran;
          return (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-stone-200 bg-white px-2 py-0.5 text-[11.5px] text-stone-700" key={p.component} title={p.detail}>
              <span className={cn("h-1.5 w-1.5 rounded-full", s.dot)} />
              {p.component}: <b className={s.cls}>{s.label}</b>
            </span>
          );
        })}
      </div>
    );
  }
  return (
    <section>
      {!hideTitle && <h4 className="text-[14px] font-semibold text-stone-900">How this was computed</h4>}
      <ul className={cn("divide-y divide-stone-100 rounded-lg border border-stone-200 bg-white", !hideTitle && "mt-2")}>
        {items.map((p) => {
          const s = STATUS[p.status] ?? STATUS.ran;
          const k = KIND_LABEL[p.kind] ?? { label: p.kind, cls: "bg-stone-100 text-stone-700 ring-stone-400/30" };
          return (
            <li className="flex flex-wrap items-start gap-x-3 gap-y-1 px-3 py-2.5" key={p.component}>
              <span className="flex min-w-[10rem] items-center gap-2 text-[13px] font-medium text-stone-900">
                <span className={cn("h-2 w-2 shrink-0 rounded-full", s.dot)} />
                {p.component}
              </span>
              <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset", k.cls)}>{k.label}</span>
              <span className={cn("text-[12px] font-semibold", s.cls)}>{s.label}</span>
              <span className="w-full text-[12.5px] leading-5 text-stone-600">{p.detail}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
