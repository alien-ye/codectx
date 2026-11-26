# codectx

A rebuilt local code-context CLI based on [the supplied design](DESIGN.md). It indexes Python, Java and best-effort Groovy/Spock symbols, retrieves them with BM25 and model2vec, and expands results through a name-based reference graph. It needs no API key. The embedding model downloads once; subsequent use can be offline.

## Install

```bash
cd /home/alien/repo/codectx
UV_LINK_MODE=copy uv sync --python 3.12 --extra java --extra dev
uv run codectx doctor
```

In this workspace, the installed environment is ready to use through `.venv/bin/codectx`. A `codectx` launcher is also installed under `~/.local/bin`.

## Commands

```bash
codectx index /path/to/repo --stats
codectx embed /path/to/repo
HF_HUB_OFFLINE=1 codectx search 'validate incoming request' /path/to/repo --mode hybrid
codectx symbols path/in/repo.py /path/to/repo
codectx graph 'path/in/repo.py::Class.method' /path/to/repo --callers
codectx context 'validate incoming request' /path/to/repo --tokens 4000
codectx coverage /path/to/repo --sample 100
codectx doctor --repo /path/to/repo
```

For questions about implementation details, enable passage indexing once. Subsequent `index` runs refresh changed files and remove deleted passages automatically.

```bash
codectx index /path/to/repo --bodies
codectx search 'negative indexing' /path/to/repo --mode body -k 5
codectx context 'negative indexing' /path/to/repo --mode body --tokens 2000
```

Body mode searches source text and enclosing symbol names using SQLite FTS5. A result includes the indexed source, file and line range. Short methods fit in one passage and long definitions are split into blocks of up to 48 lines. Body queries open the SQLite file directly and work offline without embeddings. Hybrid mode continues to search symbol metadata and embeddings, and skips the subtype boost when the entire query matches an indexed name or qualified name. The `coverage` command requires ripgrep.

Use `--db /custom/index` on both indexing and query commands to keep the index outside the source repository. The [benchmark cache note](bench/results/INDEX-CACHE.txt) describes how to recreate the historical indexes.

`CODECTX_MODEL_NAME` changes the semantic model; run `embed --force` afterward. Indexing and embedding are separate. Lexical search and graph operations do not import numpy or model2vec. `index --force` recovers corrupt JSONL without first trying to decode it.

## Changes from the supplied design

This is a new implementation, not the missing original source or a claim of passing its unavailable 110 tests. See `tests/test_acceptance.py` for the regression checks actually run.

* Store format **2**, with `file_path` on references. Reference pruning and parent linking use file identity.
* Vector row identity includes file, qualified name, byte offset and content hash. Stale rows from changed files are dropped; unchanged rows survive ID renumbering. `embed` checks a fingerprint instead of only the model name.
* Standard logarithmic BM25 IDF; acronym splitting (`XMLParser` → `xml`, `parser`); Python module/class variables are extracted.
* References are resolved after every file has been processed, and refreshed during graph reads. Same-name symbols across files require disambiguation at the CLI. Ambiguous graph targets are enumerated and marked; no first-match target is silently selected.
* Java records and annotation types are also extracted. Constructors retain `<init>` names. Groovy uses Java grammar after line-preserving normalization; parse errors remain visible instead of marking all symbols healthy whenever a class was found. It is not a complete Groovy parser.
* Cached parser instances, in-memory lookup maps, packed integer BM25 postings, streaming JSONL reads/writes, pooled immutable paths/names, batched embeddings and memory-mapped vectors reduce overhead. Search commands load only the reference kinds they use; partial views can update vector metadata but cannot rewrite source/reference records. Symbol and graph queries load the plain-file store from scratch. Warm benchmark queries reuse searchers.
* Context output never exceeds its **character-based estimate** (`4 chars/token`). This is not a tokenizer guarantee. Large blocks are skipped so smaller results can fit. There is no search-seed reclassification that could falsely mark a heuristic subtype as exact.
* Extra `coverage` CLI for the Python regex differential oracle. Git discovery uses NUL-separated paths; symlinks are skipped. Non-Git discovery applies ignore rules with pathspec. An unchanged reindex preserves the existing index files and manifest.
* Implementation modules expose the main component APIs; command dispatch is consolidated in `cli.py`, rather than separate `cmd_*` modules.

