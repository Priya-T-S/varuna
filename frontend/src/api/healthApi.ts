import type { HealthResponse } from "../types/api";
import { apiClient, API_V1 } from "./client";
import { toApiError } from "./errors";

export async function getHealth(): Promise<HealthResponse> {
  try {
    const { data } = await apiClient.get<HealthResponse>(`${API_V1}/health`);
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}
