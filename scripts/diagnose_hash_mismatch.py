#!/usr/bin/env python3
"""Diagnose source_hash mismatches between wiki.db and fresh renders.

Usage:
    cd ~/forge/free-code
    python3.11 ~/forge/repowise/scripts/diagnose_hash_mismatch.py [--max-pages N]

What it checks:
  A) dep_summaries (completed_page_summaries) — empty on re-run (level 0/1 skipped)
  B) graph edge ordering — non-deterministic due to ProcessPoolExecutor + as_completed
  C) betweenness_centrality — random sampling when n > 30000 nodes
  D) community_id — Louvain seed=42, should be stable
  E) git history via git_meta — NOT passed to assemble_file_page (won't affect hash)
"""
from __future__ import annotations

import argparse
import asyncio
import difflib
import hashlib
import sqlite3
import sys
from pathlib import Path

REPOWISE_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPOWISE_ROOT / "packages" / "core" / "src"))
sys.path.insert(0, str(REPOWISE_ROOT / "packages" / "cli" / "src"))


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


async def _build_pipeline(repo_path: Path):
    """Run ingestion + graph, return (parsed_files, source_map, graph_builder)."""
    from repowise.core.pipeline.orchestrator import _run_ingestion
    parsed_files, file_infos, repo_structure, source_map, graph_builder = \
        await _run_ingestion(repo_path, exclude_patterns=None, skip_tests=False,
                             skip_infra=False, progress=None)
    return parsed_files, source_map, graph_builder


def _render_file_page_prompt(pf, graph, pagerank, betweenness, community,
                              source_map, page_summaries, assembler, jinja_env):
    ctx = assembler.assemble_file_page(
        pf, graph, pagerank, betweenness, community,
        source_map.get(pf.file_info.path, b""),
        page_summaries=page_summaries,
    )
    return jinja_env.get_template("file_page.j2").render(ctx=ctx), ctx


