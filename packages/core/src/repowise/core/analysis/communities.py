"""Community detection on dependency graphs.

Uses Leiden (graspologic) when available, falls back to Louvain (networkx).
Supports both file-level and symbol-level community detection with:
- Oversized community splitting (second pass on communities >25% of graph)
- Cohesion scoring (intra-community edge density)
- Heuristic labeling (dominant directory / keyword analysis)
"""

from __future__ import annotations

import contextlib
import inspect
import io
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import PurePosixPath

import networkx as nx
import structlog

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_COMMUNITY_FRACTION = 0.25
_MIN_SPLIT_SIZE = 10

# Edge types to include when building file-level community subgraph
_FILE_COMMUNITY_EDGE_TYPES = frozenset({
    "imports", "framework", "dynamic", "extends", "implements",
})

# Edge types to include when building symbol-level community subgraph
_SYMBOL_COMMUNITY_EDGE_TYPES = frozenset({
    "calls", "extends", "implements", "has_method",
})

# Generic directory segments excluded from heuristic labeling
_GENERIC_SEGMENTS = frozenset({
    "src", "lib", "core", "common", "shared", "internal", "pkg",
    "main", "app", "utils", "helpers", "index", "mod",
})

# Keywords checked in filename stems for fallback labeling
_LABEL_KEYWORDS = (
    "api", "auth", "model", "service", "handler", "router", "db",
    "cache", "worker", "util", "test", "config", "middleware", "schema",
    "controller", "view", "store", "hook", "plugin", "adapter",
)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class CommunityInfo:
    """Metadata for a single detected community."""

    community_id: int
    label: str
    members: list[str]
    size: int
    cohesion: float
    dominant_language: str


# ---------------------------------------------------------------------------
# Output suppression (Windows PowerShell 5.1 ANSI fix)
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def _suppress_graspologic_output():
    """Suppress stdout/stderr during graspologic calls.

    graspologic's leiden() emits ANSI escape sequences that corrupt
    PowerShell 5.1's scroll buffer on Windows.
    """
    old_stderr = sys.stderr
    try:
        sys.stderr = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()):
            yield
    finally:
        sys.stderr = old_stderr


# ---------------------------------------------------------------------------
# Partition (Leiden / Louvain)
# ---------------------------------------------------------------------------


def _partition(G: nx.Graph) -> tuple[dict, str]:
    """Run community detection. Returns ({node: community_id}, algorithm_name).

    Tries Leiden (graspologic) first, falls back to Louvain (networkx).
    """
    try:
        from graspologic.partition import leiden

        with _suppress_graspologic_output():
            result = leiden(G)
        return result, "leiden"
    except ImportError:
        pass

    # Fallback: networkx Louvain
    kwargs: dict = {"seed": 42, "threshold": 1e-4}
    if "max_level" in inspect.signature(nx.community.louvain_communities).parameters:
        kwargs["max_level"] = 10

    communities = nx.community.louvain_communities(G, **kwargs)
    assignment = {node: cid for cid, nodes in enumerate(communities) for node in nodes}
    return assignment, "louvain"


# ---------------------------------------------------------------------------
# Oversized community splitting
# ---------------------------------------------------------------------------


def _split_community(
    G: nx.Graph, nodes: list[str],
) -> list[list[str]]:
    """Run a second partition pass on an oversized community subgraph."""
    subgraph = G.subgraph(nodes)
    if subgraph.number_of_edges() == 0:
        return [[n] for n in sorted(nodes)]
    try:
        sub_partition, _ = _partition(subgraph)
        sub_communities: dict[int, list[str]] = {}
        for node, cid in sub_partition.items():
            sub_communities.setdefault(cid, []).append(node)
        if len(sub_communities) <= 1:
            return [sorted(nodes)]
        return [sorted(v) for v in sub_communities.values()]
    except Exception:
        return [sorted(nodes)]


