import type { FloodBand } from "../../types/api";
import { cn } from "../../lib/cn";

export const FLOOD_BAND_COLOR: Record<FloodBand, string> = {
  low: "#3f7d56",
  moderate: "#b08a1f",
  high: "#c8612a",
  severe: "#b3342b",
};

export const FLOOD_BAND_LABEL: Record<FloodBand, string> = {
  low: "Low",
  moderate: "Moderate",
  high: "High",
  severe: "Severe",
};

const styles: Record<FloodBand, string> = {
  low: "bg-emerald-50 text-emerald-800 ring-emerald-600/20",
  moderate: "bg-amber-50 text-amber-800 ring-amber-600/20",
  high: "bg-orange-50 text-orange-800 ring-orange-600/20",
  severe: "bg-red-50 text-red-800 ring-red-600/25",
};

export function FloodBandChip({ band, className }: { band: FloodBand; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-0.5 text-[12px] font-medium ring-1 ring-inset",
        styles[band],
        className,
      )}
    >
      <span aria-hidden className="h-1.5 w-1.5 rounded-full" style={{ background: FLOOD_BAND_COLOR[band] }} />
      {FLOOD_BAND_LABEL[band]}
    </span>
  );
}
