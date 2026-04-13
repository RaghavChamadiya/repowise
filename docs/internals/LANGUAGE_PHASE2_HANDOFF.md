# Phase 2 Handoff — Language Support Refactoring

**For:** Next Claude Code session  
**Date:** 2026-04-13  
**Branch:** `feat/language-support`  
**Status:** Phase 1 DONE (not yet committed). Phase 2 ready to start.

---

## What Phase 1 Did (DONE — verify via `git diff`)

Created a centralised `LanguageRegistry` and migrated 14 consumer files to use it.

### Files created
- `packages/core/src/repowise/core/ingestion/languages/__init__.py`
- `packages/core/src/repowise/core/ingestion/languages/spec.py` — `LanguageSpec` frozen dataclass
- `packages/core/src/repowise/core/ingestion/languages/registry.py` — `LanguageRegistry` singleton with 42 language specs

### Files migrated (all derive from `REGISTRY` now)
- `ingestion/language_data.py` — thin wrapper over registry
- `ingestion/models.py` — `EXTENSION_TO_LANGUAGE`, `SPECIAL_FILENAMES` derived from registry
- `ingestion/parser.py` — `_PASSTHROUGH_LANGUAGES`, `_HERITAGE_NODE_TYPES`, `_build_language_registry()` use registry
- `ingestion/traverser.py` — `_GENERATED_SUFFIXES`, `_ENTRY_POINT_NAMES`, `_SKIP_GENERATED_CHECK`, shebang detection
- `generation/page_generator.py` — `_CODE_LANGUAGES`, `_INFRA_LANGUAGES`
- `cli/cost_estimator.py` — same (duplication eliminated)
- `analysis/dead_code.py` — `_NON_CODE_LANGUAGES`
- `ingestion/git_indexer.py` — `_CODE_EXTENSIONS`
- `cli/ui.py` — `_LANG_MAP`
- `server/mcp_server/_helpers.py` — `_CODE_EXTS`
- 4 workspace extractors — extension allowlists

### Files deleted
- `packages/core/queries/` — stale duplicate of `ingestion/queries/`

### Test results
- 1093 passed, 0 failed (1 pre-existing failure in `test_mcp_full_exploration_flow` — `KeyError: 'architecture_diagram_mermaid'`, unrelated)

---

## What Phase 1 Did NOT Touch (deliberately left for Phase 2)

These are still in their original monolithic locations inside `parser.py` and `graph.py`:

### In `parser.py` (1,771 lines)
1. **`LanguageConfig` dataclass + `LANGUAGE_CONFIGS` dict** (lines 131-340) — 8 per-language configs with `symbol_node_types`, `import_node_types`, `visibility_fn`, `parent_extraction`, etc.
2. **6 visibility functions** (lines 165-200) — `_py_visibility`, `_ts_visibility`, `_go_visibility`, `_rust_visibility`, `_java_visibility`, `_public_by_default`
3. **5 binding extractor functions** (lines 984-1278) — `_extract_python_bindings`, `_extract_ts_js_bindings`, `_extract_go_bindings`, `_extract_rust_bindings`, `_extract_java_bindings` + dispatcher
4. **9 heritage extractor functions** (lines 1361-1642) — one per language + dispatcher `_HERITAGE_EXTRACTORS`
5. **Docstring extraction** (lines 821-927) — `_extract_module_docstring`, `_extract_symbol_docstring` with if/elif per language
6. **Signature building** (lines 930-981) — `_build_signature` with if/elif on node types

### In `graph.py` (1,285 lines)
7. **`_resolve_import()`** (lines 683-805) — 5-language if/elif chain with inline Python/TS/C++ logic
8. **Go resolver submethods** (lines 811-869) — `_resolve_go_import`, `_read_go_module_path`
9. **Rust resolver submethods** (lines 875-981) — `_resolve_rust_import`, `_find_rust_crate_root`, `_probe_rust_path`
10. **C/C++ compile_commands** (lines 552-637) — `_load_compile_commands`, `_extract_include_dirs`
11. **Framework edge methods** (lines 1070-1240) — `_add_django_edges`, `_add_fastapi_edges`, `_add_flask_edges`

### Frontend (5 files)
12. Language colors/legends still hardcoded in TypeScript — `confidence.ts`, `language-donut.tsx`, `graph-legend.tsx`, `symbol-table.tsx`, `globals.css`

---

## Phase 2 Plan: Modularize Extractors & Resolvers

