import type {
  AlertEvent,
  AlertResponse,
  AlertRule,
  EvaluateRequest,
  EvaluateResponse,
  FloodLevel,
  ProviderStatus,
  Recipient,
  RecipientInput,
  TestAlertRequest,
} from "../types/api";
import { apiClient, API_V1 } from "./client";
import { toApiError } from "./errors";

async function call<T>(fn: () => Promise<{ data: T }>): Promise<T> {
  try {
    const { data } = await fn();
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

// Alert evaluation runs the model + sends messages; allow more than the default 20 s.
const SLOW = { timeout: 90000 };

export const getActiveAlerts = () => call(() => apiClient.get<AlertResponse[]>(`${API_V1}/alerts`));
export const getRecentAlerts = (limit = 50) =>
  call(() => apiClient.get<AlertResponse[]>(`${API_V1}/alerts/recent`, { params: { limit } }));
export const acknowledgeAlert = (id: number, by: string) =>
  call(() => apiClient.post<AlertResponse>(`${API_V1}/alerts/${id}/acknowledge`, { by }));
export const getAlertEvents = (id: number) => call(() => apiClient.get<AlertEvent[]>(`${API_V1}/alerts/${id}/events`));
export const reviewAlert = (id: number, by: string, note = "") =>
  call(() => apiClient.post<AlertResponse>(`${API_V1}/alerts/${id}/review`, { by, note }));
export const changeAlertSeverity = (id: number, by: string, level: FloodLevel, reason: string) =>
  call(() => apiClient.post<AlertResponse>(`${API_V1}/alerts/${id}/severity`, { by, level, reason }));
export const resolveAlert = (id: number, by: string, note = "") =>
  call(() => apiClient.post<AlertResponse>(`${API_V1}/alerts/${id}/resolve`, { by, note }));
export const addAlertNote = (id: number, by: string, text: string) =>
  call(() => apiClient.post<AlertResponse>(`${API_V1}/alerts/${id}/note`, { by, text }));
export const evaluateRegion = (body: EvaluateRequest) =>
  call(() => apiClient.post<EvaluateResponse>(`${API_V1}/alerts/evaluate`, body, SLOW));
export const sendTestAlert = (body: TestAlertRequest) =>
  call(() => apiClient.post<AlertResponse>(`${API_V1}/alerts/test`, body, SLOW));
export const getProviders = () => call(() => apiClient.get<ProviderStatus[]>(`${API_V1}/alerts/providers`));

export const getRecipients = () => call(() => apiClient.get<Recipient[]>(`${API_V1}/recipients`));
export const createRecipient = (body: RecipientInput) =>
  call(() => apiClient.post<Recipient>(`${API_V1}/recipients`, body));
export const updateRecipient = (id: number, body: RecipientInput) =>
  call(() => apiClient.put<Recipient>(`${API_V1}/recipients/${id}`, body));
export const deleteRecipient = (id: number) => call(() => apiClient.delete<void>(`${API_V1}/recipients/${id}`));

export const getAlertRules = () => call(() => apiClient.get<AlertRule[]>(`${API_V1}/alert-rules`));
export const updateAlertRule = (id: number, body: Omit<AlertRule, "id">) =>
  call(() => apiClient.put<AlertRule>(`${API_V1}/alert-rules/${id}`, body));
export const createAlertRule = (body: Omit<AlertRule, "id">) =>
  call(() => apiClient.post<AlertRule>(`${API_V1}/alert-rules`, body));
export const deleteAlertRule = (id: number) => call(() => apiClient.delete<void>(`${API_V1}/alert-rules/${id}`));

export function alertStreamUrl(): string {
  return `${import.meta.env.VITE_API_URL || ""}${API_V1}/alerts/stream`;
}
