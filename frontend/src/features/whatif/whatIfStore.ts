import { create } from "zustand";
import type { ScenarioRequest, ScenarioResult } from "../../types/api";

export interface ChatTurn {
  role: "user" | "assistant" | "system";
  text: string;
  toolsUsed?: string[];
  alertPreview?: string | null;
  error?: boolean;
}

const DEFAULT_SCENARIO: ScenarioRequest = {
  region: "Kerala",
  rainfall_change_pct: 20,
  rainfall_mm: null,
  duration_days: 3,
  antecedent: "normal",
  dam_release: false,
  high_tide: false,
};

interface WhatIfState {
  sessionId: string | null;
  turns: ChatTurn[];
  scenario: ScenarioRequest;
  result: ScenarioResult | null;
  setSessionId: (id: string | null) => void;
  addTurn: (turn: ChatTurn) => void;
  setScenario: (s: ScenarioRequest) => void;
  setResult: (r: ScenarioResult | null) => void;
  reset: () => void;
}

/** Kept outside the page so the conversation survives navigating away and back. */
export const useWhatIfStore = create<WhatIfState>((set) => ({
  sessionId: null,
  turns: [],
  scenario: DEFAULT_SCENARIO,
  result: null,
  setSessionId: (sessionId) => set({ sessionId }),
  addTurn: (turn) => set((s) => ({ turns: [...s.turns, turn] })),
  setScenario: (scenario) => set({ scenario }),
  setResult: (result) => set({ result }),
  reset: () => set({ sessionId: null, turns: [], result: null, scenario: DEFAULT_SCENARIO }),
}));
