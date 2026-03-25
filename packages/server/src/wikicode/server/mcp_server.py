"""WikiCode MCP Server — 8 tools for AI coding assistants.

Exposes the full WikiCode wiki as queryable tools via the MCP protocol.
Supports both stdio transport (Claude Code, Cursor, Cline) and SSE transport
(web-based MCP clients).

Usage:
    wikicode mcp --transport stdio  # for Claude Code / Cursor / Cline
    wikicode mcp --transport sse    # for web-based clients
"""

from __future__ import annotations

import asyncio
import json
import os
import os.path
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.fastmcp import FastMCP
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from wikicode.core.persistence.database import get_session, init_db
from wikicode.core.persistence.embedder import MockEmbedder
from wikicode.core.persistence.models import (
    DeadCodeFinding,
    DecisionRecord,
    GitMetadata,
    GraphEdge,
    GraphNode,
    Page,
    Repository,
    WikiSymbol,
)
from wikicode.core.persistence.search import FullTextSearch
from wikicode.core.persistence.vector_store import InMemoryVectorStore

# ---------------------------------------------------------------------------
# Shared state (set during lifespan)
# ---------------------------------------------------------------------------

_session_factory: async_sessionmaker[AsyncSession] | None = None
_vector_store: Any = None
_decision_store: Any = None
_fts: Any = None
_repo_path: str | None = None


def _resolve_embedder():
    """Resolve embedder from WIKICODE_EMBEDDER env var or .wikicode/config.yaml."""
    name = os.environ.get("WIKICODE_EMBEDDER", "").lower()
    if not name and _repo_path:
        try:
            from pathlib import Path

            cfg_path = Path(_repo_path) / ".wikicode" / "config.yaml"
            if cfg_path.exists():
                import yaml

                cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
                name = (cfg.get("embedder") or "").lower()
        except Exception:
            pass
    if name == "gemini":
        try:
            from wikicode.core.persistence.gemini_embedder import GeminiEmbedder

            dims = int(os.environ.get("WIKICODE_EMBEDDING_DIMS", "768"))
            return GeminiEmbedder(output_dimensionality=dims)
        except Exception:
            pass
    if name == "openai":
        try:
            from wikicode.core.persistence.openai_embedder import OpenAIEmbedder

            model = os.environ.get("WIKICODE_EMBEDDING_MODEL", "text-embedding-3-small")
            return OpenAIEmbedder(model=model)
        except Exception:
            pass
    return MockEmbedder()


@asynccontextmanager
async def _lifespan(server: FastMCP):
    """Initialize DB engine, session factory, vector store, FTS on startup."""
    global _session_factory, _vector_store, _decision_store, _fts  # noqa: PLW0603

    db_url = os.environ.get(
        "WIKICODE_DATABASE_URL", "sqlite+aiosqlite:///wikicode.db"
    )

    # If a repo path was configured, try .wikicode/wiki.db
    if _repo_path:
        from pathlib import Path
        import logging as _logging

        _log = _logging.getLogger("wikicode.mcp")
        wikicode_dir = Path(_repo_path) / ".wikicode"
        if not wikicode_dir.exists():
            _log.warning(
                "No .wikicode directory at %s — run 'wikicode init' first",
                _repo_path,
            )
        elif not (wikicode_dir / "wiki.db").exists():
            _log.warning(
                "No wiki.db in %s — run 'wikicode init' to generate the wiki",
                wikicode_dir,
            )
        if wikicode_dir.exists():
            db_path = wikicode_dir / "wiki.db"
            if db_path.exists():
                db_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"

    connect_args: dict = {}
    if db_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    engine = create_async_engine(db_url, connect_args=connect_args)
    await init_db(engine)

    _session_factory = async_sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )

    _fts = FullTextSearch(engine)
    await _fts.ensure_index()

    # Resolve real embedder from env/config instead of always using MockEmbedder
    embedder = _resolve_embedder()
    _vector_store = InMemoryVectorStore(embedder=embedder)

    # Try to load LanceDB if available
    try:
        from wikicode.core.persistence.vector_store import LanceDBVectorStore

        if _repo_path:
            from pathlib import Path

            lance_dir = Path(_repo_path) / ".wikicode" / "lancedb"
            if lance_dir.exists():
                _vector_store = LanceDBVectorStore(
                    str(lance_dir), embedder=embedder
                )
                _decision_store = LanceDBVectorStore(
                    str(lance_dir), embedder=embedder, table_name="decision_records"
                )
    except ImportError:
        pass

    if _decision_store is None:
        _decision_store = InMemoryVectorStore(embedder=embedder)

    yield

    await engine.dispose()
    await _vector_store.close()
    if _decision_store is not None:
        await _decision_store.close()