The goal: move per-language functions out of the monolithic `parser.py` and `graph.py` into a plugin-like dispatch system. After Phase 2, adding a new language's extractors/resolvers is self-contained — one file per concern.

### 2.1 Create `languages/_extractors/` — per-language extractor modules

```
languages/_extractors/
├── __init__.py         # auto-discovers and registers extractors
├── _base.py            # LanguageExtractor Protocol
├── python_ext.py       # bindings, heritage, docstrings, visibility, signature
├── typescript_ext.py
├── javascript_ext.py
├── java_ext.py
├── go_ext.py
├── rust_ext.py
├── cpp_ext.py
├── c_ext.py
```

Each extractor implements:
```python
class LanguageExtractor(Protocol):
    def extract_bindings(self, import_node, src) -> tuple[list[str], list[NamedBinding]]: ...
    def extract_heritage(self, def_node, name, line, src, out) -> None: ...
    def extract_module_docstring(self, root, src) -> str | None: ...
    def extract_symbol_docstring(self, node, src) -> str | None: ...
    def build_signature(self, node_type, name, params_text, def_node, src) -> str | None: ...
    def visibility(self, name, modifiers) -> str: ...
```

`parser.py` dispatches to extractors instead of containing the logic:
```python
extractor = REGISTRY.get_extractor(lang)
if extractor:
    bindings = extractor.extract_bindings(node, src)
```

### 2.2 Create `languages/_resolvers/` — per-language import resolvers

```
languages/_resolvers/
├── __init__.py
├── _base.py            # ImportResolver Protocol
├── python_resolver.py  # dotted imports, __init__.py, src/ layout
├── ts_js_resolver.py   # multi-ext probe, tsconfig aliases (absorbs tsconfig_resolver.py)
├── go_resolver.py      # go.mod module path stripping
├── rust_resolver.py    # crate::/self::/super::, mod.rs probing
├── cpp_c_resolver.py   # compile_commands.json include paths
```

Each resolver implements:
```python
class ImportResolver(Protocol):
    def resolve(self, module_path, importer_file, repo_root, file_index, stem_map) -> str | None: ...
```

`graph.py`'s `_resolve_import()` becomes a one-liner dispatch.

### 2.3 Move framework edges into `dynamic_hints/`

Move `_add_django_edges`, `_add_fastapi_edges`, `_add_flask_edges` from `graph.py` into `dynamic_hints/` directory which already has the right pattern (`DjangoDynamicHints`, etc.). Register via `HintRegistry`.

### 2.4 (Optional) Generate frontend language config

Generate `languageRegistry.generated.ts` from the Python registry as a build step. Eliminates the 5 hardcoded frontend files.

---

## Key Architectural Constraints

1. **`LanguageSpec` (registry) vs `LanguageConfig` (parser.py)**: Phase 1 kept these separate deliberately. `LanguageSpec` = identity/data (no tree-sitter imports). `LanguageConfig` = parser-specific AST config (depends on tree-sitter). Phase 2 may merge them into the extractor modules, but the registry itself should remain a leaf dependency.

2. **parser.py is the #1 hotspot** (99.4th percentile churn). Every change must be tested thoroughly. The strategy is: create the new extractor module first, verify parity, then swap the import in parser.py.

3. **graph.py is the #3 hotspot** (99.4th percentile). Same strategy: create resolver modules first, verify parity, then swap.

4. **Circular import risk**: Extractor modules will import tree-sitter types. They must NOT be imported by the registry. The registry stays a leaf. Extractors are loaded by parser.py, not by the registry.

5. **Pre-existing test failure**: `test_mcp_full_exploration_flow` fails with `KeyError: 'architecture_diagram_mermaid'` — this is unrelated to our changes.

---

## Reference Files

| File | Purpose | Lines |
|------|---------|-------|
| `docs/LANGUAGE_SUPPORT_PLAN.md` | Full 3-phase plan (Phase 1 done, Phase 2/3 pending) |
| `docs/LANGUAGE_SUPPORT.md` | User-facing language support doc (created in Phase 1) |
| `ingestion/languages/registry.py` | The registry (Phase 1 output) |
| `ingestion/languages/spec.py` | LanguageSpec dataclass |
| `ingestion/parser.py` | Main target for Phase 2 extraction — 1,771 lines |
| `ingestion/graph.py` | Second target for Phase 2 extraction — 1,285 lines |
| `ingestion/tsconfig_resolver.py` | TS/JS resolver to absorb into `_resolvers/` — 423 lines |
| `ingestion/dynamic_hints/` | Existing hint pattern to extend with framework edges |
