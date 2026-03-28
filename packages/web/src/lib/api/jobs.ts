import { apiGet } from "./client";
import type { JobResponse } from "./types";

export async function listJobs(opts?: {
  repo_id?: string;
  status?: string;
  limit?: number;
  offset?: number;
}): Promise<JobResponse[]> {
  return apiGet<JobResponse[]>("/api/jobs", opts);
}

export async function getJob(jobId: string): Promise<JobResponse> {
  return apiGet<JobResponse>(`/api/jobs/${jobId}`);
}

/** Returns the SSE stream URL for a job. Use with EventSource or the useSSE hook. */
export function getJobStreamUrl(jobId: string): string {
  const base = process.env.NEXT_PUBLIC_REPOWISE_API_URL ?? "";
  return `${base}/api/jobs/${jobId}/stream`;
}