# ---------------------------------------------------------------------------
# Create the MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "WikiCode",
    instructions=(
        "WikiCode is a codebase documentation engine. Use these tools to query "
        "the wiki for architecture overviews, contextual docs on files/modules/"
        "symbols, modification risk assessment, architectural decision rationale, "
        "semantic search, dependency paths, dead code, and architecture diagrams."
    ),
    lifespan=_lifespan,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CODE_EXTS = frozenset({
    ".py", ".ts", ".js", ".go", ".rs", ".java", ".tsx", ".jsx",
    ".rb", ".kt", ".cpp", ".c", ".h", ".cs", ".swift", ".scala",
})


async def _get_repo(session: AsyncSession, repo: str | None = None) -> Repository:
    """Resolve a repository — by path, by ID, or return the first one."""
    if repo:
        # Try by path
        result = await session.execute(
            select(Repository).where(Repository.local_path == repo)
        )
        obj = result.scalar_one_or_none()
        if obj:
            return obj
        # Try by ID
        obj = await session.get(Repository, repo)
        if obj:
            return obj
        # Try by name
        result = await session.execute(
            select(Repository).where(Repository.name == repo)
        )
        obj = result.scalar_one_or_none()
        if obj:
            return obj
        raise LookupError(f"Repository not found: {repo}")

    # Default: return the first (and often only) repository
    result = await session.execute(select(Repository).limit(1))
    obj = result.scalar_one_or_none()
    if obj is None:
        raise LookupError(
            "No repositories found. Run 'wikicode init' first."
        )
    return obj


def _is_path(query: str) -> bool:
    """Heuristic: does this string look like a file or module path?"""
    if "/" in query:
        return True
    _, ext = os.path.splitext(query)
    return ext in _CODE_EXTS


# ---------------------------------------------------------------------------
# Tool 1: get_overview (unchanged)
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_overview(repo: str | None = None) -> dict:
    """Get the repository overview: architecture summary, module map, key entry points.

    Best first call when starting to explore an unfamiliar codebase.

    Args:
        repo: Repository path, name, or ID. Omit if only one repo exists.
    """
    async with get_session(_session_factory) as session:
        repository = await _get_repo(session, repo)

        # Get repo overview page
        result = await session.execute(
            select(Page).where(
                Page.repository_id == repository.id,
                Page.page_type == "repo_overview",
            )
        )
        overview_page = result.scalar_one_or_none()

        # Get architecture diagram page
        result = await session.execute(
            select(Page).where(
                Page.repository_id == repository.id,
                Page.page_type == "architecture_diagram",
            )
        )
        arch_page = result.scalar_one_or_none()

        # Get module pages
        result = await session.execute(
            select(Page)
            .where(
                Page.repository_id == repository.id,
                Page.page_type == "module_page",
            )
            .order_by(Page.title)
        )
        module_pages = result.scalars().all()

        # Get entry point files from graph nodes
        result = await session.execute(
            select(GraphNode).where(
                GraphNode.repository_id == repository.id,
                GraphNode.is_entry_point == True,  # noqa: E712
            )
        )
        entry_nodes = result.scalars().all()

        return {
            "title": overview_page.title if overview_page else repository.name,
            "content_md": overview_page.content if overview_page else "No overview generated yet.",
            "architecture_diagram_mermaid": arch_page.content if arch_page else None,
            "key_modules": [
                {
                    "name": p.title,
                    "path": p.target_path,
                    "description": p.content[:200] + "..." if len(p.content) > 200 else p.content,
                }
                for p in module_pages
            ],
            "entry_points": [n.node_id for n in entry_nodes],
        }


# ---------------------------------------------------------------------------
# Tool 2: get_context (NEW — replaces 5 tools)
# ---------------------------------------------------------------------------