def _split_oversized(
    G: nx.Graph,
    communities: dict[int, list[str]],
    max_fraction: float = _MAX_COMMUNITY_FRACTION,
    min_split_size: int = _MIN_SPLIT_SIZE,
) -> list[list[str]]:
    """Split any community exceeding max_fraction of total nodes."""
    total = sum(len(v) for v in communities.values())
    max_size = max(min_split_size, int(total * max_fraction))

    result: list[list[str]] = []
    for nodes in communities.values():
        if len(nodes) > max_size:
            result.extend(_split_community(G, nodes))
        else:
            result.append(nodes)
    return result


# ---------------------------------------------------------------------------
# Cohesion scoring
# ---------------------------------------------------------------------------


def _cohesion_score(G: nx.Graph, community_nodes: list[str]) -> float:
    """Ratio of actual intra-community edges to maximum possible."""
    n = len(community_nodes)
    if n <= 1:
        return 1.0
    subgraph = G.subgraph(community_nodes)
    actual = subgraph.number_of_edges()
    possible = n * (n - 1) / 2
    return round(actual / possible, 4) if possible > 0 else 0.0


# ---------------------------------------------------------------------------
# Heuristic labeling
# ---------------------------------------------------------------------------


def _heuristic_label(member_paths: list[str], community_id: int) -> str:
    """Derive a human-readable label from member file paths."""
    if not member_paths:
        return f"cluster_{community_id}"

    # Strategy 1: dominant directory segment
    seg_counter: Counter[str] = Counter()
    for path in member_paths:
        parts = PurePosixPath(path).parts
        for part in parts[:-1]:  # exclude filename
            lower = part.lower()
            if lower not in _GENERIC_SEGMENTS and len(lower) > 1:
                seg_counter[lower] += 1

    if seg_counter:
        best_seg, best_count = seg_counter.most_common(1)[0]
        if best_count / len(member_paths) > 0.6:
            return best_seg

    # Strategy 2: keyword frequency in filenames
    stem_counter: Counter[str] = Counter()
    for path in member_paths:
        stem = PurePosixPath(path).stem.lower()
        for kw in _LABEL_KEYWORDS:
            if kw in stem:
                stem_counter[kw] += 1

    if stem_counter:
        best_kw, best_kw_count = stem_counter.most_common(1)[0]
        if best_kw_count / len(member_paths) > 0.4:
            return best_kw

    # Strategy 3: most common top-level directory
    top_dirs: Counter[str] = Counter()
    for path in member_paths:
        parts = PurePosixPath(path).parts
        if len(parts) > 1:
            top_dirs[parts[0]] += 1

    if top_dirs:
        return top_dirs.most_common(1)[0][0]

    return f"cluster_{community_id}"


def _dominant_language(
    members: list[str], graph: nx.DiGraph,
) -> str:
    """Find the most common language among community members."""
    lang_counter: Counter[str] = Counter()
    for node_id in members:
        data = graph.nodes.get(node_id, {})
        lang = data.get("language")
        if lang and lang != "unknown":
            lang_counter[lang] += 1
    if lang_counter:
        return lang_counter.most_common(1)[0][0]
    return "unknown"


# ---------------------------------------------------------------------------
# File-level community detection
# ---------------------------------------------------------------------------


