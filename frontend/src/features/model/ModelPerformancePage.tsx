import { useQuery } from "@tanstack/react-query";
import { getModelPerformance } from "../../api/systemApi";
import { IconAlertTriangle } from "../../components/ui/Icons";
import { PageHeader, Panel, StatCard } from "../../components/ui/Panel";
import { KIND_LABEL } from "../../components/ui/ProvenanceList";
import { ErrorState, Skeleton } from "../../components/ui/States";
import { cn } from "../../lib/cn";
import type { ClassMetrics, ModelPerformance } from "../../types/api";

const pct = (v: number | null | undefined, digits = 0) => (v == null ? "—" : `${(v * 100).toFixed(digits)}%`);

/** Honest evaluation page: leads with how well heavy-rain days are caught, not with accuracy. */
export function ModelPerformancePage() {
  const q = useQuery({ queryKey: ["model-performance"], queryFn: getModelPerformance, staleTime: Infinity });

  return (
    <div className="space-y-6">
      <PageHeader
        description="What each AI component is, how the pipeline fits together, and how well the rainfall model performed on data it never saw. For early warning the key questions are how many heavy-rain days it catches and how often it cries wolf, not overall accuracy."
        eyebrow="Transparency"
        title="Models & performance"
      />
      {q.isLoading && <Skeleton className="h-64" />}
      {q.isError && <ErrorState body={(q.error as Error).message} title="Evaluation report unavailable" />}
      {q.data && <Report data={q.data} />}
    </div>
  );
}

function Box({ title, sub, kind }: { title: string; sub: string; kind: string }) {
  const k = KIND_LABEL[kind];
  return (
    <div className={cn("rounded-lg border bg-white px-3 py-2 text-center shadow-sm", kind === "rule-based" ? "border-amber-300" : "border-stone-200")}>
      <p className="text-[13px] font-semibold text-stone-900">{title}</p>
      <p className="text-[11.5px] text-stone-500">{sub}</p>
      {k && <span className={cn("mt-1 inline-block rounded-full px-1.5 py-0.5 text-[10px] font-medium ring-1 ring-inset", k.cls)}>{k.label}</span>}
    </div>
  );
}

const Arrow = () => <div aria-hidden className="mx-auto h-4 w-px bg-stone-300" />;

/** Hybrid AI decision-support pipeline, as it actually runs. */
function ArchitectureDiagram() {
  return (
    <div className="mx-auto max-w-3xl">
      <div className="grid grid-cols-2 gap-4">
        <Box kind="trained" sub="Random Forest · weather + rainfall" title="Weather model" />
        <div>
          <Box kind="trained" sub="CNN (PyTorch) · satellite image" title="Satellite model" />
          <div className="mt-2 grid grid-cols-2 gap-2 text-center text-[11px]">
            <span className="rounded-md bg-emerald-50 px-1.5 py-1 text-emerald-800">Image uploaded → real CNN</span>
            <span className="rounded-md bg-amber-50 px-1.5 py-1 text-amber-800">No image → estimated from cloud &amp; humidity</span>
          </div>
        </div>
      </div>
      <Arrow />
      <Box kind="tuned" sub="0.85 × weather + 0.15 × satellite → heavy-rain probability (next 24 h)" title="Fusion" />
      <Arrow />
      <div className="grid grid-cols-2 gap-4">
        <Box kind="algorithmic" sub="Why the probability is what it is" title="SHAP explanation" />
        <Box kind="algorithmic" sub="Most similar recorded days" title="Historical comparison" />
      </div>
      <Arrow />
      <Box kind="rule-based" sub="SCS runoff + terrain + drainage on supplied rainfall" title="Village flood risk" />
      <Arrow />
      <div className="grid grid-cols-3 gap-3">
        <Box kind="" sub="Now → +48 h projection" title="64 villages & timeline" />
        <Box kind="" sub="Threshold → alert + audit trail" title="Alerts" />
        <Box kind="" sub="Telegram · e-mail · SMS · WhatsApp · dashboard" title="Notifications" />
      </div>
      <p className="mt-4 text-center text-[12px] text-stone-500">
        Inputs (rainfall, weather, river level) are operator-provided, simulated or estimated in this prototype. No live feed is connected.
      </p>
    </div>
  );
}