async def _resolve_one_target(
    session: AsyncSession,
    repository: Repository,
    target: str,
    include: set[str] | None,
) -> dict:
    """Resolve a single target and return its full context."""
    repo_id = repository.id
    result_data: dict[str, Any] = {}

    # --- Determine target type ---
    # 1. Try file page (most common)
    page_id = f"file_page:{target}"
    page = await session.get(Page, page_id)
    target_type = None
    file_path_for_git: str | None = None

    if page and page.repository_id == repo_id:
        target_type = "file"
        file_path_for_git = target
    else:
        # 2. Try module page
        res = await session.execute(
            select(Page).where(
                Page.repository_id == repo_id,
                Page.page_type == "module_page",
                Page.target_path == target,
            )
        )
        page = res.scalar_one_or_none()
        if page is None:
            # Partial match fallback for modules
            res = await session.execute(
                select(Page).where(
                    Page.repository_id == repo_id,
                    Page.page_type == "module_page",
                    Page.target_path.contains(target),
                )
            )
            page = res.scalar_one_or_none()
        if page:
            target_type = "module"
        else:
            # 3. Try symbol (exact then fuzzy)
            res = await session.execute(
                select(WikiSymbol).where(
                    WikiSymbol.repository_id == repo_id,
                    WikiSymbol.name == target,
                )
            )
            sym_matches = list(res.scalars().all())
            if not sym_matches:
                res = await session.execute(
                    select(WikiSymbol).where(
                        WikiSymbol.repository_id == repo_id,
                        WikiSymbol.name.ilike(f"%{target}%"),
                    ).limit(10)
                )
                sym_matches = list(res.scalars().all())
            if sym_matches:
                target_type = "symbol"
                file_path_for_git = sym_matches[0].file_path
            else:
                # 4. Try file page by target_path search
                res = await session.execute(
                    select(Page).where(
                        Page.repository_id == repo_id,
                        Page.page_type == "file_page",
                        Page.target_path == target,
                    )
                )
                page = res.scalar_one_or_none()
                if page:
                    target_type = "file"
                    file_path_for_git = target

    if target_type is None:
        return {"target": target, "error": f"Target not found: '{target}'"}

    result_data["target"] = target
    result_data["type"] = target_type

    # --- Docs ---
    if include is None or "docs" in include:
        docs: dict[str, Any] = {}
        if target_type == "file":
            docs["title"] = page.title
            docs["content_md"] = page.content
            # Symbols in this file
            res = await session.execute(
                select(WikiSymbol).where(
                    WikiSymbol.repository_id == repo_id,
                    WikiSymbol.file_path == target,
                )
            )
            symbols = res.scalars().all()
            docs["symbols"] = [
                {"name": s.name, "kind": s.kind, "signature": s.signature}
                for s in symbols
            ]
            # Importers
            res = await session.execute(
                select(GraphEdge).where(
                    GraphEdge.repository_id == repo_id,
                    GraphEdge.target_node_id == target,
                )
            )
            importers = res.scalars().all()
            docs["imported_by"] = [e.source_node_id for e in importers]

        elif target_type == "module":
            docs["title"] = page.title
            docs["content_md"] = page.content
            # Child file pages
            res = await session.execute(
                select(Page).where(
                    Page.repository_id == repo_id,
                    Page.page_type == "file_page",
                    Page.target_path.like(f"{page.target_path}%"),
                )
            )
            file_pages = res.scalars().all()
            docs["files"] = [
                {
                    "path": f.target_path,
                    "description": f.title,
                    "confidence_score": f.confidence,
                }
                for f in file_pages
            ]

        elif target_type == "symbol":
            sym = sym_matches[0]  # type: ignore[possibly-undefined]
            docs["name"] = sym.name
            docs["qualified_name"] = sym.qualified_name
            docs["kind"] = sym.kind
            docs["signature"] = sym.signature
            docs["file_path"] = sym.file_path
            docs["docstring"] = sym.docstring or ""
            # File page content as documentation
            sym_page_id = f"file_page:{sym.file_path}"
            sym_page = await session.get(Page, sym_page_id)
            docs["documentation"] = sym_page.content if sym_page else ""
            # Used by
            res = await session.execute(
                select(GraphEdge).where(
                    GraphEdge.repository_id == repo_id,
                    GraphEdge.target_node_id == sym.file_path,
                )
            )
            edges = res.scalars().all()
            docs["used_by"] = [e.source_node_id for e in edges][:20]
            # Candidates
            if len(sym_matches) > 1:  # type: ignore[possibly-undefined]
                docs["candidates"] = [
                    {"name": m.name, "kind": m.kind, "file_path": m.file_path}
                    for m in sym_matches[1:5]  # type: ignore[possibly-undefined]
                ]

        result_data["docs"] = docs

    # --- Ownership ---
    if include is None or "ownership" in include:
        ownership: dict[str, Any] = {}
        git_path = file_path_for_git
        if target_type == "module" and page:
            git_path = page.target_path
        if git_path:
            res = await session.execute(
                select(GitMetadata).where(
                    GitMetadata.repository_id == repo_id,
                    GitMetadata.file_path == git_path,
                )
            )
            meta = res.scalar_one_or_none()
            if meta:
                ownership["primary_owner"] = meta.primary_owner_name
                ownership["owner_pct"] = meta.primary_owner_commit_pct
                ownership["contributor_count"] = len(json.loads(meta.top_authors_json))
            else:
                ownership["primary_owner"] = None
                ownership["owner_pct"] = None
                ownership["contributor_count"] = 0
        else:
            ownership["primary_owner"] = None
            ownership["owner_pct"] = None
            ownership["contributor_count"] = 0
        result_data["ownership"] = ownership

    # --- Last change ---
    if include is None or "last_change" in include:
        last_change: dict[str, Any] = {}
        git_path = file_path_for_git
        if target_type == "module" and page:
            git_path = page.target_path
        if git_path:
            res = await session.execute(
                select(GitMetadata).where(
                    GitMetadata.repository_id == repo_id,
                    GitMetadata.file_path == git_path,
                )
            )
            meta = res.scalar_one_or_none()
            if meta:
                last_change["date"] = meta.last_commit_at.isoformat() if meta.last_commit_at else None
                last_change["author"] = meta.primary_owner_name
                last_change["days_ago"] = meta.age_days
            else:
                last_change["date"] = None
                last_change["author"] = None
                last_change["days_ago"] = None
        else:
            last_change["date"] = None
            last_change["author"] = None
            last_change["days_ago"] = None
        result_data["last_change"] = last_change

    # --- Decisions ---
    if include is None or "decisions" in include:
        res = await session.execute(
            select(DecisionRecord).where(
                DecisionRecord.repository_id == repo_id,
            )
        )
        all_decisions = res.scalars().all()
        governing = []
        for d in all_decisions:
            affected_files = json.loads(d.affected_files_json)
            affected_modules = json.loads(d.affected_modules_json)
            if target in affected_files or target in affected_modules:
                governing.append({
                    "id": d.id,
                    "title": d.title,
                    "status": d.status,
                    "decision": d.decision,
                    "rationale": d.rationale,
                    "confidence": d.confidence,
                })
            elif file_path_for_git and file_path_for_git in affected_files:
                governing.append({
                    "id": d.id,
                    "title": d.title,
                    "status": d.status,
                    "decision": d.decision,
                    "rationale": d.rationale,
                    "confidence": d.confidence,
                })
        result_data["decisions"] = governing

    # --- Freshness ---
    if include is None or "freshness" in include:
        freshness: dict[str, Any] = {}
        if page:
            freshness["confidence_score"] = page.confidence
            freshness["freshness_status"] = page.freshness_status
            freshness["is_stale"] = (page.confidence or 1.0) < 0.6
        elif target_type == "symbol" and file_path_for_git:
            sym_page_id = f"file_page:{file_path_for_git}"
            sym_page = await session.get(Page, sym_page_id)
            if sym_page:
                freshness["confidence_score"] = sym_page.confidence
                freshness["freshness_status"] = sym_page.freshness_status
                freshness["is_stale"] = (sym_page.confidence or 1.0) < 0.6
            else:
                freshness["confidence_score"] = None
                freshness["freshness_status"] = None
                freshness["is_stale"] = None
        else:
            freshness["confidence_score"] = None
            freshness["freshness_status"] = None
            freshness["is_stale"] = None
        result_data["freshness"] = freshness

    return result_data


