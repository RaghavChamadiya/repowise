import { apiGet } from "./client";
import type {
  GitMetadataResponse,
  HotspotResponse,
  OwnershipEntry,
  GitSummaryResponse,
} from "./types";

export async function getGitMetadata(
  repoId: string,
  filePath: string,
): Promise<GitMetadataResponse> {
  return apiGet<GitMetadataResponse>(`/api/repos/${repoId}/git-metadata`, {
    file_path: filePath,
  });
}

export async function getHotspots(
  repoId: string,
  limit = 20,
): Promise<HotspotResponse[]> {
  return apiGet<HotspotResponse[]>(`/api/repos/${repoId}/hotspots`, { limit });
}

export async function getOwnership(
  repoId: string,
  granularity: "file" | "module" = "module",
): Promise<OwnershipEntry[]> {
  return apiGet<OwnershipEntry[]>(`/api/repos/${repoId}/ownership`, { granularity });
}

export async function getCoChanges(
  repoId: string,
  filePath: string,
  minCount = 3,
): Promise<{ file_path: string; co_change_partners: Array<{ file_path: string; co_change_count: number }> }> {
  return apiGet(`/api/repos/${repoId}/co-changes`, {
    file_path: filePath,
    min_count: minCount,
  });
}

export async function getGitSummary(repoId: string): Promise<GitSummaryResponse> {
  return apiGet<GitSummaryResponse>(`/api/repos/${repoId}/git-summary`);
}
