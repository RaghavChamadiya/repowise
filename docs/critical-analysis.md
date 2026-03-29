# Repowise — Critical Analysis

An honest assessment of what Repowise solves, where it can fail, how likely those failures are, and what would make it better.

---

## Table of Contents

1. [What Problem Does Repowise Solve?](#1-what-problem-does-repowise-solve)
2. [How Useful Is It?](#2-how-useful-is-it)
3. [Where the Architecture Can Fail](#3-where-the-architecture-can-fail)
4. [Improvement Suggestions](#4-improvement-suggestions)

---

## 1. What Problem Does Repowise Solve?

### The core problem: Code knowledge is invisible and perishable

When a developer joins a team, they face a codebase with thousands of files and no map. They ask:

- "What does this file do?" → Read the code, guess, or interrupt someone.
- "Why is it built this way?" → Nobody remembers. The original author left.
- "If I change this, what breaks?" → No way to know without deep expertise.
- "What's dead code vs critical infrastructure?" → Looks the same in the file tree.

This knowledge exists — scattered across git history, code comments, Slack threads, and people's heads. But it's not **accessible** at the moment of need.

### What Repowise does about it

Repowise automates the creation and maintenance of codebase intelligence:

| Problem | Repowise Solution | How |
|---------|-------------------|-----|
| No documentation | Auto-generated wiki pages | Tree-sitter parsing + LLM generation |
| Don't know what's important | PageRank scoring | Graph algorithms on import dependencies |
| Don't know who owns what | Ownership tracking | Git blame + commit history analysis |
| Don't know what's risky to change | Risk assessment | Churn × centrality × bus factor |
| Don't know what's dead | Dead code detection | Graph reachability + git activity |
| Don't know why decisions were made | Decision archaeology | Inline markers + git commit mining + README extraction |
| Documentation goes stale | Incremental updates | Change detection + cascade propagation |
| AI assistants lack codebase context | MCP tools | 8 specialized tools for Claude Code, Cursor, etc. |

### What makes it non-trivial

Many tools generate documentation. Repowise's differentiators are:

1. **Graph-aware intelligence.** It doesn't just document files — it understands how they connect. PageRank identifies what matters. Betweenness identifies bottlenecks. Communities identify subsystems. This structural understanding drives everything from doc priority to risk assessment.

2. **Temporal intelligence.** Git history adds a time dimension. A file's importance isn't just structural (who imports it) but behavioral (how often it changes, who touches it, what changes alongside it). Co-change detection finds coupling invisible in the import graph.

3. **Decision archaeology.** No other tool automatically discovers *why* code is built the way it is by mining commits, comments, and documentation. This is the hardest kind of knowledge to preserve and the most valuable.

4. **Incremental maintenance with cascade.** The cascade algorithm is genuinely clever — it propagates staleness through the dependency graph with a bounded budget, ensuring the most important docs stay fresh without unbounded cost.

---

## 2. How Useful Is It?

### High value scenarios

| Scenario | Value | Why |
|----------|-------|-----|
| New developer onboarding | **Very High** | Replaces weeks of "reading code and asking questions" with searchable documentation, architecture diagrams, and ownership maps |
| Pre-refactor impact analysis | **Very High** | `get_risk` tells you exactly what depends on what you're changing, who owns it, and how volatile it is — before you touch anything |
| AI-assisted development | **High** | MCP tools give Claude Code / Cursor deep codebase context. Instead of the AI guessing, it queries real docs, ownership, and decisions |
| Dead code cleanup | **High** | Automated detection with confidence tiers saves engineering time. The "safe to delete" flag reduces review burden |
| Knowledge preservation | **High** | When senior developers leave, their decision rationale is captured in the wiki and decision records instead of leaving with them |
| Code review context | **Medium** | Reviewer can check the wiki for file context, ownership, and governing decisions before reviewing a PR |
| Compliance and auditing | **Medium** | Decision records with provenance (source, evidence commits, confidence) provide audit trails |

### Moderate value scenarios

| Scenario | Value | Limitation |
|----------|-------|-----------|
| Small repos (< 50 files) | **Low** | You can read 50 files yourself. The overhead of running Repowise isn't justified. |
| Rapidly prototyping repos | **Low** | Code changes so fast that documentation is stale within hours. The incremental system helps but can't keep up with constant rewrites. |
| Non-code-heavy repos | **Low** | Repos that are mostly config, data, or documentation get little value from AST parsing and dependency graphs. |

### Quantitative value estimate

For a **500-file repo with 10 developers**:

```
Without Repowise:
  New developer onboarding: ~2 weeks of asking questions
  Finding file owners: ~10 min per file (git blame, asking around)
  Pre-refactor impact: ~1-2 hours of manual grep + tracing
  Dead code discovery: ~1-2 days of manual audit per quarter

With Repowise:
  New developer onboarding: ~2 days reading wiki + using search
  Finding file owners: instant (ownership data in every page)
  Pre-refactor impact: ~30 seconds (get_risk tool call)
  Dead code discovery: instant (pre-computed with confidence tiers)

Time saved per developer per quarter: ~15-25 hours
For 10 developers: ~150-250 hours/quarter
```

The ROI depends on the LLM cost of `repowise init` (potentially $5-50 depending on provider and repo size) versus the engineering hours saved.

---

## 3. Where the Architecture Can Fail

### Failure Category 1: Data Consistency (Three-Store Split)

**The problem:** Repowise writes to three independent stores — SQL, vector store, and graph — without atomic transactions across them. They can get out of sync.

**Failure scenario:**

```
1. LLM generates page content          ✓
2. Embed in vector store                ✓
3. Upsert in SQL database               ✗ (database connection drops)
4. Index in FTS                          (never reached)

State: Vector store has the page. SQL doesn't. FTS doesn't.
Result: Semantic search finds the page, but clicking it returns 404.
```

**Reverse scenario:**

```
1. LLM generates page content          ✓
2. Embed in vector store                ✗ (embedding API timeout)
3. Upsert in SQL database               ✓
4. Index in FTS                          ✓

State: SQL and FTS have the page. Vector store doesn't.
Result: Keyword search works. Semantic search misses the page.
```

**Probability: Medium (5-15% over a large init run).** Vector store embedding involves an external API call (OpenAI/Gemini). Over hundreds of pages, at least one is likely to fail. The failure is silent (logged at debug level), so the user may not notice.

**Impact: Low-Medium.** Individual pages missing from one store doesn't break the system — it degrades search quality. But the user has no way to detect or repair the inconsistency.

**Why it happens:** True distributed transactions across SQLite + LanceDB + an embedding API are impractical. The architecture prioritizes availability (keep going if one store fails) over consistency (all stores agree).

---

### Failure Category 2: LLM Output Quality

**The problem:** Generated documentation is only as good as the LLM's understanding. The LLM sees assembled context (symbols, imports, source code snippets), not the running system.

**Failure scenarios:**

| Scenario | Probability | Impact |
|----------|------------|--------|
| LLM hallucinates function behavior that doesn't match the code | **Medium (10-20%)** | Misleading docs. Developer trusts wiki and writes incorrect code. |
| LLM misunderstands complex metaprogramming, decorators, or dynamic dispatch | **High (30%+)** for such files | Missing or wrong symbol documentation |
| LLM generates vague "this module handles X" without specifics | **Medium (15-25%)** for low-context files | Docs exist but aren't useful |
| LLM fails to converge on architecture diagram | **Low (< 5%)** | Falls back to no diagram |

**Why it's hard to fix:** The LLM doesn't execute the code. It infers behavior from static text. For straightforward code (clear function names, type annotations, docstrings), accuracy is high. For metaprogramming-heavy code (Python decorators that transform functions, Ruby method_missing, JavaScript Proxy objects), the LLM may produce plausible but wrong descriptions.

**Compounding problem:** Once an incorrect doc is embedded in the vector store, it becomes RAG context for other pages. If `auth.py`'s docs incorrectly describe its behavior, `service.py`'s docs (which reference `auth.py` via dependency summaries) inherit the error.

---

### Failure Category 3: Stale Documentation Drift

**The problem:** Even with incremental updates, documentation can drift from reality.

**How staleness accumulates:**

```
Day 1:   repowise init → all docs fresh
Day 3:   Developer changes config.py → cascade updates 30 pages
         But cascade_budget = 30, and 50 pages actually depend on config.py
         20 pages are marked "decay_only" (stale, not regenerated)
Day 5:   Developer changes utils.py → cascade updates 30 different pages
         The 20 stale pages from Day 3 are still stale
Day 10:  Those 20 pages hit staleness_threshold (7 days)
         But nobody runs repowise update again
Day 30:  Those pages hit expiry_threshold and would be regenerated
         IF someone runs repowise update
```

**Probability: High (almost certain) for repos without automated CI integration.** If `repowise update` only runs when a developer remembers to run it, documentation drift is inevitable.

**Impact: Medium.** Stale docs are worse than no docs — they give a false sense of confidence. The freshness indicator (confidence score) mitigates this, but only if developers check it.

---

### Failure Category 4: Graph Accuracy (Import Resolution)

**The problem:** The dependency graph is only as accurate as import resolution. Missed or wrong imports lead to wrong PageRank, wrong cascade propagation, and wrong dead code detection.

**Where import resolution fails:**

| Pattern | Example | What Repowise misses |
|---------|---------|---------------------|
| Dynamic imports | `importlib.import_module(name)` | Entire dependency edge |
| Conditional imports | `if TYPE_CHECKING: import X` | Edge exists but is typing-only, not runtime |
| Re-exports through `__init__.py` | `from .utils import *` | May miss specific names in wildcard |
| Barrel files (TypeScript) | `export * from './module'` | Specific names re-exported |
| Build-time code generation | Protobuf → `_pb2.py` files | Generated files might be gitignored |
| Runtime plugin loading | Django apps, pytest plugins | Framework-mediated imports |
| Monkeypatching | `module.func = my_func` | No import edge at all |

**Probability: Medium-High (20-40% of edges affected in large repos).** Most codebases use some dynamic imports. The more framework-heavy the code (Django, Flask, FastAPI with dependency injection), the more imports are invisible to static analysis.

**Impact cascades:**

```
Missing edge A → B means:
  - A's documentation doesn't mention dependency on B
  - B's PageRank is too low (missing one vote)
  - Changing B doesn't cascade to A's docs (becomes stale silently)
  - B might be falsely flagged as dead code (in_degree appears lower)
```

**Partial mitigation:** Co-change edges partially compensate. If A and B always change together (captured from git history), they get a co-change edge even without an import edge. But co-change edges don't affect PageRank (deliberately excluded).

---

### Failure Category 5: Scale and Performance

**The problem:** Several components are in-memory and O(n²) or worse.

| Component | Complexity | Breaks at | What happens |
|-----------|-----------|-----------|-------------|
| NetworkX graph in memory | O(N + E) memory | ~100K files with dense edges | OOM crash during `graph.build()` |
| Betweenness centrality (exact) | O(N × E) time | >30K nodes | Falls back to sampling (k=500), approximate results |
| PageRank convergence | O(E × iterations) | Unusual graph topologies | `PowerIterationFailedConvergence` → falls back to uniform scores |
| Symbol rename detection | O(removed × added) per file | Files with 500+ symbols | Slow rename detection, but no hard limit |
| InMemory vector search | O(N × D) per query | >10K pages | Seconds per search, kills UX |
| `git log --name-only` | O(commits) | >500K commits | Parsing huge git log output |
| Co-change pair computation | O(files_per_commit²) per commit | Commits touching 100+ files | Quadratic pair generation |

**Probability:**

- For repos < 10K files: **Very Low** (< 1%). Everything fits comfortably.
- For repos 10K-50K files: **Low** (5-10%). Might see betweenness approximation and slower git indexing.
- For repos 50K-100K files: **Medium** (20-30%). Memory pressure on graph, long git indexing times.
- For repos > 100K files: **High** (50%+). Likely needs architectural changes (streaming graph, approximate algorithms, sharded processing).

---

### Failure Category 6: Decision Mining Accuracy

**The problem:** LLM-based decision extraction from git commits and READMEs produces false positives and false negatives.

**False positives (phantom decisions):**

```
Commit: "Migrate test fixtures to new format"
LLM extracts: "Decision: Migrate to new test format"
Reality: This was a routine chore, not an architectural decision
Confidence: 0.70 (git_archaeology)
```

**Probability: Medium (15-25% of git-mined decisions).** The word "migrate" triggers extraction, but not every migration is an architectural decision.

**False negatives (missed decisions):**

```
Commit: "Rewrote the query layer because the ORM couldn't handle
         the new partitioning scheme"
→ Might be missed if commit doesn't use signal keywords
```

Decisions expressed in natural language without keywords like "migrate", "switch to", "replace" won't be found.

**Impact: Medium.** False positives clutter the decision list (proposed status helps — developers can dismiss them). False negatives mean some decisions are invisible (the harder problem).

---

### Failure Category 7: Job System and Resumability

**The problem:** The checkpoint file (JSON on disk) and the database can get out of sync.

**Failure scenario:**

```
1. Page generated successfully
2. job_system.complete_page(job_id, page_id) → JSON file updated ✓
3. Process crashes before session.commit()
4. Database doesn't have the page

On resume:
5. Job checkpoint says page_id is complete (skip it)
6. But database doesn't have it
7. Page is permanently missing
```

**Probability: Low (1-3% per large init run).** Requires a crash between two specific lines. But over hundreds of pages, the window is hit occasionally.

**Impact: Low.** The missing page is a gap in documentation. It won't be regenerated because the checkpoint says it's done. Manual intervention (clearing the checkpoint) is needed.

---

### Failure Category 8: Security and Sensitive Data

**The problem:** Repowise sends source code to external LLM APIs.

| Risk | Probability | Severity |
|------|------------|----------|
| Source code sent to LLM API (Anthropic, OpenAI) includes secrets | **Low** (file size + gitignore filtering helps) | **High** if secrets leak |
| `.env` files parsed and sent as context | **Very Low** (excluded by traverser) | **Critical** |
| API keys in code comments sent to LLM | **Low-Medium** | **High** |
| Generated docs stored in plain text in `.repowise/wiki.db` | **Certain** (by design) | **Medium** (local file, but if shared...) |
| Vector embeddings encode semantic content of code | **Certain** | **Low** (embeddings aren't reversible to code, but contain signal) |

**Mitigation:** Ollama provider supports fully offline operation. For sensitive codebases, this is the only safe option.

---

### Summary: Failure probability matrix

| Failure Category | Probability | Impact | Detection | Recovery |
|-----------------|------------|--------|-----------|----------|
| Three-store inconsistency | Medium | Low-Medium | Hard (silent failures) | Manual re-index |
| LLM hallucination in docs | Medium | Medium | Hard (looks plausible) | Re-generate page |
| Documentation staleness | High | Medium | Easy (confidence score) | Run update |
| Import resolution gaps | Medium-High | Medium | Hard (invisible edges) | None (fundamental limit) |
| Scale/performance limits | Low-High (repo dependent) | High | Easy (OOM, timeout) | Architecture changes |
| Decision mining false positives | Medium | Low | Easy (review proposed) | Dismiss via CLI |
| Job checkpoint desync | Low | Low | Hard (silent gap) | Clear checkpoint |
| Sensitive data exposure | Low | High | Medium (audit logs) | Use Ollama |

---

## 4. Improvement Suggestions

> **Note:** Five of the improvements below have been implemented. They are marked with **(IMPLEMENTED)** and describe what was built rather than what should be built.

### Priority 1: Data Consistency (High impact, Medium effort) — IMPLEMENTED

**Problem:** Three stores can get out of sync.

**Implemented: `repowise doctor --repair`**

The `doctor` command now checks SQL↔Vector Store and SQL↔FTS consistency by comparing page ID sets across all three stores. With `--repair`, it re-embeds missing vector entries, re-indexes missing FTS entries, and deletes orphans. This is powered by new `list_page_ids()` methods on all vector store implementations and `list_indexed_ids()` on FullTextSearch.

**Original suggestion (not yet implemented): Write-ahead log for multi-store writes**

```
Before:
  1. embed_to_vector_store(page)    # may fail
  2. upsert_to_sql(page)            # may fail
  3. index_to_fts(page)             # may fail

After:
  1. write_to_wal(page_id, content, metadata)     # single append
  2. embed_to_vector_store(page)                   # may fail
  3. upsert_to_sql(page)                           # may fail
  4. index_to_fts(page)                            # may fail
  5. mark_wal_entry_complete(page_id)

On startup:
  for entry in wal where not complete:
      retry all three stores
```

This doesn't give you atomic transactions, but it gives you **eventual consistency** — every page that was generated will eventually land in all three stores, even if the process crashes mid-write.

**Simpler alternative:** Add a `repowise doctor --repair` command that compares SQL pages vs vector store entries vs FTS index and re-syncs any mismatches. Not real-time, but catches drift.

### Priority 2: LLM Output Validation (High impact, Low effort) — IMPLEMENTED

**Problem:** LLM output is trusted without validation.

**Implemented:** `_validate_symbol_references()` in `page_generator.py` extracts all backtick-quoted names from generated markdown via regex, cross-checks them against actual symbols, exports, and imports from the ParsedFile. Warnings are logged via structlog and stored in `page.metadata["hallucination_warnings"]`. Common language keywords and builtins are excluded via `_BACKTICK_SKIP`.

**Additional suggestions (not yet implemented):**

1. **Structural validation:** After LLM generates a page, verify it contains expected sections (e.g., file_page should have at least a title and a symbol table). Reject and retry if malformed.

2. **Factual cross-check:** Compare function names in the generated docs against actual symbol names from AST parsing. If the docs reference a function that doesn't exist in the file, flag as hallucination.

   ```python
   actual_symbols = {s.name for s in parsed_file.symbols}
   mentioned_symbols = extract_code_references(generated_content)
   hallucinated = mentioned_symbols - actual_symbols
   if hallucinated:
       log.warning("Possible hallucination", symbols=hallucinated)
       # Option: re-generate with stronger prompt, or add warning to page
   ```

3. **Confidence-weighted display:** Show LLM confidence alongside generated content. Pages generated with "minimal" depth or low-context could display a "low detail" indicator.

### Priority 3: Dynamic Import Detection (High impact, High effort) — PARTIALLY IMPLEMENTED

**Problem:** Static import resolution misses dynamic imports, framework-mediated loading, and plugin systems.

**Implemented:** `add_framework_edges()` on `GraphBuilder` adds synthetic edges with `edge_type="framework"` for four frameworks:
- **pytest**: conftest.py → test files in same/child directories
- **Django**: admin→models, urls→views, forms→models, serializers→models
- **FastAPI**: `include_router()` calls → router modules
- **Flask**: `register_blueprint()` calls → blueprint modules

Framework detection uses regex on source code and the existing `detect_tech_stack()` from manifest files. Called automatically during `repowise init` and `repowise update`.

**Additional suggestions (not yet implemented):**

1. **More framework-aware heuristics:** Additional patterns to detect:

   ```python
   # Django: settings.INSTALLED_APPS → app module imports
   # Flask: app.register_blueprint(bp) → blueprint module
   # FastAPI: app.include_router(router) → router module
   # pytest: conftest.py fixtures → test files using them
   ```

   Each framework pattern is a known import mechanism that can be statically detected even though it's not a Python `import` statement.

2. **Runtime trace integration (optional):** For Python, run `sys.settrace()` during tests to capture actual imports. Merge runtime edges with static edges. This captures every dynamic import that's exercised by tests. Downside: requires running tests, which may be slow or unavailable.

3. **Heuristic edge recovery from co-change:** If two files always co-change AND are in related directories AND have overlapping symbol names, add a weak synthetic import edge. This is noisy but better than nothing for dynamic-import-heavy codebases.

### Priority 4: Scale Architecture (Medium impact, High effort)

**Problem:** In-memory graph, in-memory vector search, and O(n²) algorithms limit scale.

**Suggestions:**

1. **Streaming graph construction:** Instead of building the full NetworkX graph in memory, use a SQLite-backed graph where nodes and edges are stored in tables. Compute metrics incrementally or with SQL-based algorithms.

   ```
   Current:  Build graph in memory → compute metrics → persist to SQLite
   Improved: Build directly in SQLite → compute metrics with SQL queries
                                       (PageRank via iterative SQL)
   ```

2. **Approximate graph metrics at scale:** For repos > 50K files, consider:
   - **PageRank:** Use the power iteration directly on the edge list (no need for full graph in memory). Can be done with SQL or sparse matrix operations.
   - **Betweenness:** Already approximated with sampling. Could use a more efficient algorithm like Brandes' with better sampling strategies.
   - **Communities:** Louvain is already fast. No change needed.

3. **Chunk-based vector search:** Replace InMemoryVectorStore default with LanceDB even for small repos. LanceDB handles scaling internally with IVF-PQ indexes. The in-memory implementation should be test-only.

4. **Parallel git indexing with process pool:** The current ThreadPoolExecutor(20) is limited by Python's GIL for CPU-bound work and GitPython's thread safety for I/O. Consider using `multiprocessing` for git operations, or calling `git log` as a subprocess and parsing output.

### Priority 5: Staleness Prevention (Medium impact, Medium effort) — PARTIALLY IMPLEMENTED

**Problem:** Documentation drifts if nobody runs `repowise update`.

**Suggestions:**

1. **CI/CD integration as first-class:** Provide a GitHub Action and GitLab CI template that runs `repowise update` on every push to main. This makes maintenance automatic rather than opt-in.

   ```yaml
   # .github/workflows/repowise.yml
   on:
     push:
       branches: [main]
   jobs:
     update-docs:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
           with: { fetch-depth: 0 }
         - run: pip install repowise-cli
         - run: repowise update --cascade-budget 50
         - run: repowise serve --export  # publish to static site
   ```

2. **Staleness alerts in CLAUDE.md:** When generating CLAUDE.md, include a staleness summary:

   ```markdown
   ⚠ 15 pages are stale (last updated > 7 days ago)
   Run `repowise update` to refresh documentation.
   ```

   AI coding assistants reading CLAUDE.md would see this and could suggest running an update.

3. **Smarter cascade budgeting — IMPLEMENTED:** `compute_adaptive_budget()` in `change_detector.py` scales budget by change magnitude: 1 file→10, 2-5→30, 6+→min(n×3, 50). Hard cap at 50. The `--cascade-budget` CLI flag defaults to auto when unset, and users can still override manually.

### Priority 6: Decision System Refinement (Medium impact, Low effort)

**Problem:** False positives in git archaeology; no user feedback loop.

**Suggestions:**

1. **Feedback-weighted confidence:** When a developer dismisses a proposed decision (via `repowise decision dismiss`), record the false positive pattern. Over time, learn which commit message patterns produce false positives and lower their confidence.

   ```
   Dismissed: "Migrate test fixtures to new format" (git_archaeology)
   Pattern learned: "migrate" + "test" + "fixture" → lower confidence by 0.15
   ```

2. **Decision coverage in file pages:** When generating a file_page, include a section on governing decisions. This surfaces decisions where developers actually need them — in the documentation for the file they're about to modify.

3. **Decision expiry:** Auto-deprecate decisions that haven't been confirmed and have high staleness scores for > 90 days. Currently decisions stay "active" forever unless manually changed.

### Priority 7: Observability and Repair (Low impact, Low effort) — IMPLEMENTED

**Problem:** Failures are silent. Users don't know when something is degraded.

**Implemented:**

1. **`repowise doctor --repair`:** Extended with three-store consistency checks (SQL↔Vector, SQL↔FTS) and automated repair (re-embed, re-index, delete orphans). See Priority 1.

2. **Generation report:** `GenerationReport` dataclass in `report.py` with `render_report()` prints a rich table after `repowise update` showing: pages by type, input/output/cached tokens, estimated cost, elapsed time, stale page count, hallucination warning count, and decisions extracted.

**Not yet implemented:**

3. **Structured error log:** `.repowise/errors.json` with timestamped, categorized errors. The `doctor` command would read this to suggest repairs.

### Priority 8: Testing and Validation (Low impact, High effort)

**Suggestions:**

1. **Golden test suite:** For 3-5 well-known open source repos (different sizes, languages, frameworks), generate documentation and manually validate key pages. Store as golden snapshots. Run against each new Repowise version to detect regressions.

2. **Scale benchmark:** Run `repowise init` against repos of increasing size (1K, 5K, 10K, 50K, 100K files) and record: wall time, peak memory, LLM token cost, page quality (manual sample). Publish as a benchmark table.

3. **Import resolution accuracy test:** For a known repo, manually annotate all import relationships. Compare against Repowise's resolved graph. Compute precision (no false edges) and recall (no missing edges). This quantifies the fundamental limitation of static import resolution.

---

## Summary

### What Repowise gets right

- **Graph-first architecture** is the right foundation. Import graphs capture real structural dependencies that keyword search and file-listing tools miss entirely.
- **Temporal intelligence** (git history, co-change, staleness) adds a dimension that pure static analysis can't provide.
- **Bounded cascade** is an elegant solution to the exponential propagation problem. PageRank-sorted budgets ensure the most valuable docs stay fresh.
- **Multi-source decision extraction** is genuinely novel. No other open-source tool mines architectural intent from commits, comments, and documentation simultaneously.
- **MCP integration** makes the intelligence immediately useful inside AI coding workflows, which is where developers increasingly spend their time.

### What has been addressed

Five of the top priorities have been implemented:

| Risk | Status | Implementation |
|------|--------|---------------|
| Three-store consistency | **Fixed** | `doctor --repair` checks SQL↔Vector↔FTS and auto-repairs |
| Dynamic import blindness | **Partially fixed** | Framework edges for pytest, Django, FastAPI, Flask |
| LLM output validation | **Fixed** | Symbol cross-check on every file_page generation |
| Cascade budget rigidity | **Fixed** | Adaptive budget scales 10-50 based on change magnitude |
| Silent failures | **Fixed** | Generation report after every update run |

### What still needs work

1. **CI-first staleness prevention** — the biggest adoption risk. A GitHub Action template exists in `docs/` but isn't yet a first-class integration.
2. **Scale architecture** — in-memory graph and O(n²) algorithms still limit repos > 50K files.
3. **Decision auto-expiry** — decisions with high staleness for 90+ days should auto-deprecate (partially designed, not yet in crud.py).
4. **Runtime trace integration** — would capture dynamic imports exercised by tests, complementing the static framework heuristics.

### Overall assessment

Repowise solves a real, painful problem. The architecture is well-designed for its intended scale (repos up to ~50K files). The graph-based approach is fundamentally sound — it captures structural relationships that simpler tools miss. The incremental update system with adaptive cascade budgets is sophisticated and practical.

The recent improvements address the top risks: three-store consistency is now detectable and repairable, LLM hallucinations are flagged via symbol cross-checking, framework-mediated imports are captured for the most common Python frameworks, and generation runs produce clear cost/quality summaries.

Remaining risks are: adoption requiring CI integration for automatic maintenance, scale limits for very large monorepos, and decision system maturity. None of these are fundamental to the architecture — they're engineering hardening, not redesign.

For a team with a 500-10,000 file codebase that wants to reduce onboarding time, improve refactoring safety, and preserve architectural knowledge, Repowise delivers substantial value. For very small repos (< 50 files) or very large monorepos (> 100K files), the value proposition is weaker — the first doesn't need it, the second might outgrow it.
