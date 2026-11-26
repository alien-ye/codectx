# codectx

Local symbol retrieval, SQLite FTS5 implementation search, and provenance-aware code context for Python, Java, and best-effort Groovy/Spock repositories. Runs locally with no API key; after the one-time `model2vec` download, indexing and retrieval work offline.

Built from [the detailed design specification](DESIGN.md) as a clean-room implementation (`src/codectx/`), and evaluated across five open-source codebases (`langchain`, `django`, `spring-boot`, `kafka`, and `jdk21u`).

## Features

- **Multi-signal symbol retrieval:** Combines identifier-aware BM25 (`lexical`), `model2vec` static embeddings (`semantic`, default `minishlab/potion-code-16M-v2`), and Reciprocal Rank Fusion (`hybrid`, automatically bypassing subtype boosts when a query matches an indexed name or qualified name).
- **Opt-in implementation passage search (`--mode body`):** Indexes AST-bounded source passages (up to 48 lines per block, tagged with enclosing symbol scope) into SQLite FTS5 (`bodies.sqlite3`) for intra-method logic queries without loading the symbol store or embeddings.
- **Tree-sitter static semantics & honest graph provenance:**
  - Java `package` / `import` scoping, anonymous classes, annotations, method references, overload `/arity` and `@line:byte` selectors.
  - Python relative/alias imports (`from .pkg import Foo as Bar`), decorators, metaclasses, and straight-line local/parameter type bindings.
  - Bidirectional method override tracing (`--overrides`, `--overridden-by`), polymorphic expansion (`polymorphic`), and literal vs. computed reflection markers (`reflective`, `dynamic_dispatch`).
  - Explicit provenance labels on every hop—no silent first-match guessing on ambiguous targets.
- **Token-budgeted context packing (`context`):** Packs retrieved symbols, graph neighbors, and `dynamic_dispatch` markers within a character-estimated token budget (`4 chars/token`) with `file:line` citations.
- **Incremental & serialized indexing:** Content-hash incremental symbol updates, atomic per-file replacement, no-op index preservation, and `FileLock` serialization across CLI writers.

## Installation

Requires Python `>=3.12`, `uv`, and `git` (`ripgrep` / `rg` is optional and only needed for `codectx coverage`):

```bash
git clone https://github.com/alien-ye/codectx.git
cd codectx
UV_LINK_MODE=copy uv sync --python 3.12 --extra java --extra dev
uv run codectx doctor
```

Or install with `pip`:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[java]"
codectx doctor
```

## Quick Start

### 1. Index a repository

```bash
# Symbol + graph index (creates .codectx/ inside the repo, or pass --db /custom/index)
codectx index /path/to/repo --stats

# Include opt-in SQLite FTS5 body passages for implementation-detail search
codectx index /path/to/repo --bodies

# Compute symbol embeddings for semantic / hybrid search
codectx embed /path/to/repo
```

Use `--db /custom/index` on both indexing and query commands to keep indexes outside the source repository. Set `CODECTX_MODEL_NAME` to switch the `model2vec` model (then run `codectx embed /path/to/repo --force`).

### 2. Search symbols or implementation bodies

```bash
# Lexical BM25 over symbol names, signatures, and docstrings
codectx search 'validate incoming request' /path/to/repo --mode lexical

# Offline hybrid search (BM25 + model2vec RRF)
HF_HUB_OFFLINE=1 codectx search 'validate incoming request' /path/to/repo --mode hybrid

# Implementation passage search via SQLite FTS5 (no embeddings required)
codectx search 'negative indexing' /path/to/repo --mode body -k 5
```

### 3. Inspect symbols, call graphs, and overrides

```bash
# List symbols in a file
codectx symbols path/in/repo.py /path/to/repo

# Callers / callees
codectx graph 'path/in/repo.py::Class.method' /path/to/repo --callers

# Select a specific Java overload by arity or line:byte
codectx graph 'Service.handle/2' /path/to/repo --callees
codectx graph 'app/Db.java::Db.save@4:42' /path/to/repo --callers

# Trace polymorphic overrides
codectx graph 'src/api/Repo.java::Repo.save' /path/to/repo --overridden-by --depth 3
codectx graph 'SqlRepo.save' /path/to/repo --overrides
```

### 4. Build an LLM context pack

```bash
# Symbol + graph context within a token budget (4 chars/token estimate)
codectx context 'validate incoming request' /path/to/repo --tokens 4000 --depth 1

# Implementation-passage context pack from SQLite FTS5
codectx context 'negative indexing' /path/to/repo --mode body --tokens 2000
```

### 5. Diagnostics & differential coverage

```bash
codectx doctor --repo /path/to/repo
codectx coverage /path/to/repo --sample 100   # requires ripgrep (rg)
```

## Graph Labels & Scope Limits

`codectx` reports the static evidence backing each graph hop rather than pretending to be a full compiler:

- **`exact`**: One matching bare symbol name across the index.
- **`qualified`**: Matched via package/import qualification.
- **`receiver_match`**: Narrowed via explicit parameter, field, local annotation, constructor assignment, `this`/`self`, or `super`.
- **`arity_match`**: Narrowed by Java argument count.
- **`polymorphic`**: Base declaration plus compatible descendant overrides.
- **`override_candidate`**: Inheritance-depth and name/signature override match.
- **`reflective` / `dynamic_dispatch`**: Literal reflection (`Class.forName("pkg.Driver")`, `getattr(obj, "save")`) links to candidate targets; computed targets emit a `dynamic_dispatch` marker with source location so callers can switch to `--mode body`.
- **`name_match` / `unresolved`**: Ambiguous bare-name candidates (all listed, never silently collapsed) or no indexed target found.

Java generic substitution, full Python MRO, control-flow-sensitive type inference, framework/DI wiring, and languages outside Python/Java/Groovy are outside this static analysis. Symbol and graph commands load the plain-file JSONL store from disk per invocation; only body search (`--mode body`) queries SQLite directly.

## Benchmarks & Development

See [bench/README.md](bench/README.md), [bench/REPORT.md](bench/REPORT.md), [bench/RANKING_METRICS.md](bench/RANKING_METRICS.md), and the [RAG pilot report](bench/rag_pilot/REPORT.md) for methodology, pinned repository snapshots, and raw artifacts under `bench/results/`.

```bash
# Run tests and linter
OPENBLAS_NUM_THREADS=1 HF_HUB_OFFLINE=1 .venv/bin/pytest
.venv/bin/ruff check src tests bench

# Rebuild benchmark queries, indexes, evaluations, and report
.venv/bin/python bench/make_queries.py
.venv/bin/python bench/index_all.py
.venv/bin/python bench/run_evaluations.py
.venv/bin/python bench/report.py
```

## License

Released under the [MIT License](LICENSE).
