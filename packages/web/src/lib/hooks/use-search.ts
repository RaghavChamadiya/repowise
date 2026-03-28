"use client";

import useSWR from "swr";
import { useDebounce } from "./use-debounce";
import { search } from "@/lib/api/search";
import type { SearchResultResponse } from "@/lib/api/types";

export function useSearch(
  query: string,
  opts?: { search_type?: "semantic" | "fulltext"; limit?: number; debounce?: number },
) {
  const debounced = useDebounce(query, opts?.debounce ?? 300);
  const key = debounced.trim().length >= 2 ? `search:${debounced}:${opts?.search_type}` : null;
  const { data, error, isLoading } = useSWR<SearchResultResponse[]>(
    key,
    () => search(debounced, { search_type: opts?.search_type, limit: opts?.limit }),
    { revalidateOnFocus: false },
  );
  return {
    results: data ?? [],
    error,
    isLoading: isLoading && !!key,
    isTyping: query !== debounced,
  };
}
