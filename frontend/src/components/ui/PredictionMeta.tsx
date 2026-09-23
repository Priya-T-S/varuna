import type { ReactNode } from "react";
import type { ConfidenceLabel, DataMode } from "../../types/api";
import { formatDateTime, formatRelative } from "../../lib/format";
import { cn } from "../../lib/cn";

export const DATA_MODE_LABEL: Record<string, string> = {
  observed: "Operator input",
  climatology: "Climatology",
  demo: "Demo data",
  scenario: "Scenario",
  test: "Test",
  entered: "Entered by you",
};

const MODE_STYLE: Record<string, string> = {
  observed: "bg-emerald-50 text-emerald-800 ring-emerald-600/20",
  entered: "bg-emerald-50 text-emerald-800 ring-emerald-600/20",
  climatology: "bg-stone-100 text-stone-600 ring-stone-400/30",
  demo: "bg-violet-50 text-violet-800 ring-violet-600/20",
  scenario: "bg-violet-50 text-violet-800 ring-violet-600/20",
  test: "bg-sky-50 text-sky-800 ring-sky-600/20",
};

const CONFIDENCE_STYLE: Record<ConfidenceLabel, string> = {
  High: "text-emerald-700",
  Medium: "text-amber-700",
  Low: "text-red-700",
};

export function DataModeBadge({ mode, className }: { mode?: string | null; className?: string }) {
  if (!mode) return null;
  return (
    <span className={cn("inline-flex rounded-full px-1.5 py-0.5 text-[10.5px] font-medium ring-1 ring-inset", MODE_STYLE[mode] ?? MODE_STYLE.climatology, className)}>
      {DATA_MODE_LABEL[mode] ?? mode}
    </span>
  );
}

/**
 * The four facts every prediction must carry: how likely, how sure, how fresh,
 * and for what time window. A probability without a horizon is meaningless.
 */
export function PredictionMeta({
  probability,
  probabilityLabel = "Flood probability",
  confidenceLabel,
  confidencePct,
  dataAsOf,
  dataMode,
  horizon,
  compact = false,
  className,
}: {
  probability: number;
  probabilityLabel?: string;
  confidenceLabel?: ConfidenceLabel | null;
  confidencePct?: number | null;
  dataAsOf?: string | null;
  dataMode?: DataMode | "entered" | null;
  horizon: string;
  compact?: boolean;
  className?: string;
}) {
  const conf = confidenceLabel ?? null;
  if (compact) {
    return (
      <p className={cn("flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px] text-stone-500", className)}>
        <span><b className="font-semibold text-stone-800">{(probability * 100).toFixed(0)}%</b> {probabilityLabel.toLowerCase()}</span>
        <span aria-hidden>·</span>
        <span>{horizon}</span>
        {conf && (<><span aria-hidden>·</span><span>confidence <b className={CONFIDENCE_STYLE[conf]}>{conf}</b></span></>)}
        {dataAsOf && (<><span aria-hidden>·</span><span>data {formatRelative(dataAsOf)}</span></>)}
        <DataModeBadge mode={dataMode} />
      </p>
    );
  }
  return (
    <dl className={cn("grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-stone-200 bg-stone-200 sm:grid-cols-4", className)}>
      <Cell label={probabilityLabel}>
        <span className="text-[22px] font-semibold tabular-nums text-stone-900">{(probability * 100).toFixed(0)}%</span>
      </Cell>
      <Cell label="Model confidence" sub={confidencePct != null ? `${confidencePct.toFixed(0)}% score` : "AI rainfall model"}>
        {conf ? (
          <span className={cn("text-[18px] font-semibold", CONFIDENCE_STYLE[conf])}>{conf}</span>
        ) : (
          <span className="text-[15px] text-stone-400">Not available</span>
        )}
      </Cell>
      <Cell
        label="Last data update"
        sub={dataAsOf ? formatDateTime(dataAsOf) : undefined}
        title={dataAsOf ? formatDateTime(dataAsOf) : undefined}
      >
        <span className="flex flex-wrap items-center gap-1.5">
          <span className="text-[15px] font-semibold text-stone-900">{dataAsOf ? formatRelative(dataAsOf) : "Unknown"}</span>
          <DataModeBadge mode={dataMode} />
        </span>
      </Cell>
      <Cell label="Forecast horizon">
        <span className="text-[15px] font-semibold text-stone-900">{horizon}</span>
      </Cell>
    </dl>
  );
}

function Cell({ label, sub, title, children }: { label: string; sub?: string; title?: string; children: ReactNode }) {
  return (
    <div className="bg-white px-3.5 py-2.5" title={title}>
      <dt className="text-[11.5px] text-stone-500">{label}</dt>
      <dd className="mt-0.5">{children}</dd>
      {sub && <dd className="mt-0.5 text-[11px] text-stone-400">{sub}</dd>}
    </div>
  );
}
