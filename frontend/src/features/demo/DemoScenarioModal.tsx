import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { runDemo } from "../../api/systemApi";
import { Button } from "../../components/ui/Button";
import { IconCheck, IconDrop, IconX } from "../../components/ui/Icons";
import { cn } from "../../lib/cn";
import { useUiStore } from "../../store/uiStore";
import type { DemoRunResult } from "../../types/api";

type ScenarioId = "kerala_extreme" | "mumbai_2005";

const SCENARIOS: { id: ScenarioId; title: string; subtitle: string; blurb: string }[] = [
  {
    id: "kerala_extreme",
    title: "Extreme Kerala rainfall",
    subtitle: "350 mm over 3 days · saturated soil",
    blurb: "A monsoon burst on already waterlogged ground, similar to August 2018.",
  },
  {
    id: "mumbai_2005",
    title: "Mumbai 26 July replay",
    subtitle: "900 mm in 24 hours · high tide",
    blurb: "The 2005 deluge: record rain arriving during a high tide.",
  },
];

const STEPS = [
  { key: "data", label: "Data received" },
  { key: "ai", label: "AI analysing" },
  { key: "risk", label: "Risk detected" },
  { key: "explain", label: "Explanation generated" },
  { key: "villages", label: "Villages identified" },
  { key: "alert", label: "Alert prepared" },
];

/**
 * One-click demo: runs a preset scenario through the real pipeline
 * (fusion model → hydrology → alert → dispatch) and animates each stage.
 */
export function DemoScenarioModal({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const setSelectedAlertId = useUiStore((s) => s.setSelectedAlertId);
  const [scenario, setScenario] = useState<ScenarioId>("kerala_extreme");
  const [step, setStep] = useState(-1); // index of the last completed stage
  const [result, setResult] = useState<DemoRunResult | null>(null);
  const timers = useRef<number[]>([]);

  const clearTimers = () => {
    timers.current.forEach((t) => window.clearTimeout(t));
    timers.current = [];
  };
  useEffect(() => clearTimers, []);

  const run = useMutation({
    mutationFn: () => runDemo(scenario),
    onMutate: () => {
      clearTimers();
      setResult(null);
      setStep(-1);
      // Advance through the first stages while the pipeline runs...
      [0, 1].forEach((i) => timers.current.push(window.setTimeout(() => setStep((s) => Math.max(s, i)), 450 + i * 650)));
    },
    onSuccess: (data) => {
      setResult(data);
      clearTimers();
      // ...then reveal the remaining stages one by one with their real details.
      STEPS.forEach((_, i) => timers.current.push(window.setTimeout(() => setStep((s) => Math.max(s, i)), 250 + i * 420)));
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
      queryClient.invalidateQueries({ queryKey: ["current-risk"] });
      queryClient.invalidateQueries({ queryKey: ["system-status"] });
    },
    onError: () => clearTimers(),
  });

  const running = run.isPending || (result !== null && step < STEPS.length - 1);
  const finished = result !== null && step >= STEPS.length - 1;
  const detailFor = (key: string) => result?.stages.find((s) => s.key === key)?.detail;

  // Portal to <body>: the page's fade-in transform would otherwise trap position:fixed.
  return createPortal(
    <div aria-modal className="fixed inset-0 z-[1300] overflow-y-auto" role="dialog">
      <button aria-label="Close" className="fixed inset-0 bg-stone-900/40 backdrop-blur-[2px]" onClick={onClose} type="button" />
      <div className="flex min-h-full items-center justify-center p-4">
      <div className="relative w-full max-w-lg animate-fade-up overflow-hidden rounded-2xl bg-white shadow-2xl">
        <header className="flex items-start justify-between gap-3 bg-gradient-to-br from-brand-800 to-brand-600 px-6 py-5 text-white">
          <div>
            <p className="text-[12px] font-medium uppercase tracking-[0.12em] text-brand-100">Live demo</p>
            <h2 className="mt-0.5 text-[19px] font-semibold">Run a demo scenario</h2>
            <p className="mt-1 text-[13px] text-brand-100">Real pipeline, simulated rainfall. The alert it creates is labelled "Demo".</p>
          </div>
          <button aria-label="Close" className="rounded-lg p-1.5 text-brand-100 hover:bg-white/10" onClick={onClose} type="button">
            <IconX size={18} />
          </button>
        </header>

        <div className="space-y-5 px-6 py-5">
          <div className="grid gap-2 sm:grid-cols-2">
            {SCENARIOS.map((s) => (
              <button
                className={cn(
                  "rounded-xl border p-3.5 text-left transition-colors",
                  scenario === s.id ? "border-brand-500 bg-brand-50 ring-1 ring-brand-500" : "border-stone-200 hover:border-stone-300",
                )}
                disabled={running}
                key={s.id}
                onClick={() => setScenario(s.id)}
                type="button"
              >
                <span className="flex items-center gap-2 text-[14px] font-semibold text-stone-900"><IconDrop size={15} className="text-brand-600" /> {s.title}</span>
                <span className="mt-0.5 block text-[12.5px] font-medium text-brand-700">{s.subtitle}</span>
                <span className="mt-1 block text-[12px] leading-5 text-stone-500">{s.blurb}</span>
              </button>
            ))}
          </div>

          {(run.isPending || result) && (
            <ol className="space-y-2.5" aria-live="polite">
              {STEPS.map((s, i) => {
                const done = step >= i;
                const active = !done && (i === step + 1) && running;
                return (
                  <li className="flex items-start gap-3" key={s.key}>
                    <span
                      className={cn(
                        "mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full border-2 transition-colors",
                        done ? "border-emerald-600 bg-emerald-600 text-white" : active ? "border-brand-500" : "border-stone-200",
                      )}
                    >
                      {done ? <IconCheck size={13} /> : active ? <span className="h-2 w-2 animate-ping rounded-full bg-brand-500" /> : null}
                    </span>
                    <span>
                      <span className={cn("block text-[13.5px] font-medium", done ? "text-stone-900" : "text-stone-400")}>{s.label}</span>
                      {done && detailFor(s.key) && <span className="block text-[12.5px] leading-5 text-stone-600 animate-fade-up">{detailFor(s.key)}</span>}
                    </span>
                  </li>
                );
              })}
            </ol>
          )}
          {run.isError && <p className="text-[13px] text-red-700">{(run.error as Error).message}</p>}

          <div className="flex flex-wrap justify-end gap-2 border-t border-stone-100 pt-4">
            <Button onClick={onClose} type="button" variant="ghost">Close</Button>
            {finished && result?.top_alert_id ? (
              <Button
                onClick={() => {
                  setSelectedAlertId(result.top_alert_id);
                  onClose();
                  navigate("/alerts");
                }}
                type="button"
              >
                View alert →
              </Button>
            ) : (
              <Button disabled={running} onClick={() => run.mutate()} type="button">
                {running ? "Running…" : result ? "Run again" : "Run simulation"}
              </Button>
            )}
          </div>
        </div>
      </div>
      </div>
    </div>,
    document.body,
  );
}