def detect_file_communities(
    graph: nx.DiGraph,
) -> tuple[dict[str, int], dict[int, CommunityInfo], str]:
    """Detect communities among file nodes.

    Returns:
        (file_assignment, communities_info, algorithm_used)
        - file_assignment: {file_path: community_id}
        - communities_info: {community_id: CommunityInfo}
        - algorithm_used: "leiden" or "louvain"
    """
    # Extract file nodes (exclude external nodes — they're structural noise)
    file_nodes = [
        n for n, d in graph.nodes(data=True)
        if d.get("node_type", "file") == "file"
    ]

    if not file_nodes:
        return {}, {}, "none"

    # Build undirected subgraph with relevant edges only
    undirected = nx.Graph()
    undirected.add_nodes_from(file_nodes)

    for u, v, d in graph.edges(data=True):
        edge_type = d.get("edge_type", "imports")
        if edge_type in _FILE_COMMUNITY_EDGE_TYPES and u in undirected and v in undirected:
            if not undirected.has_edge(u, v):
                undirected.add_edge(u, v)

    # Separate isolates
    isolates = [n for n in undirected.nodes() if undirected.degree(n) == 0]
    connected = [n for n in undirected.nodes() if undirected.degree(n) > 0]

    raw_communities: dict[int, list[str]] = {}
    algorithm = "none"

    if connected:
        connected_subgraph = undirected.subgraph(connected)
        partition, algorithm = _partition(connected_subgraph)

        for node, cid in partition.items():
            raw_communities.setdefault(cid, []).append(node)

    # Each isolate gets its own community
    next_cid = max(raw_communities.keys(), default=-1) + 1
    for node in isolates:
        raw_communities[next_cid] = [node]
        next_cid += 1

    # Split oversized communities
    split_lists = _split_oversized(undirected, raw_communities)

    # Re-index by size descending for deterministic ordering
    split_lists.sort(key=len, reverse=True)

    # Build final assignment and info
    file_assignment: dict[str, int] = {}
    communities_info: dict[int, CommunityInfo] = {}

    for cid, members in enumerate(split_lists):
        sorted_members = sorted(members)
        for node in sorted_members:
            file_assignment[node] = cid

        communities_info[cid] = CommunityInfo(
            community_id=cid,
            label=_heuristic_label(sorted_members, cid),
            members=sorted_members,
            size=len(sorted_members),
            cohesion=_cohesion_score(undirected, sorted_members),
            dominant_language=_dominant_language(sorted_members, graph),
        )

    log.info(
        "file_communities_detected",
        total_files=len(file_nodes),
        communities=len(communities_info),
        algorithm=algorithm,
    )

    return file_assignment, communities_info, algorithm


# ---------------------------------------------------------------------------
# Symbol-level community detection
# ---------------------------------------------------------------------------


def detect_symbol_communities(graph: nx.DiGraph) -> dict[str, int]:
    """Detect communities among symbol nodes using calls/heritage edges.

    Returns {symbol_id: community_id}.
    """
    symbol_nodes = [
        n for n, d in graph.nodes(data=True)
        if d.get("node_type") == "symbol"
    ]

    if not symbol_nodes:
        return {}

    # Build undirected subgraph from call/heritage edges only
    symbol_set = frozenset(symbol_nodes)
    undirected = nx.Graph()
    undirected.add_nodes_from(symbol_nodes)

    for u, v, d in graph.edges(data=True):
        edge_type = d.get("edge_type")
        if (
            edge_type in _SYMBOL_COMMUNITY_EDGE_TYPES
            and u in symbol_set
            and v in symbol_set
        ):
            if not undirected.has_edge(u, v):
                undirected.add_edge(u, v)

    # Separate isolates
    connected = [n for n in undirected.nodes() if undirected.degree(n) > 0]

    if not connected:
        # No edges — each symbol is its own community
        return {sym: i for i, sym in enumerate(sorted(symbol_nodes))}

    connected_subgraph = undirected.subgraph(connected)
    partition, _ = _partition(connected_subgraph)

    # Build communities dict for re-indexing
    raw: dict[int, list[str]] = {}
    for node, cid in partition.items():
        raw.setdefault(cid, []).append(node)

    # Assign isolates
    next_cid = max(raw.keys(), default=-1) + 1
    isolates = [n for n in undirected.nodes() if undirected.degree(n) == 0]
    for node in isolates:
        raw[next_cid] = [node]
        next_cid += 1

    # Re-index by size descending
    ordered = sorted(raw.values(), key=len, reverse=True)
    result: dict[str, int] = {}
    for cid, members in enumerate(ordered):
        for node in members:
            result[node] = cid

    log.info(
        "symbol_communities_detected",
        total_symbols=len(symbol_nodes),
        connected=len(connected),
        communities=len(ordered),
    )

    return result
