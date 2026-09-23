import { useEffect, useRef, useState } from "react";
import { Button } from "../../components/ui/Button";
import { IconSend, IconSparkles, LogoMark } from "../../components/ui/Icons";
import { Markdown } from "../../components/ui/Markdown";
import { cn } from "../../lib/cn";
import type { ChatTurn } from "./whatIfStore";

export const SUGGESTIONS = [
  "If rainfall increases by 20% in Kerala, which villages flood?",
  "What if Chennai gets 2015-level rain (490 mm in a day) during high tide?",
  "Mumbai gets 900 mm in 24 hours like 26 July 2005. Which wards go under?",
  "Assam: 40% more rain for 5 days with rivers already full. What happens in Majuli and Dhemaji?",
  "Kerala: +50% rain on saturated soil and Idukki dam releases water. Who is at risk?",
];

const TOOL_LABELS: Record<string, string> = {
  simulate_flood_scenario: "Ran flood simulation",
  get_village_profile: "Checked village terrain",
  search_past_incidents: "Searched past incidents",
  list_monitored_places: "Listed monitored places",
  draft_alert_message: "Drafted collector alert",
};

export function ChatPanel({
  turns,
  pending,
  onSend,
  onReset,
}: {
  turns: ChatTurn[];
  pending: boolean;
  onSend: (text: string) => void;
  onReset: () => void;
}) {
  const [draft, setDraft] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: "smooth", block: "end" });
  }, [turns.length, pending]);

  function submit(text: string) {
    const trimmed = text.trim();
    if (!trimmed || pending) return;
    onSend(trimmed);
    setDraft("");
  }

  return (
    <section className="flex h-[36rem] flex-col overflow-hidden rounded-xl border border-stone-200/80 bg-paper shadow-card">
      <header className="flex items-center justify-between gap-3 border-b border-stone-100 bg-gradient-to-r from-brand-50 to-white px-5 py-3.5">
        <div className="flex items-center gap-3">
          <LogoMark size={34} />
          <div>
            <h2 className="text-[14.5px] font-semibold text-stone-900">Flood advisor</h2>
            <p className="text-[12px] text-stone-500">Describe a situation. I'll simulate it and explain the result.</p>
          </div>
        </div>
        {turns.length > 0 && (
          <Button onClick={onReset} size="sm" type="button" variant="ghost">
            New chat
          </Button>
        )}
      </header>

      <div aria-live="polite" className="scroll-quiet flex-1 space-y-4 overflow-y-auto bg-stone-50/40 px-4 py-4">
        {turns.length === 0 && (
          <div className="space-y-3">
            <div className="flex items-start gap-2 text-[13.5px] leading-6 text-stone-600">
              <IconSparkles className="mt-1 shrink-0 text-brand-500" />
              <p>Ask in plain language, in English, Hindi, Malayalam, Tamil or Assamese. Try one of these:</p>
            </div>
            <div className="space-y-2">
              {SUGGESTIONS.map((s) => (
                <button
                  className="block w-full rounded-lg border border-stone-200 bg-white px-3.5 py-2.5 text-left text-[13px] leading-snug text-stone-700 shadow-sm transition-all hover:border-brand-300 hover:bg-brand-50/50 hover:text-stone-900"
                  key={s}
                  onClick={() => submit(s)}
                  type="button"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {turns.map((turn, idx) => (
          <div className={cn("flex gap-2.5", turn.role === "user" ? "justify-end" : "justify-start")} key={idx}>
            {turn.role === "assistant" && (
              <span className="mt-0.5 shrink-0"><LogoMark size={26} /></span>
            )}
            <div
              className={cn(
                "max-w-[88%] px-3.5 py-2.5",
                turn.role === "user" && "rounded-2xl rounded-br-md bg-brand-700 text-[13.5px] leading-6 text-white",
                turn.role === "assistant" && "rounded-2xl rounded-tl-md border border-stone-200 bg-white shadow-sm",
                turn.role === "system" && "rounded-xl border border-amber-200 bg-amber-50 text-[13px] leading-6 text-amber-900",
                turn.error && "border-red-200 bg-red-50 text-red-900",
              )}
            >
              {turn.role === "assistant" ? <Markdown text={turn.text} /> : <p className="whitespace-pre-wrap">{turn.text}</p>}
              {turn.toolsUsed && turn.toolsUsed.length > 0 && (
                <div className="mt-2.5 flex flex-wrap gap-1.5 border-t border-stone-100 pt-2">
                  {Array.from(new Set(turn.toolsUsed)).map((t) => (
                    <span className="rounded-full bg-brand-50 px-2 py-0.5 text-[11px] font-medium text-brand-700" key={t}>
                      {TOOL_LABELS[t] ?? t}
                    </span>
                  ))}
                </div>
              )}
              {turn.alertPreview && (
                <pre className="mt-2.5 whitespace-pre-wrap rounded-lg border border-dashed border-stone-300 bg-stone-50 p-2.5 font-mono text-[11.5px] leading-5 text-stone-700">
                  {turn.alertPreview}
                </pre>
              )}
            </div>
          </div>
        ))}
        {pending && (
          <div className="flex items-center gap-2.5">
            <LogoMark size={26} />
            <div className="flex items-center gap-2 rounded-2xl rounded-tl-md border border-stone-200 bg-white px-3.5 py-2.5 text-[13px] text-stone-500 shadow-sm">
              <span className="flex gap-1">
                {[0, 1, 2].map((i) => (
                  <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-brand-400" key={i} style={{ animationDelay: `${i * 0.15}s` }} />
                ))}
              </span>
              Simulating and checking past incidents…
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <form
        className="border-t border-stone-100 bg-white p-3"
        onSubmit={(e) => {
          e.preventDefault();
          submit(draft);
        }}
      >
        <div className="flex items-end gap-2 rounded-xl border border-stone-300 bg-white p-1.5 shadow-sm focus-within:border-brand-500 focus-within:ring-2 focus-within:ring-brand-100">
          <textarea
            aria-label="Describe a rainfall scenario"
            className="max-h-32 min-h-[2.5rem] flex-1 resize-none bg-transparent px-2 py-1.5 text-[14px] outline-none placeholder:text-stone-400"
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit(draft);
              }
            }}
            placeholder="e.g. What if Kochi gets 30% more rain and the Idukki dam opens?"
            rows={2}
            value={draft}
          />
          <Button aria-label="Ask" className="h-9 w-9 !p-0" disabled={pending || !draft.trim()} type="submit">
            <IconSend size={17} />
          </Button>
        </div>
        <p className="mt-1.5 px-1 text-[11px] text-stone-400">Enter to send · Shift+Enter for a new line</p>
      </form>
    </section>
  );
}
