import type { PredictionRequest, PredictionResponse } from "../types/api";

export interface HistorySession {
  id: string;
  stored_at: string;
  simulated: boolean;
  request: PredictionRequest;
  response: PredictionResponse;
}

const STORAGE_KEY = "varuna.history.v1";

export function loadHistory(): HistorySession[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as HistorySession[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveHistory(sessions: HistorySession[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
}

export function appendHistory(session: HistorySession): HistorySession[] {
  const next = [session, ...loadHistory()].slice(0, 100);
  saveHistory(next);
  return next;
}
