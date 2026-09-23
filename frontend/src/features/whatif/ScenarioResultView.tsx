import { useEffect, useState, type ReactNode } from "react";
import type { IncidentMatch, ScenarioResult, VillageImpact } from "../../types/api";
import { FloodBandChip } from "../../components/ui/FloodBandChip";
import { IconAlertTriangle, IconBook, IconBrain, IconDrop, IconMapPin, IconUsers } from "../../components/ui/Icons";
import { Panel } from "../../components/ui/Panel";
import { ProvenanceList } from "../../components/ui/ProvenanceList";
import { RiskTimeline } from "../../components/ui/RiskTimeline";
import { cn } from "../../lib/cn";
import { formatRelative, horizonText } from "../../lib/format";
import { RecommendedActions } from "../alerts/RecommendedActions";
import { ShapChart } from "../explainability/ShapChart";
import { VillageRiskMap } from "./VillageRiskMap";

const pct = (v: number) => `${(v * 100).toFixed(0)}%`;

export function ScenarioResultView({ result }: { result: ScenarioResult }) {
  const [selectedId, setSelectedId] = useState<string | null>(result.villages[0]?.id ?? null);
  useEffect(() => setSelectedId(result.villages[0]?.id ?? null), [result]);
  const selected = result.villages.find((v) => v.id === selectedId) ?? null;
  const { summary } = result;
  const change = result.scenario_rain.change_pct;

  return (
    <div className="space-y-4">
      <section className="overflow-hidden rounded-xl border border-brand-200 bg-gradient-to-br from-brand-800 to-brand-600 text-white shadow-card">
        <div className="px-5 py-4">
          <p className="text-[12px] font-medium uppercase tracking-[0.12em] text-brand-100">What-if result · {result.region}</p>
          <p className="mt-1.5 text-[18px] font-semibold leading-snug">{summary.headline}</p>
        </div>
        <dl className="grid grid-cols-2 gap-px bg-white/10 sm:grid-cols-4">
          <HeroStat
            icon={<IconDrop size={15} />}
            label="Rainfall"
            sub={`${change >= 0 ? "+" : ""}${change.toFixed(0)}% vs ${result.baseline_rain.event_total_mm.toFixed(0)} mm · ${result.scenario_rain.duration_days} days`}
            value={`${result.scenario_rain.event_total_mm.toFixed(0)} mm`}
          />
          <HeroStat
            icon={<IconMapPin size={15} />}
            label="High or severe"
            sub={summary.newly_at_risk ? `${summary.newly_at_risk} newly at risk` : "no new places"}
            value={`${summary.villages_high_or_severe} of ${summary.villages_assessed}`}
          />
          <HeroStat
            icon={<IconUsers size={15} />}
            label="People exposed"
            sub={summary.districts_at_risk.slice(0, 3).join(", ") || "—"}
            value={summary.population_at_risk.toLocaleString("en-IN")}
          />
          <HeroStat
            icon={<IconBrain size={15} />}
            label="AI heavy-rain chance"
            sub={
              result.baseline_model && result.model_delta !== null
                ? `was ${pct(result.baseline_model.probability)} (${result.model_delta >= 0 ? "+" : ""}${(result.model_delta * 100).toFixed(1)} pts)`
                : "model unavailable"
            }
            value={result.scenario_model ? pct(result.scenario_model.probability) : "n/a"}
          />
        </dl>
        <p className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-white/15 bg-brand-900/30 px-5 py-2.5 text-[12px] text-brand-100">
          <span>Highest village risk <b className="text-white">{pct(Math.max(...result.villages.map((v) => v.flood_probability), 0))}</b></span>
          <span aria-hidden>·</span>
          <span>Model confidence <b className="text-white">{result.scenario_model?.confidence_label ?? "n/a"}</b></span>
          <span aria-hidden>·</span>
          <span>{horizonText(result.timeline, result.scenario_model?.horizon_hours ?? 24)}</span>
          <span aria-hidden>·</span>
          <span>Simulated scenario{result.generated_at ? `, run ${formatRelative(result.generated_at)}` : ""}</span>
        </p>
      </section>

      {result.timeline && result.timeline.length > 0 && (
        <Panel description="Worst-affected location at each step (hydrological projection)" title="Risk timeline">
          <RiskTimeline points={result.timeline} />
        </Panel>
      )}

      <div className="grid gap-4 2xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
        <VillageRiskMap className="min-h-[24rem]" onSelect={(v) => setSelectedId(v.id)} selectedId={selectedId} villages={result.villages} />
        <Panel description="How much each factor adds to this village's flood risk" title="Why this village?">
          {selected ? <VillageFactors village={selected} /> : <p className="text-sm text-stone-500">Select a village on the map or in the table.</p>}
        </Panel>
      </div>

      <Panel bodyClassName="p-0" description="Sorted by flood probability under this scenario. Click a row to see why." title="Villages & wards">
        <div className="scroll-quiet max-h-[26rem] overflow-auto">
          <table className="w-full min-w-[38rem] text-left text-[13.5px]">
            <thead className="sticky top-0 z-10 bg-stone-50 text-[12px] text-stone-500">
              <tr>
                <th className="px-4 py-2.5 font-medium">Village / ward</th>
                <th className="px-4 py-2.5 font-medium">Risk: before → after</th>
                <th className="px-4 py-2.5 text-right font-medium">Probability</th>
                <th className="px-4 py-2.5 text-right font-medium">Water depth</th>
                <th className="px-4 py-2.5 text-right font-medium">People</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {result.villages.map((v) => (
                <tr
                  className={cn("cursor-pointer transition-colors", v.id === selectedId ? "bg-brand-50/70" : "hover:bg-stone-50")}
                  key={v.id}
                  onClick={() => setSelectedId(v.id)}
                >
                  <td className="px-4 py-2.5">
                    <p className="font-medium text-stone-900">
                      {v.name}
                      {v.landslide_risk && (
                        <span className="ml-2 inline-flex items-center gap-1 rounded-full bg-red-50 px-1.5 py-0.5 text-[11px] font-medium text-red-700">
                          <IconAlertTriangle size={11} /> Landslide
                        </span>
                      )}
                    </p>
                    <p className="text-[12px] text-stone-500">{v.district}</p>
                  </td>
                  <td className="px-4 py-2.5">
                    <span className="inline-flex items-center gap-1.5">
                      <FloodBandChip band={v.baseline_band} className="opacity-60" />
                      <span className="text-stone-400">→</span>
                      <FloodBandChip band={v.band} />
                      {v.band_increased && <span className="text-[11px] font-semibold text-risk-extreme">▲</span>}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right tabular-nums text-stone-500">
                    {pct(v.baseline_probability)} → <b className="text-stone-900">{pct(v.flood_probability)}</b>
                  </td>
                  <td className="px-4 py-2.5 text-right tabular-nums text-stone-700">{v.expected_depth_m ? `~${v.expected_depth_m} m` : "—"}</td>
                  <td className="px-4 py-2.5 text-right tabular-nums text-stone-700">{v.population.toLocaleString("en-IN")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel
          description="How much each weather input pushed the AI's heavy-rain forecast up (orange) or down (blue) compared with the baseline"
          icon={<IconBrain />}
          title="What changed in the AI's view"
        >
          {result.driver_changes.length ? (
            <ShapChart
              attributions={result.driver_changes.map((d) => ({ feature: d.feature, value: d.scenario_value, contribution: d.delta }))}
            />
          ) : (
            <p className="text-sm text-stone-500">The AI explanation isn't available for this run.</p>
          )}
        </Panel>
        <Panel description="Documented disasters most similar to this scenario" icon={<IconBook />} title="Has this happened before?">
          <div className="space-y-3">
            {result.similar_incidents.map((i) => <IncidentCard incident={i} key={i.id} />)}
            {result.model_analogues.length > 0 && (
              <p className="pt-1 text-[12px] leading-5 text-stone-500">
                Closest rain days in the AI's training record:{" "}
                {result.model_analogues.map((a) => `${a.region} ${a.date} (${a.observed_rainfall_mm.toFixed(0)} mm)`).join(" · ")}
              </p>
            )}
          </div>
        </Panel>
      </div>

      {result.actions && result.actions.length > 0 && (
        <Panel
          description="Decision support for the responsible officer, not automatic commands"
          title="If this happened: suggested actions"
        >
          <RecommendedActions actions={result.actions} hideTitle readOnly />
        </Panel>
      )}

      {result.provenance && result.provenance.length > 0 && (
        <Panel description="Which component produced each part of this result" title="How this was computed">
          <ProvenanceList hideTitle items={result.provenance} />
        </Panel>
      )}

      <details className="group rounded-xl border border-stone-200/80 bg-paper px-5 py-3 shadow-card">
        <summary className="cursor-pointer list-none text-[13.5px] font-semibold text-stone-800">
          <span className="inline-block transition-transform group-open:rotate-90">›</span> Assumptions & limitations
        </summary>
        <ul className="mt-3 list-disc space-y-1.5 pl-5 text-[13px] leading-6 text-stone-600">
          {[...result.assumptions, ...result.caveats].map((line) => <li key={line}>{line}</li>)}
        </ul>
      </details>
    </div>
  );
}

function HeroStat({ label, value, sub, icon }: { label: string; value: string; sub?: string; icon: ReactNode }) {
  return (
    <div className="bg-brand-900/20 px-5 py-3.5">
      <dt className="flex items-center gap-1.5 text-[12px] text-brand-100">{icon}{label}</dt>
      <dd className="mt-1 text-[22px] font-semibold tabular-nums leading-none">{value}</dd>
      {sub && <dd className="mt-1.5 truncate text-[12px] text-brand-100/90" title={sub}>{sub}</dd>}
    </div>
  );
}

function VillageFactors({ village }: { village: VillageImpact }) {
  const max = Math.max(...village.factors.map((f) => Math.abs(f.contribution)), 0.01);
  return (
    <div className="space-y-4 text-sm">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-[16px] font-semibold text-stone-900">{village.name}</span>
          <FloodBandChip band={village.band} />
          {village.landslide_risk && <span className="rounded-full bg-red-50 px-2 py-0.5 text-[11.5px] font-medium text-red-700">Landslide risk</span>}
        </div>
        <p className="mt-1 text-[12.5px] text-stone-500">
          {village.district} · {pct(village.flood_probability)} flood probability · {village.runoff_mm.toFixed(0)} mm runoff
          {village.expected_depth_m ? ` · about ${village.expected_depth_m} m of water` : ""}
          {village.river_rise_m ? ` · river +${village.river_rise_m} m (modelled)` : ""}
        </p>
      </div>
      {village.timeline && village.timeline.length > 0 && <RiskTimeline footnote={false} points={village.timeline} />}
      <div className="space-y-2">
        {village.factors.map((f) => (
          <div className="grid grid-cols-[9rem_minmax(0,1fr)_2.8rem] items-center gap-3" key={f.factor} title={f.detail}>
            <span className="truncate text-[13px] text-stone-700">{f.label}</span>
            <div className="h-2 overflow-hidden rounded-full bg-stone-100">
              <div
                className="h-full rounded-full bg-gradient-to-r from-risk-moderate to-risk-heavy"
                style={{ width: `${(Math.abs(f.contribution) / max) * 100}%`, opacity: f.contribution > 0 ? 1 : 0.25 }}
              />
            </div>
            <span className="text-right text-[12px] tabular-nums text-stone-500">+{f.contribution.toFixed(1)}</span>
          </div>
        ))}
      </div>
      {village.reasons.length > 0 && (
        <div className="rounded-lg bg-stone-50 p-3">
          <p className="mb-1.5 text-[12.5px] font-semibold text-stone-700">In plain words</p>
          <ul className="list-disc space-y-1 pl-5 text-[13px] leading-6 text-stone-700">
            {village.reasons.map((r) => <li key={r}>{r}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}

export function IncidentCard({ incident }: { incident: IncidentMatch }) {
  return (
    <article className="rounded-lg border border-stone-200 bg-white p-4 transition-colors hover:border-brand-200">
      <div className="flex items-start justify-between gap-3">
        <h4 className="text-[14px] font-semibold leading-snug text-stone-900">{incident.name}</h4>
        <span className="shrink-0 rounded-full bg-stone-100 px-2 py-0.5 text-[11.5px] font-medium text-stone-600">{incident.date.slice(0, 4)}</span>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5 text-[11.5px]">
        <span className="rounded-full bg-brand-50 px-2 py-0.5 text-brand-800">{incident.rainfall_mm} mm / {incident.rainfall_window_days} d</span>
        {incident.deaths ? <span className="rounded-full bg-red-50 px-2 py-0.5 text-red-800">~{incident.deaths.toLocaleString("en-IN")} deaths</span> : null}
        {incident.displaced ? <span className="rounded-full bg-amber-50 px-2 py-0.5 text-amber-800">~{incident.displaced.toLocaleString("en-IN")} displaced</span> : null}
      </div>
      <p className="mt-2 text-[13px] leading-6 text-stone-700">{incident.summary}</p>
      {incident.why_similar && incident.why_similar.length > 0 && (
        <p className="mt-2 text-[12.5px] leading-5 text-brand-700">
          <span className="font-medium">Why it's similar:</span> {incident.why_similar.join("; ")}
        </p>
      )}
      <p className="mt-1.5 text-[11px] text-stone-400">Source: {incident.source}</p>
    </article>
  );
}
