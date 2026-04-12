"""Shared graph query utilities used by both MCP tools and REST routers.

This module avoids duplicating BFS trace logic and community-meta parsing
across `tool_flows.py` and `routers/graph.py`.
"""

from __future__ import annotations

import json
from collections import deque
from typing import Any

from repowise.core.persistence.crud import (
    get_graph_edges_for_node,
    get_graph_nodes_by_ids,
)
from repowise.core.persistence.models import GraphNode


def parse_community_meta(node: GraphNode) -> dict[str, Any]:
    """Safely parse ``community_meta_json`` from a GraphNode."""
    try:
        return json.loads(node.community_meta_json or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}


def community_label(node: GraphNode) -> str:
    """Extract human-readable community label, falling back to 'cluster_N'."""
    meta = parse_community_meta(node)
    return meta.get("label") or f"cluster_{node.community_id}"


def community_cohesion(node: GraphNode) -> float:
    """Extract cohesion score from community_meta_json."""
    meta = parse_community_meta(node)
    return float(meta.get("cohesion", 0.0) or 0.0)


def entry_point_score(node: GraphNode) -> float:
    """Extract entry_point_score from community_meta_json (symbol nodes only)."""
    meta = parse_community_meta(node)
    return float(meta.get("entry_point_score", 0.0) or 0.0)


def percentile_rank(value: float, all_values: list[float]) -> int:
    """Compute the percentile rank (0–100) of *value* within *all_values*."""
    if not all_values:
        return 0
    count_below = sum(1 for v in all_values if v < value)
    return round(100.0 * count_below / len(all_values))


async def bfs_trace(
    session: Any,
    repo_id: str,
    entry_id: str,
    max_depth: int,
    node_cache: dict[str, GraphNode] | None = None,
) -> list[str]:
    """BFS trace from *entry_id* following ``calls`` edges.

    Returns an ordered list of symbol IDs in the trace.  Uses greedy
    successor ordering (highest confidence first for the primary path)
    and a visited set for cycle safety.
    """
    if node_cache is None:
        node_cache = {}

    trace: list[str] = [entry_id]
    visited: set[str] = {entry_id}
    queue: deque[tuple[str, int]] = deque([(entry_id, 0)])

    while queue:
        current, depth = queue.popleft()
        if depth >= max_depth:
            continue

        edges = await get_graph_edges_for_node(
            session,
            repo_id,
            current,
            direction="callees",
            edge_types=["calls"],
            limit=20,
        )

        successors: list[tuple[str, float]] = []
        for e in edges:
            if e.target_node_id not in visited:
                successors.append((e.target_node_id, e.confidence or 0.0))

        successors.sort(key=lambda x: -x[1])

        for target_id, _ in successors:
            if target_id in visited:
                continue
            visited.add(target_id)
            trace.append(target_id)
            queue.append((target_id, depth + 1))

    return trace


async def resolve_trace_communities(
    session: Any,
    repo_id: str,
    trace: list[str],
    node_cache: dict[str, GraphNode],
) -> tuple[list[int], bool]:
    """Resolve community IDs for trace nodes.

    Returns ``(communities_visited, crosses_community)``.
    """
    missing = [nid for nid in trace if nid not in node_cache]
    if missing:
        batch = await get_graph_nodes_by_ids(session, repo_id, missing)
        node_cache.update(batch)

    communities_visited: list[int] = []
    seen: set[int] = set()
    for nid in trace:
        n = node_cache.get(nid)
        cid = n.community_id if n else 0
        if cid is not None and cid not in seen:
            seen.add(cid)
            communities_visited.append(cid)

    return communities_visited, len(communities_visited) > 1