## Java and Python graph queries

Run `codectx index /path/to/repo` once to refresh an older format-2 index. The indexer tracks the extractor version per file. Subsequent runs return to content-based updates.

```bash
codectx graph 'Service.handle/2' /path/to/repo --callees
codectx graph 'src/api/Repo.java::Repo.save' /path/to/repo --overridden-by --depth 3
codectx graph 'SqlRepo.save' /path/to/repo --overrides
```

* Java call sites retain their receiver and argument count. Outgoing edges belong to the declaring overload's source location. Select a declaration by `/arity`, or use the exact `file::name@line:byte` selector printed for ambiguous matches. Anonymous class bodies have their own symbols and base edges.
* Java package names and explicit imports scope inheritance. Python records individual imports and aliases, including relative imports. Decorators, Java annotations and Python metaclasses appear as references. Module imports can have zero candidates because the graph indexes declarations.
* Receiver lookup uses simple parameter types, Java field and local declarations, and straight-line Python local annotations or assignments such as `repo = SqlRepo()`. Python instance methods share field types from class annotations and straight-line assignments in `__init__`, including a field assigned from an annotated parameter. A known builtin container receiver such as a dictionary initialized with `{}` is labeled `builtin_receiver` and has zero project targets. Lookup also follows `this`, `self`, and direct `super` calls. `polymorphic` lists the indexed base declaration and compatible descendant implementations. The same targets participate in reverse caller queries. Override queries use inheritance depth and name matching, plus written parameter types for Java. Java generic substitution, Python's full MRO, and control-flow-sensitive type inference are outside this analysis.
* Literal reflection such as `Class.forName("pkg.Driver")` and `getattr(obj, "save")` produces a `reflective` reference. A computed target produces a `dynamic_dispatch` marker with its source location in graph and hybrid context output. Use `--mode body` to inspect related implementations. Framework wiring, SPI configuration and runtime-generated methods still require other evidence.

A graph label describes the available static evidence. `exact` means a unique bare name, `arity_match` uses argument count, and `receiver_match` uses a receiver type. Unknown receivers and equal-arity overloads can still yield several candidates.

CLI index and embed commands take the same per-index writer lock. Direct Store API callers must coordinate writes themselves. The symbol store publishes each JSONL file individually and writes the manifest last. Readers that need a consistent multi-file symbol snapshot should run between writes. Body queries check the SQLite generation against the manifest and report when reindexing is needed.

## Assessment

See [benchmark methodology](bench/README.md), [labels](bench/queries.json), and the generated `bench/REPORT.md`. Full raw output, index timings, sample context packs and per-query rankings are retained under `bench/results/`.

Fetch the model once before running the offline checks (the benchmark environment already has it cached):

```bash
.venv/bin/python -c 'from codectx.semantic import _load_model, DEFAULT_MODEL_NAME; _load_model(DEFAULT_MODEL_NAME)'
OPENBLAS_NUM_THREADS=1 HF_HUB_OFFLINE=1 .venv/bin/pytest
.venv/bin/ruff check src tests bench
.venv/bin/python bench/make_queries.py
.venv/bin/python bench/index_all.py
.venv/bin/python bench/run_evaluations.py
.venv/bin/python bench/report.py
```

## Source-grounded RAG pilot

The [RAG pilot report](bench/rag_pilot/REPORT.md) audits actual packed evidence on twenty source-checked questions and preserves an interactive answer walkthrough. The [model runner and optional judge](bench/rag_pilot/README.md) support stateless calls to local model servers. Context-coverage scores are objective; interactive answer judgments are not an independent model benchmark.
