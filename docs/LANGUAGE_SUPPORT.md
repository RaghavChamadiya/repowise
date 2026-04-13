# Language Support

repowise analyses codebases written in many languages. Each language goes
through a multi-stage pipeline: file traversal, AST parsing, import
resolution, call graph construction, and heritage (inheritance) extraction.
Not every language has reached full coverage yet --- this page documents
exactly what works today, what is coming next, and how to add a new language.

---

## Support Tiers

Every language falls into one of five tiers. The tier determines which
pipeline stages produce meaningful output.

| Stage | Full | Partial | Scaffolded | Traversal | Config / Data |
|-------|:----:|:-------:|:----------:|:---------:|:-------------:|
| File discovery & git history | Y | Y | Y | Y | Y |
| AST symbol extraction | Y | Y | -- | -- | -- |
| Import resolution | Y | Y | -- | -- | -- |
| Call graph edges | Y | partial | -- | -- | -- |
| Heritage (extends/implements) | Y | partial | -- | -- | -- |
| Named bindings | Y | -- | -- | -- | -- |
| Dead code detection | Y | Y | Y | Y | -- |
| Semantic search & wiki pages | Y | Y | Y | Y | Y |

---

## Language Reference

### Full

Languages with complete pipeline coverage: AST parsing, import resolution,
call resolution, named bindings, and heritage extraction.

| Language | Extensions | Entry Points | Import Style |
|----------|-----------|-------------|-------------|
| **Python** | `.py` `.pyi` | `main.py` `app.py` `__main__.py` `manage.py` `wsgi.py` `asgi.py` | `import x` / `from x import y` |
| **TypeScript** | `.ts` `.tsx` | `index.ts` `main.ts` `app.ts` `server.ts` | `import { x } from 'y'` / `require()` |
| **JavaScript** | `.js` `.jsx` `.mjs` `.cjs` | `index.js` `main.js` `app.js` `server.js` | `import` / `require()` |
| **Java** | `.java` | `Main.java` `Application.java` | `import pkg.Class` |
| **Go** | `.go` | `main.go` `cmd/main.go` | `import "path"` with `go.mod` resolution |
| **Rust** | `.rs` | `main.rs` `lib.rs` | `use crate::` / `use super::` / `use self::` with `Cargo.toml` |

All six languages support:
- Tree-sitter AST parsing with dedicated `.scm` query files
- Three-tier call resolution (same-file, cross-file, global stem match)
- Named binding extraction (mapping imported names to source symbols)
- Heritage extraction (class/interface/trait inheritance chains)
- Framework-aware edges (Django, FastAPI, Flask for Python; tsconfig path aliases for TS/JS)

### Partial

AST parsing and symbol extraction work. Import resolution is available.
Call resolution or heritage extraction may have gaps.

| Language | Extensions | What Works | Gaps |
|----------|-----------|-----------|------|
| **C++** | `.cpp` `.cc` `.cxx` `.h` `.hpp` `.hxx` | Symbols, `#include` resolution via `compile_commands.json`, heritage, call captures | No named binding extractor |
| **C** | `.c` | Symbols (structs, functions, macros), `#include` resolution via `compile_commands.json` | No call captures in `.scm`, no heritage |

C and C++ share the same tree-sitter grammar (`tree-sitter-cpp`). C files
use a narrower `.scm` query.

### Scaffolded

Tree-sitter query files (`.scm`) and heritage extractors exist, but the
grammar packages are not yet wired as dependencies. These languages are
tracked in the file tree and included in wiki generation, but without AST
detail.

| Language | Extensions | What Exists | What is Missing |
|----------|-----------|------------|----------------|
| **Kotlin** | `.kt` `.kts` | `kotlin.scm` (symbols + imports), heritage extractor, builtin data | Grammar not in dependencies, no call captures, no binding extractor |
| **Ruby** | `.rb` | `ruby.scm` (symbols + require imports), heritage extractor, builtin data | Grammar not in dependencies, no call captures, no binding extractor |

