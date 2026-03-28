import { apiGet } from "./client";
import type { SymbolResponse } from "./types";

export interface SymbolListParams {
  repo_id: string;
  q?: string;
  kind?: string;
  language?: string;
  limit?: number;
  offset?: number;
}

export async function listSymbols(params: SymbolListParams): Promise<SymbolResponse[]> {
  const p: Record<string, string | number | boolean | undefined> = { ...params };
  return apiGet<SymbolResponse[]>("/api/symbols", p);
}

export async function lookupSymbolByName(
  name: string,
  repoId: string,
): Promise<SymbolResponse[]> {
  return apiGet<SymbolResponse[]>(`/api/symbols/by-name/${encodeURIComponent(name)}`, {
    repo_id: repoId,
  });
}

export async function getSymbolById(symbolDbId: string): Promise<SymbolResponse> {
  return apiGet<SymbolResponse>(`/api/symbols/${encodeURIComponent(symbolDbId)}`);
}
