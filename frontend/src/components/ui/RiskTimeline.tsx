import type { CSSProperties } from "react";
import type { TimelinePoint } from "../../types/api";
import { cn } from "../../lib/cn";
import { FLOOD_BAND_COLOR, FLOOD_BAND_LABEL } from "./FloodBandChip";

const BG: Record<string, string> = {
  low: "bg-emerald-50 border-emerald-200",
  moderate: "bg-amber-50 border-amber-200",
  high: "bg-orange-50 border-orange-200",
  severe: "bg-red-50 border-red-200",
};

function when(p: TimelinePoint): string {
  return p.offset_h === 0 ? "Now" : `+${p.offset_h} h`;
}

/**
 * Now → +6h → +12h → +24h → +48h flood-risk projection. A trailing
 * `beyond_window` point marks the end of the rain spell when it falls later.
 */
export function RiskTimeline({
  points,
  compact = false,
  footnote = true,
  className,
}: {
  points: TimelinePoint[];
  compact?: boolean;
  footnote?: boolean;
  className?: string;
}) {
  if (!points.length) return null;
  const peak = points.reduce((best, p) => (p.probability > best.probability ? p : best), points[0]);

  if (compact) {
    return (
      <div aria-label="Risk timeline" className={cn("flex flex-wrap items-center gap-1 text-[11px]", className)}>
        {points.filter((p) => !p.beyond_window).map((p, i) => (
          <span className="flex items-center gap-1" key={p.offset_h}>
            {i > 0 && <span className="text-stone-300">→</span>}
            <span className="text-stone-400">{when(p)}</span>
            <span className="h-2 w-2 rounded-full" style={{ background: FLOOD_BAND_COLOR[p.band] }} title={FLOOD_BAND_LABEL[p.band]} />
          </span>
        ))}
      </div>
    );
  }

  return (
    <div className={className}>
      <ol aria-label="Risk timeline" className="flex items-stretch gap-1.5 overflow-x-auto pb-1 pt-2.5">
        {points.map((p, i) => {
          const isPeak = p === peak;
          return (
            <li className="flex min-w-[4.8rem] flex-1 items-center gap-1.5" key={`${p.offset_h}-${i}`}>
              <div
                className={cn(
                  "relative flex-1 rounded-lg border px-2 py-2 text-center",
                  BG[p.band],
                  p.beyond_window && "border-dashed opacity-80",
                  isPeak && "ring-2 ring-offset-1",
                )}
                style={isPeak ? ({ ["--tw-ring-color" as string]: FLOOD_BAND_COLOR[p.band] } as CSSProperties) : undefined}
              >
                {isPeak && (
                  <span className="absolute -top-2 left-1/2 -translate-x-1/2 rounded-full bg-stone-900 px-1.5 text-[9.5px] font-semibold uppercase tracking-wide text-white">
                    Peak
                  </span>
                )}
                <p className="text-[11px] text-stone-500">{p.beyond_window ? `+${p.offset_h} h · rain ends` : when(p)}</p>
                <p className="text-[13px] font-semibold" style={{ color: FLOOD_BAND_COLOR[p.band] }}>{FLOOD_BAND_LABEL[p.band]}</p>
                <p className="text-[11.5px] tabular-nums text-stone-600">{(p.probability * 100).toFixed(0)}%</p>
              </div>
              {i < points.length - 1 && <span aria-hidden className="text-stone-300">→</span>}
            </li>
          );
        })}
      </ol>
      {footnote && (
        <p className="mt-1.5 text-[11.5px] leading-5 text-stone-500">
          Hydrological projection from the rainfall scenario. The AI rain probability itself covers the next 24 h.
        </p>
      )}
    </div>
  );
}
