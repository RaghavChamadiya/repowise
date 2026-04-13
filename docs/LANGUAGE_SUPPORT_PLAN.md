# Language Support Plan

**Date:** 2026-04-12  
**Goal:** Modularize all language-specific code, complete partially-implemented languages, add new language support.  
**Estimated scope:** ~4,000–6,000 LOC across 3 phases.

---

## Current State — Honest Audit

The README claims 5 language tiers. The code tells a different story.

### What the README says vs. what actually works

| Language | README Tier | Actual Tier | What's Real | What's Missing |
|----------|-------------|-------------|-------------|----------------|
| **Python** | Full | **Full** | AST, imports, call resolution, heritage, bindings, dedicated resolver | — |
| **TypeScript** | Full | **Full** | AST, imports, call resolution, heritage, bindings, tsconfig resolver | — |
| **JavaScript** | Full | **Full** | AST, imports, call resolution, heritage, bindings, tsconfig resolver | — |
| **Java** | Full | **Full** | AST, imports, call resolution, heritage, bindings | — |
| **Go** | Good | **Full** | AST, imports, call resolution, heritage, bindings, go.mod resolver | README under-reports — has full pipeline identical to Python/TS |
| **Rust** | Good | **Full** | AST, imports, call resolution, heritage, bindings, crate resolver | README under-reports — has full pipeline identical to Python/TS |
| **C++** | Good | **Partial** | AST (via tree-sitter-cpp), symbols, compile_commands.json imports, heritage | No call resolution `.scm` captures? — **check**: cpp.scm has `@call.*`. No named binding extractor. |
| **C** | Basic | **Partial** | Shares cpp grammar, narrower .scm, compile_commands.json imports | No call captures in c.scm, no binding extractor, `parent_extraction="none"` |
| **Kotlin** | Good | **Traversal** | `.scm` file exists, heritage extractor exists, `BUILTIN_CALLS`/`BUILTIN_PARENTS` defined | Grammar NOT loaded, NOT in pyproject.toml, no `LANGUAGE_CONFIGS`, no binding extractor — all dead code |
| **Ruby** | Good | **Traversal** | `.scm` file exists, heritage extractor exists, `BUILTIN_CALLS`/`BUILTIN_PARENTS` defined | Grammar NOT loaded, NOT in pyproject.toml, no `LANGUAGE_CONFIGS`, no binding extractor — all dead code |
| **C#** | Good | **Traversal** | Heritage extractor exists, `BUILTIN_CALLS`/`BUILTIN_PARENTS` defined | No `.scm` file, no grammar, no `LANGUAGE_CONFIGS` — heritage extractor unreachable |
| **Swift** | Traversal | **Traversal** | Extension mapped in `models.py`, files indexed | No `.scm`, no grammar, no nothing |
| **Scala** | Traversal | **Traversal** | Extension mapped in `models.py`, files indexed | No `.scm`, no grammar, no nothing |
| **PHP** | Traversal | **Traversal** | Extension mapped in `models.py`, files indexed | No `.scm`, no grammar, no nothing |

