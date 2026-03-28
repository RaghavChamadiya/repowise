"use client";

import useSWR from "swr";
import { getPageById, getPageVersions } from "@/lib/api/pages";
import type { PageResponse, PageVersionResponse } from "@/lib/api/types";

export function usePage(pageId: string | null) {
  const { data, error, isLoading, mutate } = useSWR<PageResponse>(
    pageId ? `page:${pageId}` : null,
    () => getPageById(pageId!),
    { revalidateOnFocus: false },
  );
  return { page: data, error, isLoading, mutate };
}

export function usePageVersions(pageId: string | null) {
  const { data, error, isLoading } = useSWR<PageVersionResponse[]>(
    pageId ? `page:${pageId}:versions` : null,
    () => getPageVersions(pageId!),
    { revalidateOnFocus: false },
  );
  return { versions: data ?? [], error, isLoading };
}
