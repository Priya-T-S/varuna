import { create } from "zustand";
import type { AlertResponse, PredictionRequest, PredictionResponse, WeatherFeatures } from "../types/api";
import { appendHistory, loadHistory, type HistorySession } from "../lib/historyStorage";

export type SimulatorMode = "auto" | "forced" | "off";

export interface ActiveAnalysis {
  request: PredictionRequest;
  response: PredictionResponse;
  simulated: boolean;
}

interface AnalysisDraft {
  latitude: string;
  longitude: string;
  region_name: string;
  horizon_hours: string;
  weather: Record<keyof WeatherFeatures, string>;
}

const emptyWeather: Record<keyof WeatherFeatures, string> = {
  temperature_c: "",
  humidity_pct: "",
  pressure_hpa: "",
  wind_speed_ms: "",
  cloud_cover_pct: "",
};

interface UiState {
  simulatorMode: SimulatorMode;
  lastModelUnavailableDetail: string | null;
  analysisDraft: AnalysisDraft;
  activeAnalysis: ActiveAnalysis | null;
  history: HistorySession[];
  selectedAlertId: number | null;
  setSimulatorMode: (mode: SimulatorMode) => void;
  setLastModelUnavailableDetail: (detail: string | null) => void;
  patchDraft: (patch: Partial<AnalysisDraft>) => void;
  setWeatherField: (key: keyof WeatherFeatures, value: string) => void;
  applyAlert: (alert: AlertResponse) => void;
  setActiveAnalysis: (analysis: ActiveAnalysis) => void;
  loadHistoryFromStorage: () => void;
  addHistory: (session: Omit<HistorySession, "id" | "stored_at">) => void;
  setSelectedAlertId: (id: number | null) => void;
}

export const useUiStore = create<UiState>((set, get) => ({
  simulatorMode: "auto",
  lastModelUnavailableDetail: null,
  analysisDraft: {
    latitude: "19.0760",
    longitude: "72.8777",
    region_name: "Mumbai",
    horizon_hours: "12",
    weather: { ...emptyWeather },
  },
  activeAnalysis: null,
  history: [],
  selectedAlertId: null,
  setSimulatorMode: (simulatorMode) => set({ simulatorMode }),
  setLastModelUnavailableDetail: (lastModelUnavailableDetail) => set({ lastModelUnavailableDetail }),
  patchDraft: (patch) => set({ analysisDraft: { ...get().analysisDraft, ...patch } }),
  setWeatherField: (key, value) =>
    set({
      analysisDraft: {
        ...get().analysisDraft,
        weather: { ...get().analysisDraft.weather, [key]: value },
      },
    }),
  applyAlert: (alert) =>
    set({
      selectedAlertId: alert.id,
      analysisDraft: {
        ...get().analysisDraft,
        latitude: String(alert.location.latitude),
        longitude: String(alert.location.longitude),
        region_name: alert.region_name,
      },
    }),
  setActiveAnalysis: (activeAnalysis) => set({ activeAnalysis }),
  loadHistoryFromStorage: () => set({ history: loadHistory() }),
  addHistory: (session) => {
    const record: HistorySession = {
      ...session,
      id: crypto.randomUUID(),
      stored_at: new Date().toISOString(),
    };
    set({ history: appendHistory(record) });
  },
  setSelectedAlertId: (selectedAlertId) => set({ selectedAlertId }),
}));