function Report({ data }: { data: ModelPerformance }) {
  const wm = data.warning_metrics.test;
  const test = data.test;
  const ds = data.dataset;

  return (
    <>
      <Panel description="Hybrid AI decision support: trained models for rainfall, a rule-based layer for flood impact" title="Architecture">
        <ArchitectureDiagram />
      </Panel>

      {data.components && (
        <Panel bodyClassName="p-0" description="Exactly what each part is and when it runs" title="AI components">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[52rem] text-left text-[13px]">
              <thead className="bg-stone-50 text-[12px] text-stone-500">
                <tr>
                  <th className="px-5 py-2.5 font-medium">Component</th>
                  <th className="px-3 py-2.5 font-medium">What it is</th>
                  <th className="px-3 py-2.5 font-medium">When it runs</th>
                  <th className="px-3 py-2.5 font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100">
                {data.components.map((c) => {
                  const k = KIND_LABEL[c.kind];
                  return (
                    <tr className="align-top" key={c.name}>
                      <td className="px-5 py-3">
                        <p className="font-semibold text-stone-900">{c.name}</p>
                        {k && <span className={cn("mt-1 inline-block rounded-full px-1.5 py-0.5 text-[10.5px] font-medium ring-1 ring-inset", k.cls)}>{k.label}</span>}
                      </td>
                      <td className="px-3 py-3">
                        <p className="text-stone-800">{c.method}</p>
                        <p className="font-mono text-[11px] text-stone-400">{c.artifact}</p>
                        {c.evidence && <p className="mt-0.5 text-[12px] text-stone-500">{c.evidence}</p>}
                      </td>
                      <td className="px-3 py-3 text-stone-600">{c.runs}</td>
                      <td className="px-3 py-3">
                        <span className={cn("rounded-full px-2 py-0.5 text-[11.5px] font-medium", c.loaded ? "bg-emerald-50 text-emerald-700" : "bg-stone-100 text-stone-500")}>
                          {c.loaded ? "Available" : c.kind === "llm" ? "Not configured" : "Unavailable"}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
      <section className="rounded-xl border border-stone-200/80 bg-paper px-5 py-4 shadow-card">
        <p className="text-[13.5px] leading-6 text-stone-700">
          <b>Evaluation method.</b> The deployed pipeline ({data.model_name}, version {data.model_version}) predicts the <b>next day's</b> rainfall category (normal / heavy ≥64.5 mm / extreme ≥204.4 mm) for a region.
          Data was split by date (train on earlier days, test on later days) so no future information leaks into training.
          {ds && <> It was evaluated on a held-out test period of <b>{ds.splits.test} region-days</b>, the most recent part of {ds.date_range[0]} to {ds.date_range[1]}, using chronological splits.</>}
          {wm && <> Only <b>{wm.heavy_days}</b> of those days had heavy rain, so every heavy-rain figure below rests on a small sample.</>}
        </p>
      </section>

      {wm && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard
            label="Heavy-rain days caught (recall)"
            sub={`${wm.true_positives} of ${wm.heavy_days} heavy-rain days were flagged`}
            tone={wm.heavy_recall != null && wm.heavy_recall < 0.7 ? "warn" : "ok"}
            value={pct(wm.heavy_recall)}
          />
          <StatCard
            label="Missed events"
            sub={`${wm.false_negatives} heavy-rain days got no warning`}
            tone="danger"
            value={pct(wm.missed_event_rate)}
          />
          <StatCard
            label="Warnings that were right (precision)"
            sub={`${wm.true_positives} of ${wm.true_positives + wm.false_positives} heavy-rain warnings verified`}
            tone="warn"
            value={pct(wm.heavy_precision)}
          />
          <StatCard
            label="False-alarm rate"
            sub={`${wm.false_positives} of ${wm.normal_days} normal days wrongly flagged`}
            tone="default"
            value={pct(wm.false_alarm_rate, 1)}
          />
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        {test && (
          <Panel description="Rows: what actually happened. Columns: what the model predicted. Test period." title="Confusion matrix">
            <ConfusionMatrix metrics={test} />
          </Panel>
        )}
        <Panel description="Macro-averaged over the classes that occur. Accuracy is shown last because 95% of days are normal." title="Scores by period">
          <table className="w-full text-[13.5px]">
            <thead className="text-[12px] text-stone-500">
              <tr><th className="pb-2 text-left font-medium">Metric</th><th className="pb-2 text-right font-medium">Validation</th><th className="pb-2 text-right font-medium">Test</th></tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {([
                ["Heavy-rain recall", data.warning_metrics.validation?.heavy_recall, wm?.heavy_recall],
                ["Heavy-rain precision", data.warning_metrics.validation?.heavy_precision, wm?.heavy_precision],
                ["Macro F1", data.validation?.f1_macro, test?.f1_macro],
                ["Macro recall", data.validation?.recall_macro, test?.recall_macro],
                ["Accuracy", data.validation?.accuracy, test?.accuracy],
              ] as [string, number | null | undefined, number | null | undefined][]).map(([name, v, t]) => (
                <tr key={name}>
                  <td className={cn("py-2", name === "Accuracy" ? "text-stone-500" : "text-stone-800")}>{name}</td>
                  <td className="py-2 text-right tabular-nums text-stone-600">{pct(v, 1)}</td>
                  <td className="py-2 text-right font-semibold tabular-nums text-stone-900">{pct(t, 1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.single_modality_test && test && (
            <>
              <h4 className="mb-2 mt-5 text-[13px] font-semibold text-stone-800">Fusion vs single sources (test macro F1)</h4>
              <ModalityBars fusion={test} others={data.single_modality_test} />
            </>
          )}
        </Panel>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
        {ds && (
          <Panel title="Dataset">
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2.5 text-[13px]">
              <dt className="text-stone-500">Region-days</dt><dd className="font-medium">{ds.rows.toLocaleString("en-IN")}</dd>
              <dt className="text-stone-500">Regions</dt><dd>{ds.regions.join(", ")}</dd>
              <dt className="text-stone-500">Period</dt><dd>{ds.date_range[0]} → {ds.date_range[1]}</dd>
              <dt className="text-stone-500">Splits (chronological)</dt><dd>{ds.splits.train} train · {ds.splits.val} validation · {ds.splits.test} test</dd>
              <dt className="text-stone-500">Class counts</dt><dd>{ds.target_counts["0"]} normal · {ds.target_counts["1"]} heavy · {ds.target_counts["2"]} extreme</dd>
              <dt className="text-stone-500">Extreme class</dt><dd className="text-red-700">Not measurable (no test samples)</dd>
              <dt className="text-stone-500">Sources</dt><dd className="col-span-1">{ds.source}</dd>
            </dl>
          </Panel>
        )}
        <section className="rounded-xl border border-amber-200 bg-amber-50/70 p-5">
          <h3 className="flex items-center gap-2 text-[14px] font-semibold text-amber-900">
            <IconAlertTriangle className="text-amber-600" size={17} /> Limitations recorded by the evaluation
          </h3>
          <ul className="mt-3 list-disc space-y-2 pl-5 text-[13px] leading-6 text-amber-950">
            {data.caveats.map((c) => <li key={c}>{c}</li>)}
          </ul>
        </section>
      </div>
    </>
  );
}

function ConfusionMatrix({ metrics }: { metrics: ClassMetrics }) {
  const labels = ["Normal", "Heavy", "Extreme"];
  const cm = metrics.confusion_matrix;
  const max = Math.max(...cm.flat(), 1);
  return (
    <div className="overflow-x-auto">
      <table className="mx-auto text-center text-[13px]">
        <thead>
          <tr>
            <th />
            {labels.map((l) => <th className="px-2 pb-2 text-[12px] font-medium text-stone-500" key={l}>Predicted {l.toLowerCase()}</th>)}
          </tr>
        </thead>
        <tbody>
          {cm.map((row, i) => (
            <tr key={labels[i]}>
              <th className="pr-3 text-right text-[12px] font-medium text-stone-500">Actual {labels[i].toLowerCase()}</th>
              {row.map((v, j) => {
                const correct = i === j;
                const alpha = v / max;
                return (
                  <td className="p-1" key={j}>
                    <div
                      className={cn("grid h-16 w-20 place-items-center rounded-lg text-[16px] font-semibold tabular-nums", v === 0 && "text-stone-300")}
                      style={{
                        background: v === 0 ? "#fafaf9" : correct ? `rgba(42,119,151,${0.12 + alpha * 0.6})` : `rgba(200,97,42,${0.15 + alpha * 0.55})`,
                        color: v !== 0 && alpha > 0.5 ? "#fff" : undefined,
                      }}
                    >
                      {v}
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="mt-2 text-center text-[11.5px] text-stone-500">Blue = correct · orange = errors. The extreme row is empty: no extreme days in the test period.</p>
    </div>
  );
}

function ModalityBars({ fusion, others }: { fusion: ClassMetrics; others: Record<string, ClassMetrics> }) {
  const rows: [string, number][] = [
    ["Fusion (deployed)", fusion.f1_macro],
    ...Object.entries(others).map(([k, v]) => [k.replace("_", " ").replace(/^\w/, (c) => c.toUpperCase()), v.f1_macro] as [string, number]),
  ];
  return (
    <div className="space-y-2">
      {rows.map(([name, v]) => (
        <div className="grid grid-cols-[9rem_minmax(0,1fr)_3.5rem] items-center gap-3 text-[12.5px]" key={name}>
          <span className="text-stone-700">{name}</span>
          <div className="h-2 rounded-full bg-stone-100"><div className="h-full rounded-full bg-brand-500" style={{ width: `${v * 100}%` }} /></div>
          <span className="text-right tabular-nums text-stone-600">{pct(v, 1)}</span>
        </div>
      ))}
      <p className="text-[11.5px] leading-5 text-stone-500">Fusion is not better than weather-only on the test period, as the evaluation's caveats note.</p>
    </div>
  );
}
