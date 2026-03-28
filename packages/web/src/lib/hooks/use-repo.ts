"use client";

import useSWR from "swr";
import { listRepos, getRepo } from "@/lib/api/repos";
import type { RepoResponse } from "@/lib/api/types";

export function useRepos() {
  const { data, error, isLoading, mutate } = useSWR<RepoResponse[]>(
    "repos",
    () => listRepos(),
    { refreshInterval: 30_000 },
  );
  return { repos: data ?? [], error, isLoading, mutate };
}

export function useRepo(repoId: string | null) {
  const { data, error, isLoading, mutate } = useSWR<RepoResponse>(
    repoId ? `repo:${repoId}` : null,
    () => getRepo(repoId!),
    { refreshInterval: 30_000 },
  );
  return { repo: data, error, isLoading, mutate };
}
