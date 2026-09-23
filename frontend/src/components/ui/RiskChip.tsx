import type { RiskLevel } from "../../types/api";
import { RISK_LABELS } from "../../lib/format";
import { cn } from "../../lib/cn";

const styles: Record<RiskLevel, { chip: string; dot: string }> = {
  low: { chip: "bg-emerald-50 text-emerald-800 ring-emerald-600/20", dot: "bg-risk-low" },
  moderate: { chip: "bg-amber-50 text-amber-800 ring-amber-600/20", dot: "bg-risk-moderate" },
  heavy: { chip: "bg-orange-50 text-orange-800 ring-orange-600/20", dot: "bg-risk-heavy" },
  extreme: { chip: "bg-red-50 text-red-800 ring-red-600/20", dot: "bg-risk-extreme" },
};

export function RiskChip({ level }: { level: RiskLevel }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[12px] font-medium ring-1 ring-inset", styles[level].chip)}>
      <span aria-hidden className={cn("h-1.5 w-1.5 rounded-full", styles[level].dot)} />
      {RISK_LABELS[level]}
    </span>
  );
}