To activate Kotlin or Ruby, install the grammar and add a `LanguageConfig`
entry --- see [Adding a New Language](#adding-a-new-language) below.

### Traversal

Files are discovered, indexed in git history, and included in wiki
generation and semantic search. No AST parsing.

| Language | Extensions |
|----------|-----------|
| **C#** | `.cs` |
| **PHP** | `.php` |
| **Swift** | `.swift` |
| **Scala** | `.scala` |

### Config / Data

Non-code files included in the file tree and wiki. Special handlers extract
endpoints or targets where applicable.

| Language | Extensions / Filenames | Special Handler |
|----------|----------------------|----------------|
| **OpenAPI** | YAML/JSON with `openapi` or `swagger` key | Extracts API paths and schemas |
| **Dockerfile** | `Dockerfile` | Extracts stages and exposed ports |
| **Makefile** | `Makefile` `GNUmakefile` | Extracts targets |
| **Protobuf** | `.proto` | -- |
| **GraphQL** | `.graphql` `.gql` | -- |
| **Terraform** | `.tf` `.hcl` | -- |
| **YAML** | `.yaml` `.yml` | -- |
| **JSON** | `.json` | -- |
| **TOML** | `.toml` | -- |
| **Markdown** | `.md` `.mdx` | -- |
| **SQL** | `.sql` | -- |
| **Shell** | `.sh` `.bash` `.zsh` | -- |

### Git-Blame-Only

These languages are tracked in git history (blame, hotspot analysis,
co-change detection) but have no AST parsing or dedicated support. Files
appear in the wiki as traversal-level entries.

Objective-C, Elixir, Erlang, Lua, R, Dart, Zig, Julia, Clojure, Elm,
Haskell, OCaml, F#, Crystal, Nim, D

---

## How the Pipeline Processes a File

```
File discovered by FileTraverser
        |
        v
Extension/filename -> LanguageTag  (via LanguageRegistry)
        |
        +-- Config/data language?  -> empty ParsedFile (passthrough)
        +-- Special format?        -> special_handlers.py (OpenAPI/Dockerfile/Makefile)
        +-- Has grammar?           -> tree-sitter AST parsing
                |
                v
        .scm query extracts:
          @symbol.def / @symbol.name    -> Symbol nodes
          @import.statement / @import.module -> Import edges
          @call.target / @call.receiver     -> Call edges
                |
                v
        Per-language extractors:
          - Named bindings (import name -> source symbol)
          - Heritage (extends/implements/traits)
          - Docstrings (Python, JSDoc, GoDoc, Rustdoc, Javadoc)
          - Visibility (public/private/protected)
                |
                v
        GraphBuilder resolves imports:
          Python: dotted module paths, __init__.py, src/ layout
          TS/JS:  relative paths, tsconfig aliases, node_modules
          Go:     go.mod module path stripping
          Rust:   crate::/self::/super::, mod.rs probing
          C/C++:  compile_commands.json include directories
          Other:  stem-map fallback (filename matching)
                |
                v
        Graph analysis:
          PageRank, community detection, dead code, execution flows
```

---

## Adding a New Language

All language configuration lives in the centralised `LanguageRegistry`
(`packages/core/src/repowise/core/ingestion/languages/`). Adding a new
language touches at most five places:

### Step 1: Add a `LanguageSpec` to the registry

Edit `packages/core/src/repowise/core/ingestion/languages/registry.py` and
add a new `LanguageSpec(...)` entry to the `_SPECS` tuple:

```python
LanguageSpec(
    tag="mylang",
    display_name="MyLang",
    extensions=frozenset({".ml"}),
    grammar_package="tree_sitter_mylang",       # PyPI package name
    scm_file="mylang.scm",                      # query file name
    heritage_node_types=frozenset({"class_declaration"}),
    entry_point_patterns=("main.ml",),
    manifest_files=("mylang.toml",),
    shebang_tokens=("mylang",),
    builtin_calls=frozenset({"print", "len"}),  # filter from call graph
    builtin_parents=frozenset({"Object"}),       # filter from heritage
    color_hex="#AB47BC",
)
```

### Step 2: Add the `LanguageTag`

Add `"mylang"` to the `LanguageTag` Literal type in
`packages/core/src/repowise/core/ingestion/models.py`.

### Step 3: Write a tree-sitter query file

Create `packages/core/src/repowise/core/ingestion/queries/mylang.scm` using
tree-sitter S-expression syntax. Follow the capture-name conventions:

| Capture | Purpose | Required? |
|---------|---------|-----------|
| `@symbol.def` | Full definition node (line numbers, kind lookup) | Yes |
| `@symbol.name` | Name identifier | Yes |
| `@symbol.params` | Parameter list | No |
| `@symbol.modifiers` | Decorators / visibility modifiers | No |
| `@symbol.receiver` | Go-style method receiver | No |
| `@import.statement` | Full import node | Yes |
| `@import.module` | Module path being imported | Yes |
| `@call.target` | Function/method being called | No (enables call graph) |
| `@call.receiver` | Object the call is made on | No |
| `@call.arguments` | Call arguments | No |

Look at existing `.scm` files for examples --- `python.scm` and
`typescript.scm` are good starting points.

### Step 4: Add a `LanguageConfig` entry

Add a parser configuration to `LANGUAGE_CONFIGS` in
`packages/core/src/repowise/core/ingestion/parser.py`:

```python
"mylang": LanguageConfig(
    symbol_node_types={
        "function_definition": "function",
        "class_definition": "class",
    },
    import_node_types=["import_statement"],
    export_node_types=[],
    visibility_fn=_public_by_default,
    parent_extraction="nesting",
    parent_class_types=frozenset({"class_definition"}),
    entry_point_patterns=["main.ml"],
),
```

### Step 5: Add the tree-sitter grammar dependency

Add the grammar package to `pyproject.toml`:

```toml
[project]
dependencies = [
    # ...
    "tree-sitter-mylang>=0.23,<1",
]
```

### Optional: Import resolver

If the language has a non-trivial import system, add resolution logic to
`_resolve_import()` in `packages/core/src/repowise/core/ingestion/graph.py`.
For simple languages, the generic stem-map fallback (matching by filename)
works out of the box.

### Optional: Binding and heritage extractors

For full-tier support, add:
- `_extract_mylang_bindings()` in `parser.py` (maps import nodes to named symbols)
- `_extract_mylang_heritage()` in `parser.py` (extracts inheritance chains)

### Verify

```bash
# Run the parser tests
pytest tests/ -k "mylang or sample_repo" -x

# Index a real project
repowise init /path/to/mylang-project
```

No changes are needed to `traverser.py`, `graph.py` (for basic support),
`dead_code.py`, `page_generator.py`, `cost_estimator.py`, or any other
consumer file --- they all derive their language sets from the registry
automatically.

---

## Roadmap

Languages planned for future support, in rough priority order:

| Language | Target Tier | Status |
|----------|------------|--------|
| Kotlin | Good (AST + imports + calls) | `.scm` and heritage extractor exist, grammar wiring needed |
| Ruby | Good | `.scm` and heritage extractor exist, grammar wiring needed |
| C# | Good | Heritage extractor exists, `.scm` + grammar needed |
| Swift | Good | Spec exists, all extractors needed |
| Scala | Good | Spec exists, all extractors needed |
| PHP | Good | Spec exists, all extractors needed |
| Dart | Good | Stretch goal |
| Elixir | Good | Stretch goal |

See `docs/LANGUAGE_SUPPORT_PLAN.md` for the detailed implementation plan.
