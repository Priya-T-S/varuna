import { useMutation } from "@tanstack/react-query";
import { sendChat, simulateScenario } from "../../api/scenarioApi";
import { ApiError } from "../../api/errors";
import { IconSparkles } from "../../components/ui/Icons";
import { PageHeader, Panel } from "../../components/ui/Panel";
import { EmptyState, ErrorState } from "../../components/ui/States";
import { ChatPanel } from "./ChatPanel";
import { ScenarioControls } from "./ScenarioControls";
import { ScenarioResultView } from "./ScenarioResultView";
import { useWhatIfStore } from "./whatIfStore";

export function WhatIfPage() {
  const { sessionId, turns, scenario, result, setSessionId, addTurn, setScenario, setResult, reset } = useWhatIfStore();

  const chat = useMutation({
    mutationFn: (message: string) => sendChat({ message, session_id: sessionId }),
    onSuccess: (data) => {
      setSessionId(data.session_id);
      addTurn({ role: "assistant", text: data.reply_markdown, toolsUsed: data.tools_used, alertPreview: data.alert_preview });
      if (data.scenario) {
        setResult(data.scenario);
        setScenario({ ...scenario, ...data.scenario.scenario });
      }
    },
    onError: (error) => {
      const unavailable = error instanceof ApiError && error.status === 503;
      addTurn({
        role: "system",
        error: !unavailable,
        text: unavailable
          ? "The AI advisor isn't switched on yet (it needs an Anthropic API key). You can still run the simulation directly with the scenario controls below."
          : `The advisor could not answer: ${error instanceof Error ? error.message : "request failed"}`,
      });
    },
  });

  const simulate = useMutation({
    mutationFn: simulateScenario,
    onSuccess: (data) => setResult(data),
  });

  function send(text: string) {
    addTurn({ role: "user", text });
    chat.mutate(text);
  }

  return (
    <div className="space-y-6">
      <PageHeader
        description="Describe a rainfall situation, or set it with the controls. See which villages would flood, why, and which past disasters looked similar."
        eyebrow="Scenario planning"
        title="What-if flood simulator"
      />
      <div className="grid gap-4 lg:grid-cols-[minmax(0,25rem)_minmax(0,1fr)]">
        <div className="space-y-4 lg:sticky lg:top-[5.5rem] lg:self-start">
          <ChatPanel
            onReset={() => {
              reset();
              chat.reset();
              simulate.reset();
            }}
            onSend={send}
            pending={chat.isPending}
            turns={turns}
          />
          <Panel description="Runs the simulator directly, no AI needed. The advisor's last scenario appears here." title="Scenario controls">
            <ScenarioControls onChange={setScenario} onRun={() => simulate.mutate(scenario)} running={simulate.isPending} value={scenario} />
          </Panel>
        </div>

        <div className="min-w-0 space-y-4">
          {simulate.isError && (
            <ErrorState body={simulate.error instanceof Error ? simulate.error.message : "Request failed"} title="Simulation failed" />
          )}
          {result ? (
            <ScenarioResultView result={result} />
          ) : (
            <EmptyState
              body="Ask the advisor something like “If rainfall increases by 20% in Kerala, which villages flood?”, or press Run simulation. You'll get every monitored village's flood risk, the reasons behind it, the AI model's view and similar past disasters."
              className="bg-white py-20"
              icon={<IconSparkles size={20} />}
              title="Your scenario results will appear here"
            />
          )}
        </div>
      </div>
    </div>
  );
}
