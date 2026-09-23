import type { GradCamResponse, ModelInfoResponse, PredictionRequest, PredictionResponse } from "../types/api";
import { apiClient, API_V1 } from "./client";
import { toApiError } from "./errors";


export async function createPrediction(body: PredictionRequest): Promise<PredictionResponse> {
  try {
    const { data } = await apiClient.post<PredictionResponse>(`${API_V1}/predictions`, body);
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function getModelInfo(): Promise<ModelInfoResponse> {
  try {
    const { data } = await apiClient.get<ModelInfoResponse>(`${API_V1}/predictions/model-info`);
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}

/**
 * POST /api/v1/predictions/explain-image
 *
 * Upload a satellite image and receive a real Grad-CAM explanation from
 * the trained satellite_model_v1.pt.  The image is sent as multipart/form-data.
 * The returned heatmap_data_url and overlay_data_url are base64 PNG data URLs.
 */
export async function explainImage(imageFile: File): Promise<GradCamResponse> {
  try {
    const formData = new FormData();
    formData.append("image", imageFile);
    const { data } = await apiClient.post<GradCamResponse>(
      `${API_V1}/predictions/explain-image`,
      formData,
      { headers: { "Content-Type": "multipart/form-data" } },
    );
    return data;
  } catch (error) {
    throw toApiError(error);
  }
}
