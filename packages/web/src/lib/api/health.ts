import { apiGet } from "./client";
import type { HealthResponse } from "./types";

export async function getHealth(): Promise<HealthResponse> {
  return apiGet<HealthResponse>("/health");
}
