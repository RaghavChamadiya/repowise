"use client";

import useSWR from "swr";
import { listAllPages } from "@/lib/api/pages";
import type { PageResponse } from "@/lib/api/types";

export function usePages(repoId: string | null, opts?: { page_type?: string }) {
  const { data, error, isLoading, mutate } = useSWR<PageResponse[]>(
    repoId ? `pages:${repoId}:${opts?.page_type ?? "all"}` : null,
    () => listAllPages(repoId!, { page_type: opts?.page_type }),
    { revalidateOnFocus: false },
  );
  return { pages: data ?? [], error, isLoading, mutate };
}
