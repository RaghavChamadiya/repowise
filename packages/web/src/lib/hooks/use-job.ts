"use client";

import useSWR from "swr";
import { getJob, getJobStreamUrl } from "@/lib/api/jobs";
import { useSSE } from "./use-sse";
import type { JobResponse, JobProgressEvent } from "@/lib/api/types";

/**
 * Combines polling (SWR) for job metadata with SSE for live progress events.
 * - When the job is running, SSE is active and progress events update in real-time.
 * - When done/failed, SSE closes and SWR has the final state.
 */
export function useJob(jobId: string | null) {
  const { data: job, mutate } = useSWR<JobResponse>(
    jobId ? `/api/jobs/${jobId}` : null,
    jobId ? () => getJob(jobId) : null,
    {
      refreshInterval: (j) =>
        j?.status === "running" || j?.status === "pending" ? 5000 : 0,
    },
  );

  const isActive = job?.status === "running" || job?.status === "pending";
  const streamUrl = jobId && isActive ? getJobStreamUrl(jobId) : null;

  const sse = useSSE<JobProgressEvent>(streamUrl, { enabled: !!streamUrl });

  // When SSE marks done, trigger a final SWR revalidation
  if (sse.isDone && isActive) {
    mutate();
  }

  return { job, sse, isActive };
}