@mcp.tool()
async def get_context(
    targets: list[str],
    include: list[str] | None = None,
    repo: str | None = None,
) -> dict:
    """Get complete context for one or more targets (files, modules, or symbols).

    Pass ALL relevant targets in a single call rather than calling this tool
    multiple times. Each target is resolved automatically — pass file paths
    like "src/auth/service.py", module paths like "src/auth", or symbol names
    like "AuthService".

    Example: get_context(["src/auth/service.py", "src/auth/middleware.py", "AuthService"])

    Optional `include` parameter filters response fields:
    ["docs", "ownership", "last_change", "decisions", "freshness"]
    Default: all fields returned.

    Args:
        targets: List of file paths, module paths, or symbol names to look up.
        include: Optional list of fields to include. Default returns all.
        repo: Repository path, name, or ID.
    """
    include_set = set(include) if include else None

    async with get_session(_session_factory) as session:
        repository = await _get_repo(session, repo)

        results = await asyncio.gather(*[
            _resolve_one_target(session, repository, t, include_set)
            for t in targets
        ])

    return {
        "targets": {r["target"]: r for r in results},
    }


# ---------------------------------------------------------------------------
# Tool 3: get_risk (NEW — replaces 3 tools)
# ---------------------------------------------------------------------------


async def _assess_one_target(
    session: AsyncSession,
    repository: Repository,
    target: str,
    all_edge_map: dict[str, int],
    import_links: dict[str, set[str]],
) -> dict:
    """Assess risk for a single target file."""
    repo_id = repository.id
    result_data: dict[str, Any] = {"target": target}

    # Git metadata
    res = await session.execute(
        select(GitMetadata).where(
            GitMetadata.repository_id == repo_id,
            GitMetadata.file_path == target,
        )
    )
    meta = res.scalar_one_or_none()

    if meta is None:
        result_data["hotspot_score"] = 0.0
        result_data["dependents_count"] = all_edge_map.get(target, 0)
        result_data["co_change_partners"] = []
        result_data["primary_owner"] = None
        result_data["owner_pct"] = None
        result_data["risk_summary"] = f"{target} — no git metadata available"
        return result_data

    hotspot_score = meta.churn_percentile or 0.0
    dep_count = all_edge_map.get(target, 0)

    # Co-change partners
    partners = json.loads(meta.co_change_partners_json)
    import_related = import_links.get(target, set())
    co_changes = [
        {
            "file_path": p.get("file_path", p.get("path", "")),
            "count": p.get("co_change_count", p.get("count", 0)),
            "has_import_link": p.get("file_path", p.get("path", "")) in import_related,
        }
        for p in partners
    ]

    owner = meta.primary_owner_name or "unknown"
    pct = meta.primary_owner_commit_pct or 0.0

    result_data["hotspot_score"] = hotspot_score
    result_data["dependents_count"] = dep_count
    result_data["co_change_partners"] = co_changes
    result_data["primary_owner"] = owner
    result_data["owner_pct"] = pct
    result_data["risk_summary"] = (
        f"{target} — hotspot score {hotspot_score:.0%}, {dep_count} dependents, "
        f"{len(co_changes)} co-change partners, owned {pct:.0%} by {owner}"
    )

    return result_data


