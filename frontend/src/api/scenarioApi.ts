import type { ChatRequest, ChatResponse, IncidentMatch, RegionProfile, ScenarioRequest, ScenarioResult } from "../types/api";
import { apiClient, API_V1 } from "./client";
import { toApiError } from "./errors";

export async function simulateScenario(body: ScenarioRequest): Promise<ScenarioResult> {
  try {
    const { data } = await apiClient.post<ScenarioResult>(`${API_V1}/scenarios/simulate`, body, { timeout: 60000 });
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

/** The assistant may run several simulations per answer; allow up to 3 minutes. */
export async function sendChat(body: ChatRequest): Promise<ChatResponse> {
  try {
    const { data } = await apiClient.post<ChatResponse>(`${API_V1}/chat`, body, { timeout: 180000 });
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export interface GeoVillage {
  id: string;
  name: string;
  district: string;
  region: string;
  lat: number;
  lon: number;
}

export async function getVillages(): Promise<GeoVillage[]> {
  try {
    const { data } = await apiClient.get<GeoVillage[]>(`${API_V1}/geo/villages`);
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function getIncidents(): Promise<IncidentMatch[]> {
  try {
    const { data } = await apiClient.get<IncidentMatch[]>(`${API_V1}/geo/incidents`, { params: { limit: 200 } });
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function getRegions(): Promise<RegionProfile[]> {
  try {
    const { data } = await apiClient.get<RegionProfile[]>(`${API_V1}/geo/regions`);
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}
