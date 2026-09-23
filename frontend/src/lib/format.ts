import type { RiskLevel } from "../types/api";

export const RISK_LABELS: Record<RiskLevel, string> = {
  low: "Low",
  moderate: "Moderate",
  heavy: "Heavy",
  extreme: "Extreme",
};

export function formatCoordinate(value: number, digits = 4): string {
  return value.toFixed(digits);
}

export function formatProbability(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Kolkata",
  }).format(date);
}

/** Horizon line for an alert: the AI window plus when the flood projection peaks. */
export function horizonText(timeline?: { offset_h: number; probability: number }[] | null, hours = 24): string {
  if (!timeline?.length) return `Next ${hours} hours`;
  const peak = timeline.reduce((b, p) => (p.probability > b.probability ? p : b), timeline[0]);
  return peak.offset_h === 0 ? `Next ${hours} h · peak now` : `Next ${hours} h · peak +${peak.offset_h} h`;
}

/** "just now", "12 min ago", "3 h ago", else a date. */
export function formatRelative(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return iso;
  const seconds = Math.round((Date.now() - then) / 1000);
  if (seconds < 45) return "just now";
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)} h ago`;
  return formatDateTime(iso);
}

export function formatNumber(value: number | null | undefined, digits = 1, unit?: string): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const text = value.toFixed(digits);
  return unit ? `${text} ${unit}` : text;
}