@mcp.tool()
async def get_risk(
    targets: list[str],
    repo: str | None = None,
) -> dict:
    """Assess modification risk for one or more files before making changes.

    Pass ALL files you plan to modify in a single call. Returns hotspot
    score, dependents, co-change partners, and a plain-English risk summary
    for each target, plus the top 5 global hotspots for ambient awareness.

    Example: get_risk(["src/auth/service.py", "src/auth/middleware.py"])

    Args:
        targets: List of file paths to assess.
        repo: Repository path, name, or ID.
    """
    async with get_session(_session_factory) as session:
        repository = await _get_repo(session, repo)
        repo_id = repository.id

        # Pre-load edge counts (dependents = incoming edges)
        res = await session.execute(
            select(GraphEdge).where(
                GraphEdge.repository_id == repo_id,
            )
        )
        all_edges = res.scalars().all()
        dep_counts: dict[str, int] = {}
        import_links: dict[str, set[str]] = {}
        for e in all_edges:
            dep_counts[e.target_node_id] = dep_counts.get(e.target_node_id, 0) + 1
            import_links.setdefault(e.source_node_id, set()).add(e.target_node_id)
            import_links.setdefault(e.target_node_id, set()).add(e.source_node_id)

        # Assess each target
        results = await asyncio.gather(*[
            _assess_one_target(session, repository, t, dep_counts, import_links)
            for t in targets
        ])

        # Global hotspots (excluding requested targets)
        target_set = set(targets)
        res = await session.execute(
            select(GitMetadata)
            .where(
                GitMetadata.repository_id == repo_id,
                GitMetadata.is_hotspot == True,  # noqa: E712
            )
            .order_by(GitMetadata.churn_percentile.desc())
            .limit(len(targets) + 5)
        )
        all_hotspots = res.scalars().all()
        global_hotspots = [
            {
                "file_path": h.file_path,
                "hotspot_score": h.churn_percentile,
                "primary_owner": h.primary_owner_name,
            }
            for h in all_hotspots
            if h.file_path not in target_set
        ][:5]

    return {
        "targets": {r["target"]: r for r in results},
        "global_hotspots": global_hotspots,
    }