### README should be updated to reflect:
- **Full:** Python, TypeScript, JavaScript, Java, Go, Rust
- **Partial:** C++ (AST + imports + heritage, no bindings), C (AST + #include, no calls/bindings)
- **Traversal (scaffolded):** Kotlin, Ruby (`.scm` + heritage extractor exist but grammar not wired)
- **Traversal:** C#, Swift, Scala, PHP (extension mapped only)
- **Config/data:** OpenAPI, Protobuf, GraphQL, Dockerfile, Makefile, YAML, JSON, TOML, SQL, Terraform

---

## Where Language Config Lives Today — The Scatter Problem

Language-specific logic is spread across **15+ files** with significant duplication:

| Concern | File(s) | Duplication? |
|---------|---------|--------------|
| Extension → language mapping | `ingestion/models.py` | Single source ✓ |
| LanguageTag enum | `ingestion/models.py` | Single source ✓ |
| Builtin call/parent filtering | `ingestion/language_data.py` | Single source ✓ |
| Tree-sitter grammar loading | `ingestion/parser.py` `_build_language_registry()` | Hardcoded if/elif |
| AST node type → symbol kind | `ingestion/parser.py` `LANGUAGE_CONFIGS` | Per-language dicts in one big dict |
| Visibility rules | `ingestion/parser.py` `_py_visibility`, `_ts_visibility`, etc. | 6 separate functions |
| Docstring extraction | `ingestion/parser.py` `_extract_module_docstring`, `_extract_symbol_docstring` | if/elif per language |
| Import binding extraction | `ingestion/parser.py` `_extract_*_bindings` | 5 separate functions + dispatcher |
| Heritage extraction | `ingestion/parser.py` `_extract_*_heritage` | 9 separate functions + dispatcher |
| Signature building | `ingestion/parser.py` `_build_signature` | Large if/elif chain |
| Import resolution | `ingestion/graph.py` `_resolve_import()` | Giant if/elif chain + dedicated resolvers |
| Framework edge wiring | `ingestion/graph.py` `_add_django/fastapi/flask_edges` | 3 separate Python-only methods |
| TS/JS path alias resolution | `ingestion/tsconfig_resolver.py` | Isolated module ✓ |
| Entry point filenames | `ingestion/parser.py` + `ingestion/traverser.py` | **Duplicated** across 2 files |
| Blocked dirs/extensions | `ingestion/traverser.py` | Mixed into traversal logic |
| Generated file suffixes | `ingestion/traverser.py` | Hardcoded per-language |
| Shebang detection | `ingestion/traverser.py` | if/elif per language |
| Non-code language sets | `parser.py`, `traverser.py`, `dead_code.py`, `page_generator.py` | **Duplicated** across 4 files |
| Manifest files | `traverser.py` + `tech_stack.py` | **Duplicated** across 2 files |
| Framework decorators | `dead_code.py` | Python-only, hardcoded |
| Dynamic import markers | `dead_code.py` | Python-only, hardcoded |
| Framework detection (Django/Pytest/Node) | `dynamic_hints/*.py` | Isolated but hardcoded registry |
| Tech stack detection | `generation/editor_files/tech_stack.py` | Hardcoded per manifest |
| Code vs infra language sets | `generation/page_generator.py` | Independent from other sets |
| Tree-sitter queries | `ingestion/queries/*.scm` | One per language ✓ |

### Key duplication issues:
1. **"Non-code" / "data" / "passthrough" languages** defined independently in 4 files
2. **Entry point filenames** defined in both `traverser.py` and `parser.py` LANGUAGE_CONFIGS
3. **Manifest files** listed in both `traverser.py` and `tech_stack.py`
4. **Code language sets** defined separately in `page_generator.py` and implicitly via `LANGUAGE_CONFIGS` keys

---

## The Graph Intelligence Upgrade Context

The recently completed [GRAPH_INTELLIGENCE_UPGRADE.md](./GRAPH_INTELLIGENCE_UPGRADE.md) (Phases 1–5, all DONE) added:
- Symbol nodes + call edges with 3-tier resolution
- Named bindings with per-language extractors (Python, TS/JS, Go, Rust, Java)
- Heritage extraction for 11 languages (Python, TS, JS, Java, Go, Rust, C++, Kotlin, Ruby, C#, C)
- Leiden community detection + execution flow tracing
- 4 new MCP tools for graph queries

**Impact on this plan:** The heritage extractors for Kotlin, Ruby, and C# already exist but are unreachable because grammars aren't loaded. Wiring these up is low-effort. The named binding extractors and call resolution patterns established for the 6 Full-tier languages serve as templates for adding bindings to C++ and new languages.

**Remaining graph gaps relevant here:**
- C++ and C lack named binding extractors (bindings are the bridge between imports and call resolution)
- Kotlin/Ruby `.scm` files lack `@call.*` captures
- No `.scm` files at all for C#, Swift, Scala, PHP

---

## Phase 1: Code Restructuring — Language Registry & Modularity

**Goal:** Centralize all language-specific configuration into a single registry system. Eliminate duplication. Make "add a new language" a matter of adding one config file + one `.scm` file.

**Estimated LOC:** ~1,500–2,000 (mostly moving existing code, not writing new)

### 1.1 Create `LanguageRegistry` — Single Source of Truth

Create `packages/core/src/repowise/core/ingestion/language_registry.py`:

```python
@dataclass(frozen=True)
class LanguageSpec:
    """Complete specification for a language. One object = everything repowise
    needs to know about a language."""
    
    # Identity
    tag: LanguageTag                           # "python", "typescript", etc.
    extensions: tuple[str, ...]                # (".py", ".pyi")
    special_filenames: tuple[str, ...] = ()    # ("Dockerfile",)
    tier: Literal["full", "partial", "traversal", "config"] = "traversal"
    
    # Tree-sitter
    grammar_package: str | None = None         # "tree_sitter_python"
    grammar_fn: str = "language"               # function name in grammar package
    scm_file: str | None = None                # "python.scm" (None = no AST)
    shares_grammar_with: str | None = None     # C shares with cpp
    
    # AST config (from current LANGUAGE_CONFIGS)
    symbol_node_types: dict[str, SymbolKind] | None = None
    import_node_types: tuple[str, ...] = ()
    export_node_types: tuple[str, ...] = ()
    visibility_fn: Callable | None = None
    parent_extraction: Literal["nesting", "receiver", "impl", "none"] = "nesting"
    parent_class_types: tuple[str, ...] = ()
    
    # Entry points & ecosystem
    entry_point_patterns: tuple[str, ...] = ()      # ("main.py", "app.py")
    manifest_files: tuple[str, ...] = ()             # ("pyproject.toml",)
    blocked_dirs: tuple[str, ...] = ()               # ("__pycache__",)
    blocked_extensions: tuple[str, ...] = ()         # (".pyc",)
    lock_files: tuple[str, ...] = ()                 # ("poetry.lock",)
    generated_suffixes: tuple[str, ...] = ()         # ("_pb2.py",)
    shebang_markers: tuple[str, ...] = ()            # ("python",)
    
    # Classification
    is_code: bool = True                   # False for yaml, json, markdown, etc.
    is_config: bool = False                # True for yaml, toml, json, dockerfile, makefile
    is_api_contract: bool = False          # True for proto, graphql
    is_infra: bool = False                 # True for dockerfile, makefile, terraform, shell
    
    # Feature flags (derived from tier, but overridable)
    has_imports: bool = False
    has_call_resolution: bool = False
    has_heritage: bool = False
    has_bindings: bool = False
    
    # Builtins (from current language_data.py)
    builtin_calls: frozenset[str] = frozenset()
    builtin_parents: frozenset[str] = frozenset()
    
    # Docstring style
    docstring_style: Literal["python", "jsdoc", "godoc", "rustdoc", "javadoc", "none"] = "none"
    
    # Comment patterns (for generated-file detection, etc.)
    line_comment: str | None = None        # "//" or "#"
    block_comment: tuple[str, str] | None = None  # ("/*", "*/")


class LanguageRegistry:
    """Central registry. All language-specific lookups go through here."""
    
    _specs: dict[LanguageTag, LanguageSpec]
    _ext_map: dict[str, LanguageTag]          # built from specs
    _filename_map: dict[str, LanguageTag]     # built from specs
    _grammar_cache: dict[str, Language]        # loaded lazily
    
    def get(self, tag: LanguageTag) -> LanguageSpec | None
    def from_extension(self, ext: str) -> LanguageTag
    def from_filename(self, name: str) -> LanguageTag | None
    def code_languages(self) -> frozenset[LanguageTag]
    def config_languages(self) -> frozenset[LanguageTag]
    def passthrough_languages(self) -> frozenset[LanguageTag]
    def infra_languages(self) -> frozenset[LanguageTag]
    def all_extensions(self) -> frozenset[str]
    def load_grammar(self, tag: LanguageTag) -> Language | None
    def entry_point_names(self) -> frozenset[str]      # union of all specs
    def manifest_filenames(self) -> frozenset[str]      # union of all specs
    def blocked_dirs(self) -> frozenset[str]            # union of all specs
    # ... etc
```

### 1.2 Per-Language Spec Files

Create `packages/core/src/repowise/core/ingestion/languages/` directory:

```
languages/
├── __init__.py          # exports REGISTRY (populated from all specs)
├── _registry.py         # LanguageRegistry + LanguageSpec classes
├── python.py            # SPEC = LanguageSpec(tag="python", ...)
├── typescript.py        # SPEC = LanguageSpec(tag="typescript", ...)
├── javascript.py
├── java.py
├── go.py
├── rust.py
├── cpp.py
├── c.py
├── kotlin.py            # tier="traversal" until grammar wired
├── ruby.py              # tier="traversal" until grammar wired
├── csharp.py            # tier="traversal"
├── swift.py             # tier="traversal"
├── scala.py             # tier="traversal"
├── php.py               # tier="traversal"
├── shell.py             # tier="config"
├── yaml.py              # tier="config"
├── json_.py             # tier="config" (underscore to avoid shadowing)
├── toml_.py             # tier="config"
├── proto.py             # tier="config", is_api_contract=True
├── graphql.py           # tier="config", is_api_contract=True
├── terraform.py         # tier="config"
├── dockerfile.py        # tier="config"
├── makefile.py          # tier="config"
├── markdown.py          # tier="config"
├── sql.py               # tier="config"
└── openapi.py           # tier="config"
```

Each file is ~30–80 lines of pure data. Example for Python:

```python
# languages/python.py
from ._registry import LanguageSpec
from ..models import SymbolKind

SPEC = LanguageSpec(
    tag="python",
    extensions=(".py", ".pyi"),
    tier="full",
    grammar_package="tree_sitter_python",
    scm_file="python.scm",
    symbol_node_types={
        "function_definition": SymbolKind.FUNCTION,
        "class_definition": SymbolKind.CLASS,
        "decorated_definition": SymbolKind.FUNCTION,
    },
    import_node_types=("import_statement", "import_from_statement"),
    visibility_fn=_py_visibility,
    parent_extraction="nesting",
    parent_class_types=("class_definition",),
    entry_point_patterns=("main.py", "app.py", "__main__.py", "manage.py", "wsgi.py", "asgi.py"),
    manifest_files=("pyproject.toml", "setup.py", "setup.cfg"),
    blocked_dirs=("__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", ".eggs", "site-packages"),
    blocked_extensions=(".pyc", ".pyo", ".pyd"),
    lock_files=("poetry.lock", "uv.lock"),
    generated_suffixes=("_pb2.py", "_pb2_grpc.py"),
    shebang_markers=("python",),
    is_code=True,
    has_imports=True,
    has_call_resolution=True,
    has_heritage=True,
    has_bindings=True,
    builtin_calls=frozenset({"abs", "len", "print", "range", ...}),
    builtin_parents=frozenset({"object", "Exception", "ABC", ...}),
    docstring_style="python",
    line_comment="#",
)
```

### 1.3 Refactor Consumers to Use Registry

Replace all scattered constants with registry lookups:

| Current | After |
|---------|-------|
| `models.py` `EXTENSION_TO_LANGUAGE` | `REGISTRY.from_extension(ext)` |
| `models.py` `SPECIAL_FILENAMES` | `REGISTRY.from_filename(name)` |
| `parser.py` `_PASSTHROUGH_LANGUAGES` | `REGISTRY.passthrough_languages()` |
| `parser.py` `LANGUAGE_CONFIGS` | `REGISTRY.get(tag)` (spec has all config) |
| `parser.py` `_build_language_registry()` | `REGISTRY.load_grammar(tag)` |
| `traverser.py` `_BLOCKED_DIRS` | `REGISTRY.blocked_dirs()` |
| `traverser.py` `_ENTRY_POINT_NAMES` | `REGISTRY.entry_point_names()` |
| `traverser.py` `_MANIFEST_FILES` | `REGISTRY.manifest_filenames()` |
| `traverser.py` `_GENERATED_SUFFIXES` | Derived from specs |
| `traverser.py` `_detect_by_shebang()` | `REGISTRY` lookup via `shebang_markers` |
| `dead_code.py` `_NON_CODE_LANGUAGES` | `REGISTRY.config_languages()` |
| `page_generator.py` `_CODE_LANGUAGES` | `REGISTRY.code_languages()` |
| `page_generator.py` `_INFRA_LANGUAGES` | `REGISTRY.infra_languages()` |
| `language_data.py` `BUILTIN_CALLS` | Moved into each spec's `builtin_calls` |
| `language_data.py` `BUILTIN_PARENTS` | Moved into each spec's `builtin_parents` |
| `git_indexer.py` `_CODE_EXTENSIONS` | `REGISTRY.all_code_extensions()` |

### 1.4 Modularize Language-Specific Functions

Move per-language functions out of the monolithic `parser.py` into a dispatch system:

```
languages/
├── _extractors/
│   ├── __init__.py         # auto-discovers and registers extractors
│   ├── _base.py            # Protocol / ABC for extractors
│   ├── python_ext.py       # PythonExtractor: bindings, docstrings, signature, visibility
│   ├── typescript_ext.py
│   ├── javascript_ext.py
│   ├── java_ext.py
│   ├── go_ext.py
│   ├── rust_ext.py
│   ├── cpp_ext.py
│   ├── c_ext.py
│   └── ...                 # one per language that has AST support
```

Each extractor implements:
```python
class LanguageExtractor(Protocol):
    def extract_bindings(self, import_node: Node) -> tuple[list[str], list[NamedBinding]]: ...
    def extract_heritage(self, symbol_node: Node, ...) -> list[HeritageRelation]: ...
    def extract_module_docstring(self, root: Node) -> str | None: ...
    def extract_symbol_docstring(self, node: Node) -> str | None: ...
    def build_signature(self, node: Node) -> str | None: ...
    def visibility(self, node: Node) -> str: ...
```

`parser.py` dispatches to the extractor instead of containing the logic:
```python
extractor = REGISTRY.get_extractor(lang)
if extractor:
    bindings = extractor.extract_bindings(node)
```

### 1.5 Modularize Import Resolvers

Move per-language import resolution out of graph.py:

```
languages/
├── _resolvers/
│   ├── __init__.py
│   ├── _base.py            # ImportResolver protocol
│   ├── python_resolver.py  # handles dotted imports, __init__.py, src/ layout
│   ├── ts_js_resolver.py   # multi-extension probe, tsconfig aliases (absorbs tsconfig_resolver.py)
│   ├── go_resolver.py      # go.mod module path stripping
│   ├── rust_resolver.py    # crate::/self::/super::, mod.rs probing
│   ├── cpp_c_resolver.py   # compile_commands.json include paths
│   └── ...
```

Each resolver implements:
```python
class ImportResolver(Protocol):
    def resolve(self, module_path: str, importer_file: str, repo_root: Path, 
                file_index: dict, stem_map: dict) -> str | None: ...
```

`graph.py` `_resolve_import()` becomes a one-liner dispatch.

### 1.6 Modularize Framework Hints

The `dynamic_hints/` directory is already well-structured. Only change needed:
- Move framework edge wiring (`_add_django_edges`, `_add_fastapi_edges`, `_add_flask_edges`) from `graph.py` into `dynamic_hints/` and register via the existing `HintRegistry`
- Make `HintRegistry` auto-discover hint classes instead of hardcoding the list

### 1.7 Outcome

After Phase 1, adding a new language requires:
1. Create `languages/<lang>.py` with a `SPEC` object (~50 lines of data)
2. Create `ingestion/queries/<lang>.scm` (tree-sitter queries)
3. Create `languages/_extractors/<lang>_ext.py` (binding/heritage/docstring extractors)
4. Create `languages/_resolvers/<lang>_resolver.py` (import resolution)
5. Add `tree-sitter-<lang>` to `pyproject.toml`

**Zero changes to parser.py, graph.py, traverser.py, dead_code.py, page_generator.py, or any other core file.**

---

## Phase 2: Complete Partially-Implemented Languages

**Goal:** Wire up Kotlin, Ruby, C#, and harden C++/C. Bring them all to at least "Good" tier.

**Estimated LOC:** ~1,500–2,000

### 2.1 C++ → Full Tier

C++ already has: grammar, `.scm` with `@call.*` captures, heritage extractor, `compile_commands.json` import resolution.

**Missing:**
- Named binding extractor for `#include` (extract header filename as binding)
- Proper `_extract_cpp_bindings()` function
- Module docstring extraction (Doxygen `/** ... */` at file top)
- Symbol docstring extraction (Doxygen before declarations)

**Work:** ~150 LOC for binding extractor + docstring support.

### 2.2 C → Partial Tier (improved)

C shares the C++ grammar. Currently has a limited `.scm` (no `@call.*`).

**Missing:**
- Add `@call.*` captures to `c.scm` (copy from cpp.scm, narrow to C patterns)
- Named binding extractor (same as C++ — `#include` filename extraction)
- Docstring support (Doxygen style)

**Work:** ~100 LOC for `.scm` additions + binding extractor.

### 2.3 Kotlin → Good Tier

Kotlin has: `.scm` file (symbols + imports, no calls), heritage extractor, builtin data.

**Missing:**
1. Add `tree-sitter-kotlin` to `pyproject.toml`
2. Wire grammar loading in registry (or `_build_language_registry()` if Phase 1 isn't done yet)
3. Add `LANGUAGE_CONFIGS` entry (symbol_node_types, import_node_types, visibility_fn, etc.)
4. Add `@call.*` captures to `kotlin.scm`
5. Write `_extract_kotlin_bindings()` for `import_header` nodes
6. Write import resolver for Kotlin (package-based, similar to Java)
7. Add Kotlin docstring extraction (KDoc `/** ... */`)

**Work:** ~350 LOC (scm additions + binding extractor + resolver + config).

### 2.4 Ruby → Good Tier

Ruby has: `.scm` file (symbols + require imports), heritage extractor, builtin data.

**Missing:**
1. Add `tree-sitter-ruby` to `pyproject.toml`
2. Wire grammar loading
3. Add `LANGUAGE_CONFIGS` entry
4. Add `@call.*` captures to `ruby.scm`
5. Write `_extract_ruby_bindings()` for `require`/`require_relative`
6. Write import resolver for Ruby (`require` → file path mapping, `require_relative` → relative)
7. Add Ruby docstring extraction (YARD `# @param` / RDoc)

**Work:** ~350 LOC.

### 2.5 C# → Good Tier

C# has: heritage extractor, builtin data. Nothing else.

**Missing:**
1. Add `tree-sitter-c-sharp` to `pyproject.toml`
2. Write `csharp.scm` query file (classes, interfaces, methods, enums, properties, `using` statements, method invocations)
3. Wire grammar loading
4. Add `LANGUAGE_CONFIGS` entry
5. Write `_extract_csharp_bindings()` for `using` directives
6. Write import resolver for C# (namespace-based, similar to Java but with `using` aliasing)
7. Add C# docstring extraction (XML doc comments `/// <summary>`)

**Work:** ~500 LOC (full .scm + all extractors + resolver).

### 2.6 Testing Strategy

For each language upgrade:
- Add sample files to `tests/fixtures/sample-repo/` in that language
- Add integration tests to `tests/integration/test_ingest_sample_repo.py` asserting:
  - Symbols extracted (count + kinds)
  - Imports resolved (at least same-dir)
  - Call edges created
  - Heritage edges created
- Add unit tests for the binding extractor and resolver

### 2.7 Outcome

After Phase 2:

| Language | Tier |
|----------|------|
| Python, TypeScript, JavaScript, Java, Go, Rust | **Full** |
| C++, Kotlin, Ruby, C# | **Good** (AST, imports, calls, heritage) |
| C | **Partial** (AST, imports, calls — no heritage nesting) |
| Swift, Scala, PHP | Traversal (Phase 3) |

---

## Phase 3: New Language Support

**Goal:** Add Swift, Scala, PHP, and optionally Dart and Elixir (from the README roadmap).

**Estimated LOC:** ~2,500–3,500

### 3.1 Swift → Good Tier

Swift is a complex language but tree-sitter-swift exists.

**Tasks:**
1. Add `tree-sitter-swift` to `pyproject.toml`
2. Write `swift.scm`: `function_declaration`, `class_declaration`, `struct_declaration`, `protocol_declaration`, `enum_declaration`, `extension_declaration`, `import_declaration`, call expressions
3. Write `LanguageSpec` / `LANGUAGE_CONFIGS` entry
4. Write binding extractor for `import` statements (module-level, no named imports in Swift)
5. Write import resolver (Swift Package Manager — `Package.swift` manifest, module-level imports)
6. Write heritage extractor: `class Foo: Bar, Protocol1` (colon-separated, similar to Kotlin)
7. Add `BUILTIN_CALLS` (Foundation framework), `BUILTIN_PARENTS` (`NSObject`, `Codable`, etc.)
8. Docstring extraction (Swift doc comments `///` and `/** ... */`)

**Complexity:** Medium — Swift imports are module-level (not file-level), making resolution simpler but coarser.

**Work:** ~500 LOC.

### 3.2 Scala → Good Tier

Scala has a rich type system and complex import syntax.

**Tasks:**
1. Add `tree-sitter-scala` to `pyproject.toml`
2. Write `scala.scm`: `function_definition`, `class_definition`, `trait_definition`, `object_definition`, `val_definition`, `import_declaration`, call expressions
3. Write `LanguageSpec` / `LANGUAGE_CONFIGS` entry
4. Write binding extractor: `import pkg.{A, B => C}`, `import pkg._` (wildcard)
5. Write import resolver (SBT-based — `build.sbt`, package-based similar to Java/Kotlin)
6. Write heritage extractor: `class Foo extends Bar with Trait1 with Trait2`
7. Add `BUILTIN_CALLS` (scala.*, Predef), `BUILTIN_PARENTS` (`Any`, `AnyRef`, `Product`, `Serializable`)
8. Docstring extraction (ScalaDoc `/** ... */`)

**Complexity:** Medium-high — Scala's import syntax with renames and wildcards requires careful tree-sitter query design.

**Work:** ~550 LOC.

### 3.3 PHP → Good Tier

PHP has `tree-sitter-php` available.

**Tasks:**
1. Add `tree-sitter-php` to `pyproject.toml`
2. Write `php.scm`: `function_definition`, `class_declaration`, `interface_declaration`, `trait_declaration`, `method_declaration`, `namespace_use_declaration`, `function_call_expression`
3. Write `LanguageSpec` / `LANGUAGE_CONFIGS` entry
4. Write binding extractor: `use Foo\Bar\Baz`, `use Foo\Bar as B`
5. Write import resolver (Composer autoload — `composer.json` PSR-4 mappings, namespace → directory)
6. Write heritage extractor: `class Foo extends Bar implements Interface1`, `use TraitName`
7. Add `BUILTIN_CALLS` (PHP globals), `BUILTIN_PARENTS` (`stdClass`, `Exception`, `Iterator`, etc.)
8. Docstring extraction (PHPDoc `/** ... */`)
9. Add `dynamic_hints/composer.py` for Composer autoload resolution

**Complexity:** Medium — PHP's namespace system maps cleanly to directories via PSR-4.

**Work:** ~550 LOC.

### 3.4 Dart → Good Tier (Roadmap)

**Tasks:**
1. Add `tree-sitter-dart` to `pyproject.toml`
2. Write `dart.scm`: classes, functions, mixins, extensions, enums, `import`/`export` directives
3. Write binding extractor: `import 'package:foo/bar.dart' show A, B` / `hide C`
4. Write import resolver: `pubspec.yaml` package mapping, `package:` URI scheme
5. Heritage: `class Foo extends Bar with Mixin1 implements Interface1`
6. Add `dynamic_hints/flutter.py` for Flutter widget tree detection

**Work:** ~500 LOC.

### 3.5 Elixir → Good Tier (Roadmap)

**Tasks:**
1. Add `tree-sitter-elixir` to `pyproject.toml`
2. Write `elixir.scm`: `def`, `defp`, `defmodule`, `defprotocol`, `defimpl`, `import`/`use`/`alias`/`require`
3. Write binding extractor: `alias Foo.Bar, as: B`, `import Foo, only: [func: 1]`
4. Write import resolver: `mix.exs` dependencies, module-to-file mapping (`Foo.Bar` → `lib/foo/bar.ex`)
5. Heritage: protocol implementations (`defimpl Protocol, for: Type`)
6. Add `BUILTIN_CALLS` (Kernel functions), `BUILTIN_PARENTS` (standard protocols)

**Complexity:** Medium — Elixir's macro-heavy nature means some constructs won't parse cleanly via tree-sitter.

**Work:** ~500 LOC.

### 3.6 Testing & Validation

For each new language:
- Create a realistic sample project in `tests/fixtures/` (3–5 files with imports, classes, calls)
- Integration tests asserting full pipeline: parse → graph → community → MCP query
- Validate against a real open-source project of that language

### 3.7 Outcome

After Phase 3:

| Tier | Languages |
|------|-----------|
| **Full** | Python, TypeScript, JavaScript, Java, Go, Rust |
| **Good** | C++, C, Kotlin, Ruby, C#, Swift, Scala, PHP, Dart*, Elixir* |
| **Config** | OpenAPI, Protobuf, GraphQL, Dockerfile, Makefile, YAML, JSON, TOML, SQL, Terraform |

*Dart and Elixir are stretch goals — depends on demand.

---

## Execution Order & Dependencies

```
Phase 1: Code Restructuring (MUST be first)
├── 1.1 LanguageRegistry + LanguageSpec         ← foundation
├── 1.2 Per-language spec files                 ← populate registry
├── 1.3 Refactor consumers                      ← eliminate duplication
├── 1.4 Modularize extractors                   ← parser.py cleanup
├── 1.5 Modularize resolvers                    ← graph.py cleanup
└── 1.6 Modularize framework hints              ← graph.py cleanup

Phase 2: Complete Existing Languages (after Phase 1)
├── 2.1 C++ bindings + docstrings               ← smallest, good validation of Phase 1 patterns
├── 2.2 C call captures + bindings              ← same as 2.1
├── 2.3 Kotlin full wiring                      ← first "new grammar" test of Phase 1
├── 2.4 Ruby full wiring                        ← same pattern as 2.3
├── 2.5 C# from scratch                         ← heaviest, validates full add-language workflow
└── 2.6 Tests for all                           ← can be parallel with each

Phase 3: New Languages (after Phase 2)
├── 3.1 Swift                                   ← independent
├── 3.2 Scala                                   ← independent
├── 3.3 PHP                                     ← independent
├── 3.4 Dart (stretch)                          ← independent
└── 3.5 Elixir (stretch)                        ← independent
```

Phase 3 languages are fully independent of each other — can be done in any order or in parallel.

---

## Migration Strategy

- **No breaking changes.** The registry is additive. Old constants continue working until all consumers are migrated.
- **Feature-flag the registry:** `REGISTRY = LanguageRegistry()` populated at import time. If a spec file is missing, the language falls back to traversal tier.
- **Gradual consumer migration:** Each consumer file (parser.py, graph.py, traverser.py, etc.) can be migrated independently.
- **Test continuously:** Run `pytest tests/` after every consumer migration. The integration tests cover the full parse → graph → persist pipeline.

---

## Open Questions

1. **Should visibility functions live in the spec or in extractors?** Spec is simpler (just a callable reference), extractor is more cohesive (all language logic in one place). **Recommendation:** Extractor, with the spec pointing to it.

2. **Should we support optional grammar loading?** Currently grammars are hard dependencies. With Kotlin/Ruby/C#/Swift/Scala/PHP added, that's 6 more C extensions to compile. **Recommendation:** Split into `repowise[all]` (all grammars) and `repowise[core]` (Python/TS/JS/Java/Go/Rust only). Use extras groups in pyproject.toml.

3. **Should the `.scm` files stay in `ingestion/queries/` or move to `languages/`?** They're tightly coupled to the language spec. **Recommendation:** Move to `languages/queries/` alongside the spec files.

4. **What about the duplicate `packages/core/queries/` directory?** It's a stale pre-call-extraction copy. **Recommendation:** Delete it in Phase 1.
