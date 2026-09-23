import { useEffect } from "react";
import { createPortal } from "react-dom";
import type { AlertResponse } from "../../types/api";
import { FloodBandChip } from "../../components/ui/FloodBandChip";
import { IconX } from "../../components/ui/Icons";
import { RiskTimeline } from "../../components/ui/RiskTimeline";
import { ShapChart } from "../explainability/ShapChart";
import { WhyThisAlert } from "./WhyThisAlert";

/** Full explanation for one alert: reasons, AI feature contributions, per-village factors, projection. */
export function AlertExplanationDrawer({ alert, onClose }: { alert: AlertResponse; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Portal to <body>: the page's fade-in transform would otherwise trap position:fixed.
  return createPortal(
    <div aria-modal className="fixed inset-0 z-[1300] flex justify-end" role="dialog">
      <button aria-label="Close explanation" className="absolute inset-0 bg-stone-900/30 backdrop-blur-[1px]" onClick={onClose} type="button" />
      <aside className="relative h-full w-full max-w-xl animate-fade-up overflow-y-auto bg-white shadow-2xl">
        <header className="sticky top-0 z-10 flex items-start justify-between gap-3 border-b border-stone-100 bg-white px-5 py-4">
          <div>
            <p className="text-[12px] font-medium uppercase tracking-[0.12em] text-brand-600">Full explanation</p>
            <h3 className="mt-0.5 text-[17px] font-semibold text-stone-900">{alert.district}, {alert.region}</h3>
          </div>
          <button aria-label="Close" className="rounded-lg p-1.5 text-stone-500 hover:bg-stone-100" onClick={onClose} type="button">
            <IconX size={18} />
          </button>
        </header>
        <div className="space-y-6 px-5 py-5">
          <WhyThisAlert alert={alert} />

          {alert.timeline && alert.timeline.length > 0 && (
            <section>
              <h4 className="mb-2 text-[14px] font-semibold text-stone-900">How the risk evolves</h4>
              <RiskTimeline points={alert.timeline} />
            </section>
          )}

          <section>
            <h4 className="text-[14px] font-semibold text-stone-900">What the AI rainfall model weighed (SHAP)</h4>
            <p className="mb-3 mt-0.5 text-[12.5px] text-stone-500">
              Contribution of each input to the fusion model's heavy-rain probability ({alert.rain_probability != null ? `${(alert.rain_probability * 100).toFixed(0)}%` : "n/a"} for the next {alert.horizon_hours ?? 24} h).
            </p>
            {alert.model_drivers && alert.model_drivers.length > 0 ? (
              <ShapChart attributions={alert.model_drivers.map((d) => ({ feature: d.feature, value: d.value, contribution: d.contribution }))} />
            ) : (
              <p className="text-[13px] text-stone-500">No SHAP breakdown was stored for this alert (the AI model may have been unavailable).</p>
            )}
          </section>

          <section>
            <h4 className="mb-2 text-[14px] font-semibold text-stone-900">Village-level factors</h4>
            <ul className="space-y-3">
              {(alert.affected_villages ?? []).map((v) => (
                <li className="rounded-lg border border-stone-200 p-3" key={v.name}>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[14px] font-medium text-stone-900">{v.name}</span>
                    <FloodBandChip band={v.band as "low" | "moderate" | "high" | "severe"} />
                    <span className="text-[12px] text-stone-500">
                      {(v.probability * 100).toFixed(0)}% · ~{v.depth_m} m water
                      {v.river_rise_m != null ? ` · river +${v.river_rise_m} m (modelled)` : ""}
                    </span>
                  </div>
                  <ul className="mt-1.5 list-disc space-y-0.5 pl-5 text-[12.5px] leading-5 text-stone-600">
                    {v.reasons.map((r) => <li key={r}>{r}</li>)}
                  </ul>
                </li>
              ))}
            </ul>
          </section>

          {alert.similar_incident && (
            <section className="rounded-lg border-l-4 border-brand-400 bg-brand-50/60 px-4 py-3">
              <h4 className="text-[13px] font-semibold text-brand-800">Similar past incident</h4>
              <p className="mt-0.5 text-[13.5px] font-medium text-stone-900">{alert.similar_incident.name}</p>
              <p className="mt-1 text-[12.5px] leading-5 text-stone-600">{alert.similar_incident.summary}</p>
            </section>
          )}

          <p className="border-t border-stone-100 pt-4 text-[11.5px] leading-5 text-stone-500">
            Flood probabilities come from a runoff + terrain model on curated village data. River rise is a modelled
            estimate, not a gauge reading. The AI model predicts next-day heavy rain and was trained on 2004–2024
            region-days. Use this as decision support alongside field reports.
          </p>
        </div>
      </aside>
    </div>,
    document.body,
  );
}