# ---------------------------------------------------------------------------
# Tool 4: get_why (refactored — 3 modes)
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_why(
    query: str | None = None,
    repo: str | None = None,
) -> dict:
    """Understand why code is built the way it is, using architectural decision records.

    Three modes:
    1. get_why("why is auth using JWT?") — semantic search over decisions
    2. get_why("src/auth/service.py") — all decisions governing a specific file
    3. get_why() — decision health dashboard: stale decisions, ungoverned hotspots

    Always call this before making architectural changes.

    Args:
        query: Natural language question, file/module path, or omit for health dashboard.
        repo: Repository path, name, or ID.
    """
    # --- Mode 1: No query → health dashboard ---
    if not query:
        from wikicode.core.persistence.crud import get_decision_health_summary

        async with get_session(_session_factory) as session:
            repository = await _get_repo(session, repo)
            health = await get_decision_health_summary(session, repository.id)

        stale = health["stale_decisions"]
        proposed = health["proposed_awaiting_review"]
        ungoverned = health["ungoverned_hotspots"]

        return {
            "mode": "health",
            "summary": (
                f"{health['summary'].get('active', 0)} active · "
                f"{health['summary'].get('stale', 0)} stale · "
                f"{len(proposed)} proposed · "
                f"{len(ungoverned)} ungoverned hotspots"
            ),
            "counts": health["summary"],
            "stale_decisions": [
                {
                    "id": d.id,
                    "title": d.title,
                    "staleness_score": d.staleness_score,
                    "affected_files": json.loads(d.affected_files_json)[:5],
                }
                for d in stale[:10]
            ],
            "proposed_awaiting_review": [
                {
                    "id": d.id,
                    "title": d.title,
                    "source": d.source,
                    "confidence": d.confidence,
                }
                for d in proposed[:10]
            ],
            "ungoverned_hotspots": ungoverned[:15],
        }

    # --- Mode 2: Path → decisions governing that path ---
    if _is_path(query):
        async with get_session(_session_factory) as session:
            repository = await _get_repo(session, repo)
            res = await session.execute(
                select(DecisionRecord).where(
                    DecisionRecord.repository_id == repository.id,
                )
            )
            all_decisions = res.scalars().all()

        governing = []
        for d in all_decisions:
            affected_files = json.loads(d.affected_files_json)
            affected_modules = json.loads(d.affected_modules_json)
            if query in affected_files or query in affected_modules:
                governing.append({
                    "id": d.id,
                    "title": d.title,
                    "status": d.status,
                    "context": d.context,
                    "decision": d.decision,
                    "rationale": d.rationale,
                    "alternatives": json.loads(d.alternatives_json),
                    "consequences": json.loads(d.consequences_json),
                    "affected_files": affected_files,
                    "source": d.source,
                    "confidence": d.confidence,
                    "staleness_score": d.staleness_score,
                })

        return {
            "mode": "path",
            "path": query,
            "decisions": governing,
        }

    # --- Mode 3: Natural language → search ---
    from wikicode.core.persistence.crud import list_decisions as _list_decisions

    async with get_session(_session_factory) as session:
        repository = await _get_repo(session, repo)
        all_decisions = await _list_decisions(
            session, repository.id, include_proposed=True, limit=200
        )

    # Keyword scoring
    query_lower = query.lower()
    query_words = set(query_lower.split())
    scored_decisions = []
    for d in all_decisions:
        text = f"{d.title} {d.decision} {d.rationale}".lower()
        match_count = sum(1 for w in query_words if w in text)
        if match_count > 0:
            scored_decisions.append((match_count, d))
    scored_decisions.sort(key=lambda t: t[0], reverse=True)
    keyword_matches = [d for _, d in scored_decisions[:5]]

    # Semantic search over decision vector store
    decision_results = []
    try:
        decision_results = await _decision_store.search(query, limit=5)
    except Exception:
        pass

    # Semantic search over documentation
    doc_results = []
    try:
        doc_results = await _vector_store.search(query, limit=3)
    except Exception:
        try:
            doc_results = await _fts.search(query, limit=3)
        except Exception:
            pass

    # Merge keyword matches with semantic results (dedup by ID)
    seen_ids: set[str] = set()
    merged_decisions = []
    for d in keyword_matches:
        if d.id not in seen_ids:
            seen_ids.add(d.id)
            merged_decisions.append({
                "id": d.id,
                "title": d.title,
                "status": d.status,
                "decision": d.decision,
                "rationale": d.rationale,
                "consequences": json.loads(d.consequences_json),
                "affected_files": json.loads(d.affected_files_json),
                "source": d.source,
                "confidence": d.confidence,
            })

    for r in decision_results:
        if r.page_id not in seen_ids:
            seen_ids.add(r.page_id)
            merged_decisions.append({
                "id": r.page_id,
                "title": r.title,
                "snippet": r.snippet,
                "relevance_score": r.score,
            })

    return {
        "mode": "search",
        "query": query,
        "decisions": merged_decisions[:8],
        "related_documentation": [
            {
                "page_id": r.page_id,
                "title": r.title,
                "page_type": r.page_type,
                "snippet": r.snippet,
                "relevance_score": r.score,
            }
            for r in doc_results[:3]
        ],
    }


