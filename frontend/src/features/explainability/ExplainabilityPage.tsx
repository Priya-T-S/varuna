import { useState } from "react";
import { Link } from "react-router-dom";
import { buttonClass } from "../../components/ui/Button";
import { IconBrain, IconTarget } from "../../components/ui/Icons";
import { PageHeader, Panel } from "../../components/ui/Panel";
import { ProvenanceList } from "../../components/ui/ProvenanceList";
import { RiskChip } from "../../components/ui/RiskChip";
import { SimulatedBanner } from "../../components/ui/SimulatedBanner";
import { EmptyState } from "../../components/ui/States";
import { formatDateTime, formatProbability } from "../../lib/format";
import { useUiStore } from "../../store/uiStore";
import { ShapChart } from "./ShapChart";

const pctOrDash = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${(v * 100).toFixed(0)}%`);

export function ExplainabilityPage() {
  const active = useUiStore((s) => s.activeAnalysis);
  const [showOverlay, setShowOverlay] = useState(true);

  if (!active) {
    return (
      <div className="space-y-6">
        <PageHeader
          description="See exactly why the AI made a forecast: which inputs pushed the risk up or down, what the satellite model looked at, and similar days from the past."
          eyebrow="Explainable AI"
          title="Why did the AI say that?"
        />
        <EmptyState
          action={
            <>
              <Link className={buttonClass("primary")} to="/analysis"><IconTarget /> Run a forecast</Link>
              <Link className={buttonClass("secondary")} to="/history">Open a past forecast</Link>
            </>
          }
          body="Run a forecast in Analysis, or reopen one from History, and its full explanation will appear here."
          className="bg-white py-16"
          icon={<IconBrain size={20} />}
          title="No forecast selected yet"
        />
      </div>
    );
  }

  const explanation = active.response.explanation ?? null;
  const attributions = explanation?.feature_attributions ?? [];
  const image = explanation?.image_explanation ?? null;
  const narrative = explanation?.narrative ?? "";
  const historical = explanation?.historical_explanation ?? null;
  const confidenceExp = explanation?.confidence_explanation ?? null;
  const caveats = explanation?.caveats ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        actions={<Link className={buttonClass("secondary")} to="/analysis">Back to Analysis</Link>}
        description={`Forecast for ${active.response.region_name || "the selected point"}, generated ${formatDateTime(active.response.generated_at)}.`}
        eyebrow="Explainable AI"
        title="Why did the AI say that?"
      />
      {active.simulated && <SimulatedBanner />}

      <div className="grid gap-4 sm:grid-cols-3">
        <div className="rounded-xl border border-stone-200/80 bg-paper p-4 shadow-card">
          <p className="text-[12.5px] text-stone-500">Risk level</p>
          <div className="mt-2"><RiskChip level={active.response.risk_level} /></div>
        </div>
        <div className="rounded-xl border border-stone-200/80 bg-paper p-4 shadow-card">
          <p className="text-[12.5px] text-stone-500">Chance of heavy rain</p>
          <p className="mt-1 text-[26px] font-semibold tabular-nums">{formatProbability(active.response.probability)}</p>
        </div>
        <div className="rounded-xl border border-stone-200/80 bg-paper p-4 shadow-card">
          <p className="text-[12.5px] text-stone-500">Model confidence</p>
          <p className="mt-1 text-[26px] font-semibold tabular-nums">{formatProbability(active.response.confidence)}</p>
        </div>
      </div>

      {narrative.trim() && (
        <section className="rounded-xl border-l-4 border-brand-500 bg-brand-50/70 px-5 py-4">
          <p className="text-[12.5px] font-semibold text-brand-800">In plain words</p>
          <p className="mt-1 max-w-4xl text-[14.5px] leading-7 text-stone-800">{narrative}</p>
        </section>
      )}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
        <Panel
          description="Each bar shows how much one input pushed the forecast up (orange) or down (blue). These are SHAP values."
          icon={<IconBrain />}
          title="SHAP feature attributions"
        >
          {attributions.length === 0 ? (
            <EmptyState body="This forecast came back without a feature breakdown." title="Breakdown unavailable" />
          ) : (
            <ShapChart attributions={attributions} />
          )}
        </Panel>

        <div className="space-y-4">
          {confidenceExp && (
            <Panel description="What the confidence score is made of" title="How sure is the model?">
              <dl className="grid grid-cols-2 gap-3">
                {[
                  ["Overall", `${confidenceExp.confidence_pct}%`, confidenceExp.confidence],
                  ["Weather vs satellite agree", pctOrDash(confidenceExp.factors.model_agreement), "branch agreement"],
                  ["Matches past days", pctOrDash(confidenceExp.factors.historical_similarity), "closest analogue"],
                  ["Input completeness", `${(confidenceExp.factors.data_quality_score * 100).toFixed(0)}%`, "fields supplied"],
                ].map(([label, value, sub]) => (
                  <div className="rounded-lg bg-stone-50 p-3" key={label}>
                    <dt className="text-[12px] text-stone-500">{label}</dt>
                    <dd className="mt-0.5 text-[20px] font-semibold tabular-nums text-stone-900">{value}</dd>
                    <dd className="text-[11.5px] text-stone-500">{sub}</dd>
                  </div>
                ))}
              </dl>
            </Panel>
          )}

          <Panel
            actions={
              image ? (
                <label className="flex items-center gap-2 text-[12.5px] text-stone-600">
                  <input checked={showOverlay} className="accent-brand-700" onChange={(e) => setShowOverlay(e.target.checked)} type="checkbox" />
                  Show heatmap
                </label>
              ) : null
            }
            description="Which parts of the satellite image the model focused on"
            title="Satellite heatmap"
          >
            {!image ? (
              <p className="text-[13px] leading-6 text-stone-500">
                No satellite image was part of this forecast. Upload one on the{" "}
                <Link className="font-medium text-brand-700 hover:underline" to="/analysis">Analysis</Link> page to see a heatmap.
              </p>
            ) : (
              <div className="space-y-3">
                <div className="overflow-hidden rounded-lg border border-stone-200 bg-stone-900">
                  {showOverlay ? (
                    <img alt="Grad-CAM heatmap" className="block w-full" src={image.heatmap_url} />
                  ) : (
                    <div className="flex aspect-square items-center justify-center bg-stone-100 px-6 text-center text-sm text-stone-600">
                      The original image isn't stored with the forecast. Turn the heatmap back on.
                    </div>
                  )}
                </div>
                <div className="flex h-2 overflow-hidden rounded-full">
                  <div className="flex-1 bg-[#2a6f8f]" />
                  <div className="flex-1 bg-[#c8612a]" />
                  <div className="flex-1 bg-[#b3342b]" />
                </div>
                <div className="flex justify-between text-[11.5px] text-stone-500"><span>Less attention</span><span>More attention</span></div>
                <p className="text-[13px] leading-6 text-stone-700">{image.description}</p>
              </div>
            )}
          </Panel>
        </div>
      </div>

      {explanation?.provenance && explanation.provenance.length > 0 && (
        <Panel title="Model provenance">
          <ProvenanceList items={explanation.provenance} />
        </Panel>
      )}

      <Panel description="Real past days the model finds most similar to this one" title="Similar days in the record">
        {!historical || !historical.matches || historical.matches.length === 0 ? (
          <p className="text-[13px] text-stone-500">No similar past days were found for this forecast.</p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {historical.matches.map((match, idx) => (
              <div className="rounded-lg border border-stone-200 bg-white p-4" key={idx}>
                <div className="flex items-center justify-between gap-2">
                  <p className="text-[14px] font-semibold text-stone-900">{match.region}</p>
                  <span className="rounded-full bg-brand-50 px-2 py-0.5 text-[12px] font-medium text-brand-700">{match.similarity_pct.toFixed(0)}% similar</span>
                </div>
                <p className="mt-1 text-[13px] text-stone-600">{match.date} · {match.observed_rainfall_mm} mm observed</p>
                <p className="mt-1 text-[12.5px] text-stone-500">{match.event}</p>
              </div>
            ))}
          </div>
        )}
      </Panel>

      {caveats.length > 0 && (
        <details className="group rounded-xl border border-amber-200 bg-amber-50/60 px-5 py-3">
          <summary className="cursor-pointer list-none text-[13.5px] font-semibold text-amber-900">
            <span className="inline-block transition-transform group-open:rotate-90">›</span> Limitations to keep in mind
          </summary>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-[13px] leading-6 text-amber-900">
            {caveats.map((c, i) => <li key={i}>{c}</li>)}
          </ul>
        </details>
      )}
    </div>
  );
}
