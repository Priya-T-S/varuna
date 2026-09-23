import type { FeatureAttribution } from "../../types/api";
import { featureLabel, featureUnit } from "../../lib/featureLabels";
import { formatNumber } from "../../lib/format";

export function ShapChart({ attributions }: { attributions: FeatureAttribution[] }) {
  const sorted = [...attributions].sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution));
  const max = Math.max(...sorted.map((a) => Math.abs(a.contribution)), 0.001);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between text-[11.5px] text-stone-500">
        <span className="flex items-center gap-1.5"><span className="h-2 w-2 rounded-full bg-info" /> Lowers risk</span>
        <span className="flex items-center gap-1.5">Raises risk <span className="h-2 w-2 rounded-full bg-risk-heavy" /></span>
      </div>
      {sorted.map((item) => {
        const width = (Math.abs(item.contribution) / max) * 50;
        const positive = item.contribution >= 0;
        const unit = featureUnit(item.feature);
        return (
          <div className="grid grid-cols-[minmax(8rem,0.42fr)_minmax(0,1fr)_4.5rem] items-center gap-3" key={item.feature}>
            <div className="min-w-0">
              <p className="truncate text-[13px] text-stone-800">{featureLabel(item.feature)}</p>
              <p className="text-[11.5px] tabular-nums text-stone-500">
                {item.value === null || item.value === undefined ? "value not shown" : `${formatNumber(item.value, 1)}${unit ? ` ${unit}` : ""}`}
              </p>
            </div>
            <div className="relative h-2.5 rounded-full bg-stone-100">
              <div className="absolute inset-y-[-3px] left-1/2 w-px bg-stone-300" />
              <div
                className={positive ? "absolute inset-y-0 rounded-r-full bg-risk-heavy" : "absolute inset-y-0 rounded-l-full bg-info"}
                style={{ width: `${width}%`, left: positive ? "50%" : `${50 - width}%` }}
              />
            </div>
            <p className={`text-right text-[12px] tabular-nums ${positive ? "text-risk-heavy" : "text-info"}`}>
              {positive ? "+" : "−"}
              {Math.abs(item.contribution).toFixed(3)}
            </p>
          </div>
        );
      })}
    </div>
  );
}