# ---------------------------------------------------------------------------
# Tool 5: search_codebase (unchanged)
# ---------------------------------------------------------------------------


@mcp.tool()
async def search_codebase(
    query: str,
    limit: int = 5,
    page_type: str | None = None,
    repo: str | None = None,
) -> dict:
    """Semantic search over the full wiki. Ask in natural language.

    Args:
        query: Natural language search query (e.g. "how does authentication work?").
        limit: Maximum results to return (default 5).
        page_type: Optional filter by page type (file_page, module_page, etc.).
        repo: Repository path, name, or ID.
    """
    async with get_session(_session_factory) as session:
        # Ensure repo exists
        await _get_repo(session, repo)

    # Try semantic search first, fall back to fulltext
    results = []
    try:
        results = await _vector_store.search(query, limit=limit)
    except Exception:
        pass
    if not results:
        try:
            results = await _fts.search(query, limit=limit)
        except Exception:
            pass

    output = []
    for r in results:
        if page_type and r.page_type != page_type:
            continue
        output.append(
            {
                "page_id": r.page_id,
                "title": r.title,
                "page_type": r.page_type,
                "snippet": r.snippet,
                "relevance_score": r.score,
                "confidence_score": getattr(r, "confidence", None),
            }
        )

    return {"results": output[:limit]}


# ---------------------------------------------------------------------------
# Tool 6: get_dependency_path (unchanged)
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_dependency_path(
    source: str, target: str, repo: str | None = None
) -> dict:
    """Find how two files/modules are connected in the dependency graph.

    Args:
        source: Source file or module path.
        target: Target file or module path.
        repo: Repository path, name, or ID.
    """
    async with get_session(_session_factory) as session:
        repository = await _get_repo(session, repo)

        result = await session.execute(
            select(GraphEdge).where(
                GraphEdge.repository_id == repository.id,
            )
        )
        edges = result.scalars().all()

    try:
        import networkx as nx
    except ImportError:
        return {"error": "networkx not available for path queries"}

    G = nx.DiGraph()
    for e in edges:
        G.add_edge(e.source_node_id, e.target_node_id)

    if source not in G:
        return {"error": f"Source node '{source}' not found in graph"}
    if target not in G:
        return {"error": f"Target node '{target}' not found in graph"}

    try:
        path = nx.shortest_path(G, source, target)
    except nx.NetworkXNoPath:
        return {"path": [], "distance": -1, "explanation": "No path found"}

    # Build path with relationships
    path_with_info = []
    for i, node in enumerate(path):
        relationship = ""
        if i < len(path) - 1:
            relationship = "imports"
        path_with_info.append({"node": node, "relationship": relationship})

    return {
        "path": path_with_info,
        "distance": len(path) - 1,
        "explanation": f"Shortest path from {source} to {target} has {len(path) - 1} hops",
    }


# ---------------------------------------------------------------------------
# Tool 7: get_dead_code (unchanged)
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_dead_code(
    repo: str | None = None,
    kind: str | None = None,
    min_confidence: float = 0.5,
    safe_only: bool = False,
    limit: int = 20,
) -> dict:
    """Get dead and unused code findings. Use before cleanup tasks.

    Results sorted by confidence desc, then lines desc (biggest wins first).

    Args:
        repo: Repository path, name, or ID.
        kind: Filter by kind (unreachable_file, unused_export, unused_internal, zombie_package).
        min_confidence: Minimum confidence threshold (default 0.6).
        safe_only: Only return findings marked safe_to_delete (default false).
        limit: Maximum findings to return (default 20).
    """
    async with get_session(_session_factory) as session:
        repository = await _get_repo(session, repo)

        query = (
            select(DeadCodeFinding)
            .where(
                DeadCodeFinding.repository_id == repository.id,
                DeadCodeFinding.status == "open",
                DeadCodeFinding.confidence >= min_confidence,
            )
            .order_by(DeadCodeFinding.confidence.desc(), DeadCodeFinding.lines.desc())
        )

        if kind:
            query = query.where(DeadCodeFinding.kind == kind)

        result = await session.execute(query)
        findings = list(result.scalars().all())

        if safe_only:
            findings = [f for f in findings if f.safe_to_delete]

        findings = findings[:limit]

        # Compute summary
        all_result = await session.execute(
            select(DeadCodeFinding).where(
                DeadCodeFinding.repository_id == repository.id,
                DeadCodeFinding.status == "open",
            )
        )
        all_findings = list(all_result.scalars().all())

        by_kind: dict[str, int] = {}
        for f in all_findings:
            by_kind[f.kind] = by_kind.get(f.kind, 0) + 1

        return {
            "summary": {
                "total_findings": len(all_findings),
                "deletable_lines": sum(f.lines for f in all_findings if f.safe_to_delete),
                "safe_to_delete_count": sum(1 for f in all_findings if f.safe_to_delete),
                "by_kind": by_kind,
            },
            "findings": [
                {
                    "kind": f.kind,
                    "file_path": f.file_path,
                    "symbol_name": f.symbol_name,
                    "confidence": f.confidence,
                    "reason": f.reason,
                    "safe_to_delete": f.safe_to_delete,
                    "lines": f.lines,
                    "last_commit_at": f.last_commit_at.isoformat() if f.last_commit_at else None,
                    "primary_owner": f.primary_owner,
                    "age_days": f.age_days,
                }
                for f in findings
            ],
        }


