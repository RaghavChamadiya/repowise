import { apiGet } from "./client";
import type { SearchResultResponse } from "./types";

export async function search(
  query: string,
  opts?: { search_type?: "semantic" | "fulltext"; limit?: number },
): Promise<SearchResultResponse[]> {
  return apiGet<SearchResultResponse[]>("/api/search", {
    query,
    search_type: opts?.search_type ?? "semantic",
    limit: opts?.limit ?? 10,
  });
}
