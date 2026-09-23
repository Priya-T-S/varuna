import axios from "axios";

/**
 * In development, Vite proxies `/api` to FastAPI (vite.config.ts).
 * Leave VITE_API_URL unset so requests stay same-origin.
 */
export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "",
  timeout: 20000,
  headers: { "Content-Type": "application/json" },
});

export const API_V1 = "/api/v1";