# ---------------------------------------------------------------------------
# Tool 8: get_architecture_diagram (unchanged)
# ---------------------------------------------------------------------------


@mcp.tool()
async def get_architecture_diagram(
    scope: str = "repo",
    path: str | None = None,
    diagram_type: str = "auto",
    repo: str | None = None,
) -> dict:
    """Get a Mermaid diagram for the codebase or a specific module.

    Args:
        scope: "repo", "module", or "file".
        path: Module or file path (required for module/file scope).
        diagram_type: "auto", "flowchart", "class", or "sequence".
        repo: Repository path, name, or ID.
    """
    async with get_session(_session_factory) as session:
        repository = await _get_repo(session, repo)

        if scope == "repo":
            # Return the architecture diagram page
            result = await session.execute(
                select(Page).where(
                    Page.repository_id == repository.id,
                    Page.page_type == "architecture_diagram",
                )
            )
            page = result.scalar_one_or_none()
            if page:
                return {
                    "diagram_type": diagram_type if diagram_type != "auto" else "flowchart",
                    "mermaid_syntax": page.content,
                    "description": page.title,
                }

        # For module/file scope or fallback, build diagram from graph
        if path:
            filter_prefix = path
        else:
            filter_prefix = ""

        result = await session.execute(
            select(GraphNode).where(
                GraphNode.repository_id == repository.id,
                GraphNode.node_id.like(f"{filter_prefix}%") if filter_prefix else GraphNode.repository_id == repository.id,
            )
        )
        nodes = result.scalars().all()

        result = await session.execute(
            select(GraphEdge).where(
                GraphEdge.repository_id == repository.id,
            )
        )
        edges = result.scalars().all()

        node_ids = {n.node_id for n in nodes}
        relevant_edges = [
            e for e in edges
            if e.source_node_id in node_ids or e.target_node_id in node_ids
        ]

        # Build Mermaid flowchart
        lines = ["graph TD"]
        seen_nodes = set()
        for e in relevant_edges[:50]:  # Limit to 50 edges for readability
            src = e.source_node_id.replace("/", "_").replace(".", "_").replace("-", "_")
            tgt = e.target_node_id.replace("/", "_").replace(".", "_").replace("-", "_")
            if src not in seen_nodes:
                lines.append(f'    {src}["{e.source_node_id}"]')
                seen_nodes.add(src)
            if tgt not in seen_nodes:
                lines.append(f'    {tgt}["{e.target_node_id}"]')
                seen_nodes.add(tgt)
            lines.append(f"    {src} --> {tgt}")

        mermaid = "\n".join(lines) if len(lines) > 1 else "graph TD\n    A[No graph data available]"

        return {
            "diagram_type": diagram_type if diagram_type != "auto" else "flowchart",
            "mermaid_syntax": mermaid,
            "description": f"Dependency graph for {scope}: {path or 'entire repo'}",
        }


# ---------------------------------------------------------------------------
# Server runner
# ---------------------------------------------------------------------------


def create_mcp_server(repo_path: str | None = None) -> FastMCP:
    """Create and return the MCP server instance, optionally scoped to a repo."""
    global _repo_path  # noqa: PLW0603
    _repo_path = repo_path
    return mcp


def run_mcp(
    transport: str = "stdio",
    repo_path: str | None = None,
    port: int = 7338,
) -> None:
    """Run the MCP server with the specified transport."""
    global _repo_path  # noqa: PLW0603
    _repo_path = repo_path

    if transport == "sse":
        mcp.settings.port = port
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")
