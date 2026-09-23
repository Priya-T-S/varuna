import type { Antecedent, ScenarioRequest } from "../../types/api";
import { Button } from "../../components/ui/Button";
import { fieldClass, labelClass } from "../../components/ui/Input";
import { cn } from "../../lib/cn";

export const REGIONS = ["Kerala", "Mumbai", "Chennai", "Assam"] as const;

const MOISTURE: { value: Antecedent; label: string }[] = [
  { value: "dry", label: "Dry" },
  { value: "normal", label: "Normal" },
  { value: "saturated", label: "Saturated" },
];

export function ScenarioControls({
  value,
  onChange,
  onRun,
  running,
}: {
  value: ScenarioRequest;
  onChange: (next: ScenarioRequest) => void;
  onRun: () => void;
  running: boolean;
}) {
  const patch = (p: Partial<ScenarioRequest>) => onChange({ ...value, ...p });
  const useAbsolute = value.rainfall_mm !== null && value.rainfall_mm !== undefined;
  const pct = value.rainfall_change_pct ?? 0;

  return (
    <form
      className="space-y-4"
      onSubmit={(e) => {
        e.preventDefault();
        onRun();
      }}
    >
      <div>
        <span className={labelClass}>Region</span>
        <div className="mt-1.5 grid grid-cols-4 gap-1 rounded-lg bg-stone-100 p-1">
          {REGIONS.map((r) => (
            <button
              className={cn(
                "rounded-md py-1.5 text-[13px] font-medium transition-colors",
                value.region === r ? "bg-white text-brand-800 shadow-sm" : "text-stone-600 hover:text-stone-900",
              )}
              key={r}
              onClick={() => patch({ region: r, district: null })}
              type="button"
            >
              {r}
            </button>
          ))}
        </div>
      </div>

      <div>
        <div className="flex items-center justify-between">
          <span className={labelClass}>Rainfall</span>
          <div className="flex rounded-md bg-stone-100 p-0.5 text-[12px]">
            <button
              className={cn("rounded px-2 py-0.5", !useAbsolute ? "bg-white font-medium text-stone-900 shadow-sm" : "text-stone-500")}
              onClick={() => patch({ rainfall_mm: null })}
              type="button"
            >
              % change
            </button>
            <button
              className={cn("rounded px-2 py-0.5", useAbsolute ? "bg-white font-medium text-stone-900 shadow-sm" : "text-stone-500")}
              onClick={() => patch({ rainfall_mm: 300 })}
              type="button"
            >
              Total mm
            </button>
          </div>
        </div>
        {useAbsolute ? (
          <label className="mt-2 block">
            <span className="sr-only">Total rainfall (mm)</span>
            <input className={fieldClass} max={2000} min={1} onChange={(e) => patch({ rainfall_mm: Number(e.target.value) })} type="number" value={value.rainfall_mm ?? 300} />
            <span className="mt-1 block text-xs text-stone-500">Total over the whole spell</span>
          </label>
        ) : (
          <label className="mt-2 block">
            <span className="flex items-baseline justify-between">
              <span className="text-[12px] text-stone-500">vs a typical heavy monsoon spell</span>
              <span className={cn("text-[20px] font-semibold tabular-nums", pct > 0 ? "text-risk-heavy" : pct < 0 ? "text-brand-600" : "text-stone-800")}>
                {pct > 0 ? "+" : ""}{pct}%
              </span>
            </span>
            <input
              aria-label="Rainfall change percent"
              className="mt-1 w-full accent-brand-700"
              max={200}
              min={-60}
              onChange={(e) => patch({ rainfall_change_pct: Number(e.target.value) })}
              step={5}
              type="range"
              value={pct}
            />
            <span className="flex justify-between text-[11px] text-stone-400"><span>−60%</span><span>0</span><span>+200%</span></span>
          </label>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <label className="block">
          <span className={labelClass}>Duration (days)</span>
          <input className={cn(fieldClass, "mt-1.5")} max={10} min={1} onChange={(e) => patch({ duration_days: Number(e.target.value) })} type="number" value={value.duration_days ?? 3} />
        </label>
        <div>
          <span className={labelClass}>Soil before rain</span>
          <select
            aria-label="Soil moisture before the spell"
            className={cn(fieldClass, "mt-1.5")}
            onChange={(e) => patch({ antecedent: e.target.value as Antecedent })}
            value={value.antecedent ?? "normal"}
          >
            {MOISTURE.map((m) => <option key={m.value} value={m.value}>{m.label}</option>)}
          </select>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <Toggle checked={!!value.dam_release} label="Dam release" onChange={(v) => patch({ dam_release: v })} sub="Reservoirs open" />
        <Toggle checked={!!value.high_tide} label="High tide" onChange={(v) => patch({ high_tide: v })} sub="Coastal outfalls blocked" />
      </div>

      <Button className="w-full" disabled={running} type="submit">
        {running ? "Simulating…" : "Run simulation"}
      </Button>
    </form>
  );
}

function Toggle({ checked, label, sub, onChange }: { checked: boolean; label: string; sub: string; onChange: (v: boolean) => void }) {
  return (
    <label
      className={cn(
        "flex cursor-pointer items-start gap-2 rounded-lg border px-3 py-2 transition-colors",
        checked ? "border-brand-300 bg-brand-50" : "border-stone-200 bg-white hover:border-stone-300",
      )}
    >
      <input checked={checked} className="mt-0.5 accent-brand-700" onChange={(e) => onChange(e.target.checked)} type="checkbox" />
      <span>
        <span className="block text-[13px] font-medium text-stone-800">{label}</span>
        <span className="block text-[11.5px] text-stone-500">{sub}</span>
      </span>
    </label>
  );
}
