import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useUiStore } from "../../store/uiStore";
import { Button, buttonClass } from "../../components/ui/Button";
import { IconHistory, IconTarget } from "../../components/ui/Icons";
import { fieldClass } from "../../components/ui/Input";
import { PageHeader } from "../../components/ui/Panel";
import { EmptyState } from "../../components/ui/States";
import { RiskChip } from "../../components/ui/RiskChip";
import { SimulatedBanner } from "../../components/ui/SimulatedBanner";
import { cn } from "../../lib/cn";
import { formatDateTime, formatProbability } from "../../lib/format";
import type { RiskLevel } from "../../types/api";

export function HistoryPage() {
  const history = useUiStore((s) => s.history);
  const setActiveAnalysis = useUiStore((s) => s.setActiveAnalysis);
  const navigate = useNavigate();

  const [risk, setRisk] = useState<RiskLevel | "all">("all");
  const [region, setRegion] = useState("");

  const filtered = useMemo(() => {
    const q = region.trim().toLowerCase();
    return history.filter((item) => {
      if (risk !== "all" && item.response.risk_level !== risk) return false;
      if (q && !(item.response.region_name ?? "").toLowerCase().includes(q)) return false;
      return true;
    });
  }, [history, region, risk]);

  return (
    <div className="space-y-6">
      <PageHeader
        description="Forecasts you've run on this device. Reopen any of them to see the full explanation again."
        eyebrow="Your work"
        title="Forecast history"
      />

      {history.length === 0 ? (
        <EmptyState
          action={<Link className={buttonClass("primary")} to="/analysis"><IconTarget /> Run your first forecast</Link>}
          body="Every forecast you run in Analysis is saved here on this device, so you can come back to it later."
          className="bg-white py-16"
          icon={<IconHistory size={20} />}
          title="No forecasts yet"
        />
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <select
              aria-label="Filter by risk level"
              className={cn(fieldClass, "w-auto py-1.5")}
              onChange={(e) => setRisk(e.target.value as RiskLevel | "all")}
              value={risk}
            >
              <option value="all">All risk levels</option>
              <option value="low">Low</option>
              <option value="moderate">Moderate</option>
              <option value="heavy">Heavy</option>
              <option value="extreme">Extreme</option>
            </select>
            <input
              aria-label="Search by place"
              className={cn(fieldClass, "max-w-xs py-1.5")}
              onChange={(e) => setRegion(e.target.value)}
              placeholder="Search by place…"
              value={region}
            />
            <span className="text-[12.5px] text-stone-500">{filtered.length} of {history.length} forecasts</span>
          </div>

          {filtered.length === 0 ? (
            <EmptyState body="Try a different risk level or search term." title="No forecasts match" />
          ) : (
            <div className="overflow-hidden rounded-xl border border-stone-200/80 bg-paper shadow-card">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[40rem] text-left text-[13.5px]">
                  <thead className="border-b border-stone-100 bg-stone-50/70 text-[12px] text-stone-500">
                    <tr>
                      <th className="px-5 py-3 font-medium">Place</th>
                      <th className="px-4 py-3 font-medium">Risk</th>
                      <th className="px-4 py-3 font-medium">Heavy-rain chance</th>
                      <th className="px-4 py-3 font-medium">Run on</th>
                      <th className="px-4 py-3 font-medium">Source</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-stone-100">
                    {filtered.map((item) => (
                      <tr className="transition-colors hover:bg-stone-50" key={item.id}>
                        <td className="px-5 py-3 font-medium text-stone-900">{item.response.region_name || "Unnamed point"}</td>
                        <td className="px-4 py-3"><RiskChip level={item.response.risk_level} /></td>
                        <td className="px-4 py-3 tabular-nums text-stone-800">{formatProbability(item.response.probability)}</td>
                        <td className="px-4 py-3 text-stone-600">{formatDateTime(item.stored_at)}</td>
                        <td className="px-4 py-3">
                          {item.simulated ? (
                            <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[11.5px] font-medium text-amber-800">Simulated</span>
                          ) : (
                            <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11.5px] font-medium text-emerald-800">AI model</span>
                          )}
                        </td>
                        <td className="px-4 py-2.5 text-right">
                          <Button
                            onClick={() => {
                              setActiveAnalysis({ request: item.request, response: item.response, simulated: item.simulated });
                              navigate("/explainability");
                            }}
                            size="sm"
                            type="button"
                            variant="secondary"
                          >
                            View explanation
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          {filtered.some((item) => item.simulated) && <SimulatedBanner compact />}
        </>
      )}
    </div>
  );
}