async def main(repo_path: Path, max_pages: int, verbose: bool) -> None:
    # --- Load cached pages from wiki.db ---
    db_path = repo_path / ".repowise" / "wiki.db"
    if not db_path.exists():
        print(f"ERROR: wiki.db not found at {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, target_path, source_hash FROM wiki_pages "
        "WHERE page_type = 'file_page' ORDER BY RANDOM() LIMIT ?",
        (max_pages,),
    ).fetchall()
    conn.close()
    print(f"Loaded {len(rows)} random file_page(s) from wiki.db.\n")

    # --- Run ingestion TWICE to detect non-determinism ---
    print("Run 1: ingestion pipeline...")
    p1, sm1, gb1 = await _build_pipeline(repo_path)
    print(f"  {len(p1)} files parsed.")

    print("Run 2: ingestion pipeline (repeat to check stability)...")
    p2, sm2, gb2 = await _build_pipeline(repo_path)
    print(f"  {len(p2)} files parsed.\n")

    # --- Compare graph properties between runs ---
    g1, g2 = gb1.graph(), gb2.graph()
    pr1, pr2 = gb1.pagerank(), gb2.pagerank()
    bc1, bc2 = gb1.betweenness_centrality(), gb2.betweenness_centrality()
    cm1, cm2 = gb1.community_detection(), gb2.community_detection()

    # Check edge ordering stability
    edge_order_unstable: list[str] = []
    for node in list(g1.nodes())[:200]:
        succ1 = list(g1.successors(node))
        succ2 = list(g2.successors(node))
        if succ1 != succ2:
            edge_order_unstable.append(node)

    bc_diff = {k for k in bc1 if abs(bc1[k] - bc2.get(k, 0)) > 1e-9}
    cm_diff = {k for k in cm1 if cm1[k] != cm2.get(k)}
    pr_diff = {k for k in pr1 if abs(pr1[k] - pr2.get(k, 0)) > 1e-9}

    print("=== Stability check (Run 1 vs Run 2) ===")
    print(f"  Graph nodes:        {g1.number_of_nodes()} vs {g2.number_of_nodes()}")
    print(f"  Graph edges:        {g1.number_of_edges()} vs {g2.number_of_edges()}")
    _ok = lambda n: "[ok]" if n == 0 else f"[!!] {n} differ"
    print(f"  Edge ordering:      {_ok(len(edge_order_unstable))}"
          + (f" e.g. {edge_order_unstable[:2]}" if edge_order_unstable else ""))
    print(f"  PageRank:           {_ok(len(pr_diff))}")
    print(f"  BetweennessCentral: {_ok(len(bc_diff))}")
    print(f"  Community detect:   {_ok(len(cm_diff))}")
    print()

    # --- Render prompts and compare with stored hashes ---
    from repowise.core.generation import ContextAssembler, GenerationConfig
    import jinja2

    config = GenerationConfig()
    assembler = ContextAssembler(config)
    templates_dir = REPOWISE_ROOT / "packages" / "core" / "src" / \
        "repowise" / "core" / "generation" / "templates"
    jinja_env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(templates_dir)),
        undefined=jinja2.StrictUndefined, autoescape=False,
    )

    path_to_pf = {pf.file_info.path: pf for pf in p1}
    graph, pagerank, betweenness, community = g1, pr1, bc1, cm1

    print("=== Hash comparison (wiki.db vs fresh render) ===")
    matches = mismatches_dep = mismatches_other = 0

    for row in rows:
        page_id    = row["id"]
        tpath      = row["target_path"]
        stored_hash = row["source_hash"]
        pf = path_to_pf.get(tpath)
        if pf is None:
            print(f"  [skip] {tpath}: not found in parsed files")
            continue

        # Render without dep_summaries (re-run scenario, level 0/1 skipped)
        prompt_nodep, ctx = _render_file_page_prompt(
            pf, graph, pagerank, betweenness, community, sm1,
            page_summaries=None, assembler=assembler, jinja_env=jinja_env,
        )
        hash_nodep = _sha256(prompt_nodep)

        if hash_nodep == stored_hash:
            matches += 1
            print(f"  [MATCH]        {tpath}")
            continue

        # Check if edge ordering is the issue: render with run 2's graph
        prompt_run2, _ = _render_file_page_prompt(
            path_to_pf.get(tpath) or pf,
            g2, pr2, bc2, cm2, sm2,
            page_summaries=None, assembler=assembler, jinja_env=jinja_env,
        )
        hash_run2 = _sha256(prompt_run2)
        edge_order_issue = (hash_nodep != hash_run2)

        # Check if dep_summaries explain the mismatch:
        # inject dummy summaries for all out-edges
        out_edges = list(graph.successors(tpath)) if tpath in graph else []
        out_edges = [e for e in out_edges if not e.startswith("external:")]
        fake_summaries = {dep: f"[summary of {dep}]" for dep in out_edges}
        prompt_fakedep, _ = _render_file_page_prompt(
            pf, graph, pagerank, betweenness, community, sm1,
            page_summaries=fake_summaries, assembler=assembler, jinja_env=jinja_env,
        )
        hash_fakedep = _sha256(prompt_fakedep)
        dep_affects = (prompt_nodep != prompt_fakedep)

        if dep_affects:
            mismatches_dep += 1
            cause = "dep_summaries differ"
        else:
            mismatches_other += 1
            cause = "unknown — dep_summaries do NOT affect prompt"

        if edge_order_issue:
            cause += " + edge-ordering non-deterministic"

        print(f"  [MISMATCH]     {tpath}")
        print(f"    cause:         {cause}")
        print(f"    stored:        {stored_hash[:20]}...")
        print(f"    fresh(nodep):  {hash_nodep[:20]}...")
        print(f"    fresh(run2):   {hash_run2[:20]}...")
        print(f"    out_edges:     {len(out_edges)}  dep_affects_prompt: {dep_affects}")

        if verbose:
            # Show first real diff between stored prompt and fresh prompt
            # We can't reconstruct the exact stored prompt, but we can diff run1 vs run2
            diff = list(difflib.unified_diff(
                prompt_nodep.splitlines(),
                prompt_run2.splitlines(),
                fromfile="run1", tofile="run2", lineterm="", n=1,
            ))
            if diff:
                print("    -- prompt diff run1 vs run2 (first 20 lines) --")
                for line in diff[:20]:
                    print(f"      {line}")
            else:
                print("    -- prompts are identical across runs (edge order stable) --")

    print()
    print("=== Summary ===")
    print(f"  Match (empty dep_summaries = stored):  {matches}")
    print(f"  Mismatch caused by dep_summaries:      {mismatches_dep}")
    print(f"  Mismatch with unknown cause:           {mismatches_other}")
    total = matches + mismatches_dep + mismatches_other
    print(f"  Total checked:                         {total}")

    if mismatches_dep and not mismatches_other:
        print("\nCONCLUSION: dep_summaries (completed_page_summaries from level 0/1)")
        print("  is the sole cause. Fix: pre-populate from wiki.db before level 2.")
    elif mismatches_other:
        print("\nCONCLUSION: at least one other factor causes hash instability.")
        print("  Run with --verbose to see prompt diffs.")
    elif matches == total:
        print("\nCONCLUSION: all hashes match on empty dep_summaries — no other instability.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("repo_path", nargs="?", default=".", help="Repo path (default: cwd)")
    ap.add_argument("--max-pages", type=int, default=10)
    ap.add_argument("--verbose", action="store_true", help="Show prompt diffs")
    args = ap.parse_args()
    asyncio.run(main(Path(args.repo_path).resolve(), args.max_pages, args.verbose))
