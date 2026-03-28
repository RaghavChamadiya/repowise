"use client";

import useSWR from "swr";
import {
  getArchitectureGraph,
  getDeadCodeGraph,
  getEgoGraph,
  getGraph,
  getHotFilesGraph,
  getModuleGraph,
} from "@/lib/api/graph";
import type {
  DeadCodeGraphResponse,
  EgoGraphResponse,
  GraphExportResponse,
  HotFilesGraphResponse,
  ModuleGraphResponse,
} from "@/lib/api/types";

const SWR_OPTS = { revalidateOnFocus: false, revalidateOnReconnect: false };

export function useGraph(repoId: string | null) {
  const { data, error, isLoading } = useSWR<GraphExportResponse>(
    repoId ? `graph:${repoId}` : null,
    () => getGraph(repoId!),
    SWR_OPTS,
  );
  return { graph: data, error, isLoading };
}

export function useModuleGraph(repoId: string | null) {
  const { data, error, isLoading } = useSWR<ModuleGraphResponse>(
    repoId ? `module-graph:${repoId}` : null,
    () => getModuleGraph(repoId!),
    SWR_OPTS,
  );
  return { graph: data, error, isLoading };
}

export function useEgoGraph(repoId: string | null, nodeId: string | null, hops = 2) {
  const { data, error, isLoading } = useSWR<EgoGraphResponse>(
    repoId && nodeId ? `ego-graph:${repoId}:${nodeId}:${hops}` : null,
    () => getEgoGraph(repoId!, nodeId!, hops),
    SWR_OPTS,
  );
  return { graph: data, error, isLoading };
}

export function useArchitectureGraph(repoId: string | null) {
  const { data, error, isLoading } = useSWR<GraphExportResponse>(
    repoId ? `arch-graph:${repoId}` : null,
    () => getArchitectureGraph(repoId!),
    SWR_OPTS,
  );
  return { graph: data, error, isLoading };
}

export function useDeadCodeGraph(repoId: string | null) {
  const { data, error, isLoading } = useSWR<DeadCodeGraphResponse>(
    repoId ? `dead-graph:${repoId}` : null,
    () => getDeadCodeGraph(repoId!),
    SWR_OPTS,
  );
  return { graph: data, error, isLoading };
}

export function useHotFilesGraph(repoId: string | null, days = 30, limit = 25) {
  const { data, error, isLoading } = useSWR<HotFilesGraphResponse>(
    repoId ? `hot-graph:${repoId}:${days}:${limit}` : null,
    () => getHotFilesGraph(repoId!, days, limit),
    SWR_OPTS,
  );
  return { graph: data, error, isLoading };
}
