import axios, { type AxiosError } from "axios";
import type { HTTPExceptionBody, HTTPValidationError } from "../types/api";

export class ApiError extends Error {
  readonly status: number | undefined;
  readonly detail: string;
  readonly validation: HTTPValidationError["detail"] | undefined;
  readonly code: "MODEL_NOT_DEPLOYED" | "VALIDATION" | "HTTP" | "NETWORK";

  constructor(params: {
    message: string;
    status?: number;
    detail: string;
    validation?: HTTPValidationError["detail"];
    code: ApiError["code"];
  }) {
    super(params.message);
    this.name = "ApiError";
    this.status = params.status;
    this.detail = params.detail;
    this.validation = params.validation;
    this.code = params.code;
  }
}

function formatValidation(items: HTTPValidationError["detail"]): string {
  return items
    .map((item) => `${item.loc.filter((p) => p !== "body").join(".")}: ${item.msg}`)
    .join("; ");
}

export function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;

  if (axios.isAxiosError(error)) {
    const ax = error as AxiosError<HTTPExceptionBody | HTTPValidationError>;
    const status = ax.response?.status;
    const data = ax.response?.data;

    if (status === 501) {
      const detail =
        data && typeof data === "object" && "detail" in data && typeof data.detail === "string"
          ? data.detail
          : "No trained rainfall model is deployed yet.";
      return new ApiError({
        message: detail,
        status,
        detail,
        code: "MODEL_NOT_DEPLOYED",
      });
    }

    if (status === 422 && data && typeof data === "object" && Array.isArray((data as HTTPValidationError).detail)) {
      const validation = (data as HTTPValidationError).detail;
      const detail = formatValidation(validation);
      return new ApiError({
        message: detail,
        status,
        detail,
        validation,
        code: "VALIDATION",
      });
    }

    if (data && typeof data === "object" && "detail" in data) {
      const raw = (data as HTTPExceptionBody | HTTPValidationError).detail;
      const detail = typeof raw === "string" ? raw : Array.isArray(raw) ? formatValidation(raw) : ax.message;
      return new ApiError({
        message: detail,
        status,
        detail,
        code: "HTTP",
      });
    }

    if (!ax.response) {
      return new ApiError({
        message: ax.message || "Network error: the API could not be reached.",
        detail: ax.message || "Network error",
        code: "NETWORK",
      });
    }

    return new ApiError({
      message: ax.message,
      status,
      detail: ax.message,
      code: "HTTP",
    });
  }

  const message = error instanceof Error ? error.message : "Unknown error";
  return new ApiError({ message, detail: message, code: "HTTP" });
}
