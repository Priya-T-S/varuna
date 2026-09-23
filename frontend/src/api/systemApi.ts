import type {
  DataSource,
  DemoRunResult,
  FaultComponent,
  ModelPerformance,
  RegionRiskSnapshot,
  SystemStatus,
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

export const getSystemStatus = () => call(() => apiClient.get<SystemStatus>(`${API_V1}/system/status`));
export const getDataSources = () => call(() => apiClient.get<DataSource[]>(`${API_V1}/system/data-sources`));
export const getCurrentRisk = () => call(() => apiClient.get<RegionRiskSnapshot[]>(`${API_V1}/system/current-risk`));
export const setFault = (component: FaultComponent, enabled: boolean) =>
  call(() => apiClient.post<Record<FaultComponent, boolean>>(`${API_V1}/system/faults`, { component, enabled }));
export const runDemo = (scenario: "kerala_extreme" | "mumbai_2005") =>
  call(() => apiClient.post<DemoRunResult>(`${API_V1}/demo/run`, { scenario }, { timeout: 90000 }));
export const getModelPerformance = () =>
  call(() => apiClient.get<ModelPerformance>(`${API_V1}/predictions/model-performance`));
