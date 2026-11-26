# codectx — Detailed Design (DD)
Purpose of this document: a complete, regeneration-grade specification of `codectx` v0.1.0.
An engineer (or an LLM) with only this file, Python 3.12, `uv`, `git` and `rg` should be able to
rebuild a project that passes the same acceptance behaviour. Every constant, file format, node
type and algorithm that affects behaviour is stated. Section 14 lists defects in the original that
you must either reproduce (for byte-for-byte compatibility) or fix deliberately.
Source of truth: `/home/elinyee/repo/tool/codectx` (read in full 2026-11-23; all 110 tests pass in a clean
venv, 0 failures (run 2026-11-23)).
---
## 1. Overview
**What it is.** A local, API-key-free CLI that gives an LLM *code context* for one repository by
fusing three retrieval signals over one plain-file index:
| Signal | Technique |
|---|---|
| Lexical | BM25 over identifier-split symbol text |
| Semantic | `model2vec` static embeddings, brute-force cosine |
| Structural | tree-sitter symbol graph (calls/imports/references + extends/implements), BFS |
Ranking fusion is Reciprocal Rank Fusion (RRF, k=60) plus a structural "base class" boost. Output of
the main command (`context`) is a token-budgeted text pack with `file:line` citations and provenance
markers that distinguish facts (exact edges) from guesses (name-match / unresolved edges).
**Goals**
1. One unit of identity — the *symbol* — flowing through search, vectors, graph and packer.
2. Index = plain, diffable files (JSONL + one `.npy`), no database, byte-stable on a no-op reindex.
3. Lexical and graph paths must work without importing numpy/model2vec (lazy imports).
4. Honest provenance: every graph edge carries `resolution_kind`; parse failures are visible, never silent.
5. Incremental indexing by content hash; `--force` for recovery.
6. Languages are pluggable modules (Python, Java, Groovy/Spock).
**Non-goals.** No type inference / precise call resolution; no languages beyond the three; no ANN index
(single repo scale: thousands of symbols); no server/daemon; no MCP server in this version (an optional
`mcp` extra and doctor check exist, no code uses it); no database; no network except the one-time
model2vec model download.
**Scale assumption.** One repo, ≤ ~10^5 symbols. Whole index is loaded into memory on open.
---
## 2. Tech stack and project scaffolding
- Python `>=3.12` (hard check in `doctor`; code uses `X | Y` unions, `slots=True` dataclasses).
- Build: `hatchling`; src layout `src/codectx`; package manager `uv` (`[tool.uv] package = true`).
- Runtime deps: `model2vec>=0.4.0`, `tree-sitter>=0.25.0`, `tree-sitter-python>=0.23.0`, `numpy>=1.26`,
  `orjson>=3.10`, `pathspec>=0.12` (declared; **not imported anywhere** — see §14).
- Optional extras: `java = ["tree-sitter-java>=0.23.0"]` (also powers Groovy), `mcp = ["mcp>=1.2.0"]`
  (unused), `dev = ["pytest>=8.0", "ruff>=0.6"]`.
- External binaries: `rg` (ripgrep) and `git` on `PATH`.
- Entry point: `[project.scripts] codectx = "codectx.cli:main"`.
- Ruff: `line-length = 100`, `target-version = "py312"`, exclude `tests/fixtures`, select
  `E,F,W,I,UP,B,SIM`, ignore `E501`. Pytest: `testpaths=["tests"]`, `addopts="-q"`.
- Version string `0.1.0` appears in `pyproject.toml`, `__init__.py` (`__version__`) and `cli.py`
  (`-V`). Keep them equal.
- Env var: `CODECTX_MODEL_NAME` overrides the embedding model.
- Default model: `minishlab/potion-code-16M-v2` (CPU, ~30 MB, downloaded on first use).
### Repository layout
```
codectx/
├─ pyproject.toml  README.md  uv.lock
├─ src/codectx/
│  ├─ __init__.py          # __version__ = "0.1.0"
│  ├─ cli.py               # argparse dispatch, error→exit-code mapping
│  ├─ doctor.py            # capability + index-integrity checks
│  ├─ model.py             # Symbol, ExtractResult, RawRef (extraction-time types)
│  ├─ store.py             # JSONL+npy store, record dataclasses, atomic commit
│  ├─ index.py             # file discovery, hashing, incremental indexing
│  ├─ extract.py           # language dispatch + persistence of symbols/refs
│  ├─ languages/{__init__,_util,python,java,groovy}.py
│  ├─ graph.py             # ref persistence + callers/callees/supertypes/subtypes
│  ├─ tokens.py  bm25.py  search.py   # lexical path
│  ├─ semantic.py          # embeddings + cosine (lazy numpy/model2vec)
│  ├─ hybrid.py            # RRF + subtype boost
│  ├─ context.py           # context packer
│  ├─ rg_tools.py          # rg search + differential coverage oracle
│  └─ cmd_{index,symbols,search,embed,graph,context}.py   # one module per subcommand
└─ tests/ (test_*.py, fixtures/sample_pkg/…)
```
---
## 3. Architecture
### 3.1 Layering and module dependencies
```
cli ──► cmd_* ──► {search, semantic, hybrid, graph, context, index} ──► store
                     │                                   ▲
index ──► extract ──► languages/* ──► model, _util        │
            └──────► graph.persist_refs ───────────────────┘
model ──► store (SymbolRecord, only for Symbol.to_record)
context ──► hybrid ──► {search, semantic} ;  context/hybrid ──► graph
doctor, rg_tools: standalone (rg_tools imports Store)
```
Rules that keep it cycle-free:
- `store.py` imports nothing from the package.
- `model.py` imports only `store.SymbolRecord`.
- `extract.py` imports `graph.persist_refs` **inside the function** (graph imports `extract.extract_refs`
  lazily too — mutual lazy imports).
- `graph.extract_refs` is a thin public re-export that lazily calls `extract.extract_refs`.
- `semantic`/`hybrid` import numpy/model2vec only inside functions.
### 3.2 Data flow
**Index:** `discover_files` → read text, sha256 → compare with `files.jsonl` → for changed code files
`extract_and_persist` (clear that file's symbols → `extract` → `persist_symbols` → `extract_refs` →
`persist_refs`) → delete vanished files → `store.commit()` (atomic).
**Embed:** all `parse_ok` symbols → `_compose_doc` → `model.encode` → `store.set_vectors` (writes `.npy`
+ `ids.jsonl` immediately; manifest keys flushed at `commit`).
**Query:** open store read-only → lexical (BM25 built per query) and/or semantic (cosine) → RRF →
subtype boost → graph expansion → pack under budget.
---
## 4. Data model
### 4.1 Extraction-time types (`model.py`, all `@dataclass(slots=True)`)
```python
Symbol:  file_path:str, name:str, qualified_name:str, kind:str,
         start_line:int, end_line:int, start_byte:int, end_byte:int,   # lines 1-based, bytes 0-based
         signature:str|None=None, docstring:str|None=None,
         parent_symbol_id:int|None=None, parse_ok:bool=True
         def to_record(self) -> SymbolRecord      # id=0, parent_id=parent_symbol_id
ExtractResult: symbols:list[Symbol]=[], parse_ok:bool=True, error:str|None=None
RawRef:  source_qualifier:str, target_name:str, kind:str, line:int
```
### 4.2 Persistent records (`store.py`)
```python
FileRecord:   path(repo-relative posix), lang, content_hash(sha256 hex), mtime_ns:int, size:int
SymbolRecord: id:int=0, file_path, name, qualified_name, kind, start_line, end_line,
              start_byte, end_byte, signature=None, docstring=None, parent_id:int|None=None,
              parse_ok:bool=True            # serialized as 1/0
RefRecord:    source_qualifier, target_name, kind, line:int|None=None, column:int|None=None,
              resolution_kind:str="unresolved", candidate_count:int=0
```
Each has `to_dict()` / `from_dict()`; `from_dict` uses `.get` with defaults for optional fields
(`resolution_kind` default `"unresolved"`, `parse_ok` default 1).
### 4.3 Vocabularies
- Symbol `kind`: `function`, `class`, `method`, `variable`, (`import` is listed in `SYMBOL_KINDS` but no
  extractor emits it). Java interfaces and enums are surfaced as `class`; Java fields and enum constants
  as `variable`; Java constructors as `method` named `<init>`.
- Edge `kind` (`EDGE_KINDS`): `calls`, `imports`, `references`, `extends`, `implements`.
  Call-graph set = `{calls, imports, references}`; inheritance set = `{extends, implements}`.
  (No extractor emits `references`.)
- `resolution_kind`: `exact` (exactly 1 symbol of that name), `name_match` (>1), `unresolved` (0).
  `ambiguous` appears in comments/CLI rendering only; nothing produces it.
- Reserved qualified names: `<module>` (module-level ref source), `<parse-error>` (placeholder symbol).
### 4.4 Identity rules (critical invariants)
1. `symbol.id` is assigned per commit, **not stable across runs**. Nothing persistent may reference it.
2. Refs store `source_qualifier` (qualified name) and `target_name` (bare name), resolved at query time.
3. Vector rows are keyed by `(file_path, qualified_name)`, re-resolved to current ids on load; rows that
   no longer resolve are dropped.
4. `parent_id` is re-derived at commit from the qualified-name prefix.
---
## 5. On-disk index format (`<repo>/.codectx/`, `FORMAT_VERSION = 1`)
```
manifest.json      pretty JSON (orjson OPT_INDENT_2)
files.jsonl        one FileRecord dict per line
symbols.jsonl      one SymbolRecord dict per line (key order as in to_dict)
refs.jsonl         one RefRecord dict per line
vectors/<safe_model_id>.npy   float32 [N, dim]
vectors/ids.jsonl             {"v":2,"row":i,"file_path":..,"qualified_name":..}
```
Manifest keys: `format_version`, `root` (resolved abs path), `indexed_at` (`time.time_ns()`),
`file_count`, `symbol_count`, `ref_count`, `last_index_root`, optional `vector_model_id`, `vector_dim`,
`vector_count`, and `error:<rel_path>` entries (parse/read failures).
`_safe_filename(model_id)`: keep `[A-Za-z0-9-_.]`, replace everything else with `_`
(`minishlab/potion-code-16M-v2` → `minishlab_potion-code-16M-v2`).
`VECTORS_IDS_VERSION = 2`. A vectors dir whose `ids.jsonl` has any row without `v == 2` is treated as
"not embedded" (forces re-embed).
**Atomic writes.** Every file is written to `<name>.tmp` then `os.replace`d. Manifest is written last.
**Byte stability.** At `commit`, symbols are sorted by `(file_path, start_line, start_byte)` and renumbered
`1..N`. A no-op reindex must produce byte-identical `symbols.jsonl` (tested). Note `files.jsonl` is
written in dict insertion order and `refs.jsonl` in list order; `indexed_at` in the manifest changes
on every commit, so only the three JSONL files (not the manifest) are expected stable — and commit
is skipped entirely when nothing is dirty. Because `index_files` always calls `upsert_file` (refreshing
mtime) the store is always dirty after an index run; stability comes from deterministic ordering.
---
## 6. Component specifications
### 6.1 `store.Store`
Dataclass holding `index_dir`, `root`, `readonly`, `_manifest`, `_files: dict[path→FileRecord]`,
`_symbols: list`, `_refs: list`, `_next_id=1`, `_dirty`.
| Method | Contract |
|---|---|
| `Store.open(root, readonly=False)` | `index_dir = root.resolve()/".codectx"`; load if dir exists |
| `Store.open_at(index_dir, readonly=False)` | explicit dir (used by every command; `--db` override) |
| `_load()` | read manifest (set `root` from it if present), files, symbols (track max id → `_next_id`), refs |
| `get_files()` / `upsert_file(rec)` | dict access; upsert sets dirty |
| `delete_file(path)` | drop file + its symbols; prune refs (see below) |
| `clear()` | wipe files/symbols/refs, `_next_id=1`, dirty |
| `add_symbol(rec) -> id` | assign `_next_id`, append |
| `clear_file_symbols(path)` | drop that file's symbols; prune refs (see below) |
| `all_symbols()`, `symbols_for_file(path)` (sorted by start_line), `symbol_by_id(id)` (linear scan), `symbols_by_name(name)` (linear scan) | |
| `add_ref`, `all_refs`, `refs_from(symbol_id)` (match `source_qualifier == sym.qualified_name`), `refs_to_name(name)` | |
| `set_vectors(ids, matrix, model_id)` | raises `RuntimeError` if readonly; resolve each id→symbol (`ValueError` if unresolvable); write `.npy` (cast float32) and `ids.jsonl`; set manifest `vector_model_id/dim/count` |
| `get_vectors() -> (ids, matrix, model_id) \\| None` | `None` if no model id, files missing, `ids.jsonl` empty or any row `v != 2`; re-resolve identities, drop non-resolving rows or rows with `row >= matrix.shape[0]`; `None` if none survive; matrix = `matrix[surviving_rows]` |
| `get_meta/set_meta` | manifest access |
| `commit()` | `RuntimeError` if readonly; no-op if not dirty; sort+renumber, rebuild parent ids, write files→symbols→refs→manifest (atomic) |
| `close()` | no-op (API symmetry) |
| `stats()` | `files_total, files_by_language, symbols_total, refs_total, index` |
| `is_empty()` | no files |
*Ref pruning rule (used by `delete_file` and `clear_file_symbols`)*: after removing the file's symbols,
keep a ref iff `ref.source_qualifier ∈ {qualified_name of remaining symbols}` or `== "<module>"`.
*Parent repair at commit*: for each symbol with `parent_id is not None`, set
`parent_id = qname_to_id.get(qualified_name.rsplit(".",1)[0])` (None if no dot).
numpy is imported lazily only in `set_vectors`/`get_vectors`.
### 6.2 `index.py` — discovery and incremental indexing
Constants: `SUPPORTED_CODE_EXTENSIONS = {".py",".java",".groovy"}`;
`DEFAULT_SKIP_DIRS = {".git",".hg",".svn","node_modules","__pycache__",".venv","venv",".tox","dist","build"}`.
`detect_language`: `.py→python`, `.java→java`, `.groovy→groovy`, else `unknown`.
`content_hash(text)` = `sha256(text.encode("utf-8")).hexdigest()`.
`discover_files(root) -> Iterator[DiscoveredFile(path, rel_path, extension)]` (frozen, slots dataclass):
1. `root = root.resolve()`. Candidate list from `_list_files_via_vcs`.
2. Drop any path having a segment in `DEFAULT_SKIP_DIRS`; drop non-files; extension lowercased.
`_list_files_via_vcs(root)` fallback chain:
1. `git -C root ls-files --cached --others --exclude-standard` (timeout 60). Use if rc==0 and stdout non-empty.
2. `rg --files` with one `--ignore-file` per `.gitignore`/`.ignore` found by walking `root`
   (needed because rg ignores `.gitignore` outside a git work tree). Use if rc==0.
3. `os.walk` with skip-dir pruning.
`index_files(store, root, *, extract_fn=None) -> IndexStats`:
- `extract_fn` hook signature `(store, root, rel_path, lang) -> int`, default `extract.extract_and_persist`.
- For each discovered file: read UTF-8 with `errors="replace"` (skip on `OSError`); hash; look up existing.
  - Same hash → `unchanged += 1`, refresh `FileRecord` (mtime/size), no extraction.
  - Else upsert record; `reindexed += 1` if existed, `indexed += 1` if new; if code extension call `extract_fn`.
  - `code_files` counts every code-extension file seen (changed or not).
- After the loop delete files in store but not seen (`store.delete_file`).
- `store.set_meta("last_index_root", str(root))`; `store.commit()`.
- `IndexStats(total_files, indexed_files, code_files, skipped, reindexed, unchanged)` frozen/slots,
  `skipped = total - indexed - unchanged` (so it includes reindexed files — quirk), `to_dict()` via `asdict`.
### 6.3 `extract.py` — dispatch + persistence
- `_LANGUAGE_MODULES` seeded with `python`; `java` and `groovy` loaded lazily on first use via
  `__import__` (so a missing optional grammar only fails when such a file is indexed).
  `_SUPPORTED_LANGS = {"python","java","groovy"}`; unknown language → `ValueError`.
- `extract_symbols(source, path, lang)` / `extract_refs(...)` delegate to `mod.extract` / `mod.extract_refs`.
- `persist_symbols(store, symbols) -> ids`: symbols arrive pre-order; for each, compute
  `parent_qname = qualified_name.rsplit(".",1)[0]` if it contains `.`, look it up in a local
  `qname→id` map, set `parent_symbol_id`, `store.add_symbol(sym.to_record())`.
- `extract_and_persist(store, root, rel_path, lang) -> int`:
  1. Read file (UTF-8, replace); on `OSError` set meta `error:<path>`, return 0.
  2. If lang not supported return 0.
  3. `store.clear_file_symbols(rel_path)`.
  4. `extract_symbols`. If `not parse_ok and not symbols`: add placeholder `SymbolRecord(name="<parse-error\>",
     qualified_name="<parse-error\>", kind="function", parse_ok=False)`, set meta `error:<path\>`, return 0
     (**refs are not extracted** in this case).
  5. `persist_symbols`; then `refs = extract_refs(...)`; `graph.persist_refs(store, refs)`; return symbol count.
- Backward-compat shims `LanguageExtractor = None`, `PYTHON_EXTRACTOR = None` (optional to reproduce).
### 6.4 Language modules (`languages/`)
Protocol: module-level `extract(source:str, file_path:str) -> ExtractResult` and
`extract_refs(source:str, file_path:str) -> list[RawRef]`. Adding a language = new module + registry
entry in `extract.py` + extension mapping in `index.py`.
`_util.py`:
- `child_by_field_name(node, field)`, `node_text(node, source_bytes)` (utf-8, replace),
  `node_has_error(node)` = `node.type == "ERROR" or getattr(node,"has_error",False)`,
  `tree_has_error(node)` = `node_has_error(node)` or any descendant of type `ERROR` (iterative stack).
- Parser creation per call: `Parser(TSLanguage(tree_sitter_<lang>.language()))`; tree-sitter ≥0.25 API
  (`Parser(lang)`, `parser.parse(bytes)`, `tree.root_node`).
**Python (`languages/python.py`)**
Symbols — recursive `_walk(node, source, file_path, prefix, result)`:
- `decorated_definition`: recurse into children that are in `_NODE_KINDS`.
- `_NODE_KINDS = {function_definition: function, class_definition: class, assignment: variable}`.
- For a target node, name = `child_by_field_name("name")`; if None, just descend.
- `function` inside any scope prefix (non-empty) → `method`. (So a nested function in a function is also `method`.)
- `qualified = prefix + name`; children walked with `prefix = qualified + "."`.
- `variable` with non-empty prefix is skipped (descend). **In practice `assignment` has no `name` field, so
  Python variables are never emitted** (verified: `X = 1` yields nothing) — see §14.
- `signature` (function/method/class): text of `parameters` field + `" -> " + return_type` if present
  (classes have no `parameters` → `None`). `docstring`: first child of body `block` that is an
  `expression_statement` with a single `string` child; quotes stripped (`"""`, `'''`, `"`, `'`), `.strip()`.
- `Symbol.parse_ok = not node_has_error(node)`; lines = `start_point[0]+1`.
- After walk: if no symbols and `tree_has_error(root)` → `parse_ok=False`, `error="parse error: syntax error in source"`.
Refs — `_walk_for_refs(node, source, prefix, refs)`:
- `source_qualifier = prefix.rstrip(".") or "<module>"`.
- `function_definition`/`class_definition`: push name onto prefix; for classes emit one `extends` ref per
  base from `superclasses` field. Base name rules: `identifier`→text; `attribute`→last segment;
  `subscript`→recurse into `value`; `call`→recurse into `function`; keyword args/`*args` ignored; dedupe.
- `import_statement` → `imports` with first `dotted_name` child text (else `<import>`); `import_from_statement`
  → `imports` with the first `dotted_name` (the *module*, not the imported names).
- `call` → `calls`; target = identifier text, or for `attribute` the attribute name (receiver ignored);
  then still descend into the call's children (nested calls).
- Line = `start_point[0]+1`.
**Java (`languages/java.py`)**
Node → kind: `class_declaration`/`interface_declaration`/`enum_declaration` → `class`;
`method_declaration`/`constructor_declaration` → `method`; `field_declaration`, `enum_constant` → `variable`.
Name: `name` field, else `declarator` field's `name` (fields). Constructor name forced to `<init>`.
Scope nodes (push qualifier): the three type declarations only (methods do **not** push in symbol walk).
Signature (method/class only, not field): `parameters` text + `" -> " + type` if `type` field present.
Javadoc: `node.prev_named_sibling` of type `block_comment` whose text starts with `/**`; strip `/**`,`*/`
and leading `*` per line, drop empty lines, join with `\\n`. `parse_ok` and parse-failure rule as Python.
Refs: scope nodes + `method_declaration`/`constructor_declaration` push their name (constructor `<init>`)
so calls attribute to the innermost method (`Class.method`). For type declarations emit inheritance
via `_extract_inheritance` before descending:
- `superclass` field → `extends` (class/enum);
- `interface_declaration`: named child of type `extends_interfaces` (no field name) → `extends` per type;
- `interfaces` field → `implements` per type.
Type-name extraction: first/all `type_identifier`/`scoped_identifier` nodes in the subtree, **not descending
into `type_arguments`**; strip generics (`split("<")[0]`), keep last dotted segment; dedupe.
`import_declaration` → `imports` with first `scoped_identifier`/`identifier` child text.
`method_invocation` → `calls` with the `name` field text (fallback: `object` field if identifier);
then descend (nested invocations).
**Groovy / Spock (`languages/groovy.py`)** — tree-sitter-groovy is unusable, so normalize then reuse Java.
`_normalize(source) -> (normalized, line_to_spec_name)`, line-count preserving, per line:
1. Replace a line whose stripped text equals `<label>:` (labels `given, when, then, expect, where, and,
   cleanup`) with an empty line.
2. If regex `(\\s*)def\\s+(["'])([^"']+)\\2\\s*\\(\\s*\\)\\s*\\{` matches at line start: rewrite to
   `{indent}def __spock_{sanitized}() {` where `sanitized = re.sub(r"[^a-zA-Z0-9_]","_",spec_name)`;
   record `line_to_spec_name[idx] = spec_name`.
3. `_terminate_field(line)`: append `;` to bare field lines (indented, ≥2 whitespace tokens, last token a
   plain identifier, no `( ) { }`, not ending in `{ } > ) ,` or `;`, not starting with `@`, `def `,
   `public `, `private `, `protected `, `static `).
`extract`: normalize → `java.extract` → `_restore_spec_names` (map sanitized tail → readable by *tail
match*, set `name`, rewrite last segment of `qualified_name`, and if no docstring set
`"Spock spec: <readable>"`). If any symbol of kind `class` exists, force `result.parse_ok=True`,
`error=None` and all symbols `parse_ok=True` (Spock mocks leave residual ERROR nodes).
`extract_refs`: normalize → `java.extract_refs` → rewrite `source_qualifier` tails starting with `__spock_`
to readable names.
Result: `callers(productionMethod)` returns Spock specs that call it.
### 6.5 `graph.py`
`persist_refs(store, refs)`: builds `name → [symbols]` over `parse_ok` symbols **currently in the store**,
then for each RawRef: 1 candidate → `exact`/1; >1 → `name_match`/N; 0 → `unresolved`/0; appends
`RefRecord(source_qualifier, target_name, kind, line, resolution_kind, candidate_count)`.
(Resolution reflects the store state *at that moment* — files indexed later aren't visible; query-time
`_live_resolution` repairs this for traversal.)
`GraphHop(ref: RefRecord, target: SymbolRecord|None)` frozen/slots.
Traversals are BFS by level with a `visited` set of expanded symbol ids; `depth` levels; stop early when
the frontier is empty; cycle-safe:
- `callees(store, id, depth=1)`: per frontier symbol, for refs from it with kind in call-graph set, target =
  `_resolve_first(name)` (first symbol by `symbols_by_name`); ref copy with `resolution_kind=_live_resolution`.
- `callers(store, id, depth=1)`: for `refs_to_name(current.name)` with call-graph kind, the hop target is the
  *source* symbol resolved via `_resolve_by_qname` (None for `<module>` or unknown); ref is returned as stored.
- `supertypes(store, id, depth=10)` forward / `subtypes(store, id, depth=10)` reverse over
  `{extends, implements}` only; both return `[]` unless the start symbol exists and `kind == "class"`.
- `_live_resolution(store, name, stored_kind)`: no matches→`unresolved`; one→`exact`; many→`name_match`
  unless `stored_kind == "unresolved"` (then stays `unresolved`).
- `_resolve_by_qname`: linear scan; `"<module>"` → None.
Inheritance is kept out of `callees/callers` deliberately so "UserService calls Base" is never reported.
### 6.6 Lexical path
`tokens.py`:
- `_TOKEN_RE = [a-zA-Z_][a-zA-Z0-9_]*`; `_CAPITAL_RUN_RE = ([A-Z]+)`.
- `tokenize(text)` = `findall`.
- `split_identifier(ident)`: `[lowered whole]` + camel parts (insert a space before each capital *run*,
  split; add lowercase parts only if >1 part) + snake parts (split on `_`, drop empties, add only if >1) ;
  de-dup preserving order. Examples: `HandlerStack→[handlerstack, handler, stack]`,
  `XMLParser→[xmlparser]` (verified: the `([A-Z]+)` capital-run split does not break acronym+word, so no
  sub-tokens are produced). Reproduce as-is or improve (§14 #10) and update tests accordingly.
- `query_tokens(query)`: for each whitespace word — if it fully matches the token regex, `split_identifier`;
  else lowercase `tokenize(word)`; then drop `_STOPWORDS`. Stopword set: articles/demonstratives, `be`
  forms, common prepositions, `and or not but if then else`, wh-words, `all any some no each every`,
  `do/does/did/doing`, `has/have/had`, modals (`can could should would will shall may might must`),
  personal/possessive pronouns.
`bm25.BM25Index` (`K1=1.5`, `B=0.75`): `build(docs: list[list[str]])` → `postings: term→{doc→tf}`,
`doc_len`, `avgdl`, `n_docs`. `idf(term) = (N - df + 0.5)/(df + 0.5) + 1.0` (**no log** — see §14; `0.0` if
df==0). `search(terms, k)`: per term per posting `idf * tf*(K1+1) / (tf + K1*(1 - B + B*dl/avgdl))`,
sum per doc, sort desc, top-k as `(doc_idx, score)`. Duplicated query terms count twice.
`search.py`:
- `build_symbol_doc(sym)`: `name_tokens = split_identifier(name)`; tokens = name_tokens ×2; if
  `kind == "class"` add name_tokens ×2 more (total ×4); for each `qualified_name` segment ≠ name add its
  `split_identifier`; signature tokens (`tokenize`, lowercased); docstring tokens (lowercased).
- `search_lexical(store, query, k=10, include_errors=False) -> list[LexHit(symbol_id, score, matched_terms)]`
  (frozen, slots): symbols filtered by `parse_ok` (unless `include_errors`), BM25 rebuilt **per query**,
  `matched_terms = sorted(set(doc) & set(query_terms))`. Empty symbols or empty query terms → `[]`.
### 6.7 Semantic path (`semantic.py`)
- `DEFAULT_MODEL_NAME = "minishlab/potion-code-16M-v2"`; `_env_model_name()` reads `CODECTX_MODEL_NAME`.
- `_compose_doc(sym)`: lines `[name, name, qualified_name (if different), signature, docstring]` joined by `\\n`.
- `_load_model(name)`: `from model2vec import StaticModel; StaticModel.from_pretrained(name)` (lazy).
- `embed_symbols(store, symbols, model_name=None)`: encode docs (empty → zeros `[0,256]` float32),
  `store.set_vectors([s.id...], matrix, model_name)`.
- `search_semantic(store, query, k=10, model_name=None) -> list[SemanticHit(symbol_id, score)]`:
  `get_vectors()` None → `[]`; if stored model id ≠ query model → `RuntimeError` (message tells user to
  re-embed); encode query; zero-norm → `[]`; cosine = row-normalized matrix · unit query (zero-norm rows
  guarded); `k=min(k,N)`; `argpartition` then sort desc.
### 6.8 Hybrid (`hybrid.py`)
`RRF_K = 60`; `_SUBTYPE_BOOST_BASE = 2.0`. `search_hybrid(store, query, k=10) -> list[HybridHit(symbol_id,
score, lexical_rank, semantic_rank)]` (slots; ranks 0-based or None):
1. `fetch = max(3k, 30)`; lexical list ranks; semantic list ranks inside `try/except RuntimeError` →
   on failure semantic is empty (graceful degradation to lexical).
2. Score = Σ `1/(60 + rank + 1)` over lists containing the symbol; sort desc.
3. **Subtype boost**: for each hit of kind `class`, `n = len(subtypes(depth=1))`; if `n>0`,
   `score *= log(n+1, 2.0)` (1 sub → ×1.0, 3 → ×2.0, 7 → ×3.0). Re-sort; return top-k.
### 6.9 Context packer (`context.py`)
Constants: `CHARS_PER_TOKEN=4`, `DEFAULT_TOKEN_BUDGET=8000`, `DEFAULT_GRAPH_DEPTH=1`, `MAX_SNIPPET_LINES=60`.
`PackedSymbol(symbol, source, via_edge_kind=None, score=0.0)`;
`ContextPack(text, symbol_count, token_estimate, truncated, sources: dict[str,int])`.
`build_context(store, query, *, root=None, token_budget=8000, graph_depth=1, k=10)`:
1. Seeds = `search_hybrid(k)` → `PackedSymbol(source="search", score)`, skipping missing/`parse_ok=False`. No seeds → empty pack.
2. For each seed (in order), add unseen targets from: `callers(depth=graph_depth)` (source `caller`),
   `callees(...)` (`callee`); if the seed is a `class`: `subtypes(depth=10)` (`subtype`),
   `supertypes(depth=10)` (`supertype`). `via_edge_kind = hop.ref.resolution_kind`. Global `seen_ids` dedup.
3. Reclassify: a `search` class whose `supertypes(depth=10)` intersect other seed classes becomes `source="subtype"`,
   `via_edge_kind="exact"`.
4. Sort by `(source_rank, -score)` with ranks `search 0, subtype 1, supertype 2, caller 3, callee 4` (stable).
5. Render: header lines `# Context for: <query>`, `# <N> symbols (search=<S>, expanded=<N-S>)`, blank; always
   emitted. `char_budget = tokens*4`; add blocks while `char_count + len(block) <= char_budget`; on first
   overflow set `truncated=True` (if nothing emitted yet also append
   `[truncated: context budget <T> tokens exceeded]`) and stop.
6. `token_estimate = char_count // 4`; `sources` counts emitted symbols by source.
Block format (`_render_symbol`), joined by `\\n` plus a trailing newline:
````
## <qualified_name>  (<kind>)  <file_path>:<start_line>
signature: <sig>            # if present
doc: <docstring>            # if present
```                          <- literal fence, snippet only if root given and file readable
<source lines start_line..end_line>
```
[via <source>, <resolution_kind>]   # only if source != "search"
````
Snippet: lines `start-1..end` (clipped), capped at 60 lines plus `    // ... (<n> more lines truncated)`.
### 6.10 `rg_tools.py` (exact search + coverage oracle)
- `RgHit(file, line, column, text)` frozen/slots. `rg_search(root, pattern, fixed_string=True)` runs
  `rg --line-number --column --no-heading --color=never [--fixed-strings] <pattern> .` with `cwd=root`,
  timeout 60; rc not in (0,1) → `RuntimeError`; parse `path:line:col:text` (split on first 3 colons, strip `./`).
- `enumerate_python_definitions(root) -> {name: [(file,line)]}`: `rg --line-number --no-heading --color=never -o
  '(?:async\\s+def|def|class)\\s+([A-Za-z_][A-Za-z0-9_]*)' .`, strip keyword prefix. Independent regex (not
  tree-sitter) on purpose: it is the oracle.
- `differential_coverage(store, root, sample_size=50, out=None) -> list[CoverageGap(name,file,line)]`:
  flatten+sort definitions, deterministic stride sample `flat[::max(1,len//sample)][:sample]`, ignore files
  containing parse-error markers, report definitions whose `(name, file)` is absent among `parse_ok`
  symbols; prints progress/gaps to `out` (default stderr). (Library function; **not wired to a CLI command**.)
- `iter_python_files(root)` helper.
### 6.11 `doctor.py`
`Check(name, ok, required, detail)` frozen/slots with `to_report_line()`: `"[*] name{:<28} tag{:<20} detail"`
where tag is `ok` / `MISSING` (required) / `missing (optional)`. `DoctorReport(checks)` with
`exit_code` (1 iff any required failed), `to_dict()` (`{"checks":[...],"exit_code":n}`), `to_text()`
(report lines, blank, then `Required capabilities missing: a, b. Install them before using codectx.` or
`All required capabilities present.`).
Checks, in order: python ≥ 3.12 (required); `rg` on PATH and `--version` first line (required);
imports `tree_sitter`, `tree_sitter_python`, `model2vec`, `numpy`, `orjson`, `pathspec` (required);
`mcp`, `tree_sitter_java` (optional). With `--repo`, integrity checks (all `required=False`):
1. `index_exists` — `<repo>/.codectx` present (else a hint with the `codectx index` command; stop).
2. `index_symbol_count` — manifest `symbol_count` equals non-empty line count of `symbols.jsonl`.
3. `index_has_symbols` — not (files>0 and symbols==0); failure text recommends `index --force`.
---
## 7. CLI specification
`cli.py`: `COMMANDS: dict[name → (description, flags|callable)]`. If the second element is callable it
is `add_arguments(subparser)` and the handler is looked up from a name→`cmd_*.cmd` map; otherwise it is a dict
of option specs and the handler is `_cmd_<name>` (only `doctor`). `main(argv=None) -> int`: no subcommand →
print help to stderr, return 2; `KeyboardInterrupt` → "Interrupted." return 130; `OSError/ValueError/
RuntimeError` → `codectx: error: <msg\>` to stderr, return 1. `-V/--version` prints `codectx 0.1.0`.
Handlers are imported at module top (the "lazy handler" comment in the original is aspirational — only
numpy/model2vec are truly lazy).
Common positional/flags (all except `doctor`): `repo` (positional, `nargs="?"`, default `.`; for `index`
and `embed` it is required), `--db PATH` (custom index dir). Index dir resolution
`resolve_index_dir(repo, db)` = `Path(db)` or `<repo.resolve()>/.codectx`.
Missing index → stderr `codectx: no index at <dir>. Run `codectx index <repo\>` first.` rc 1.
| Command | Args | Behaviour / output |
|---|---|---|
| `doctor` | `--json`, `--repo PATH` | print report (text or JSON); rc = report exit code |
| `index` | `repo`, `--stats`, `--db`, `--force` | `--force` → `store.clear()` first. Prints `Indexed <repo>: N new, N changed, N unchanged, N code files.` + `Index: <dir>`; with `--stats` prints JSON `{"index", **IndexStats, **store.stats()}`. Non-directory → rc 1 |
| `symbols` | `file`, `repo`, `--json`, `--db` | accepts abs or repo-relative path; line: `<kind:<10> <start:>5>-<end:<5> <name>  <signature> [parse-error]`; none → rc 1 |
| `search` | `query`, `repo`, `--mode lexical\\|semantic\\|hybrid` (default lexical), `-k` (10), `--db` | line `"<score:8.4f>  <kind:<10> <file:line:<40> <qualified_name>"`; hybrid prints `8.5f` score and `[L<n>+S<n>]` rank tags (1-based); no hits → stderr `No matches.` rc 1 |
| `embed` | `repo`, `--force`, `--db` | embeds all `parse_ok` symbols; skips if manifest `vector_model_id` equals configured model and not `--force`; prints `Embedded N symbols with <model>.` ; commits |
| `graph` | `symbol`, `repo`, `--callers\\|--callees\\|--supertypes\\|--subtypes` (mutually exclusive), `--depth` (1), `--db` | resolve symbol by exact `qualified_name`, else unique simple name (ambiguity → message, rc 1; not found → rc 1). Prints `# <qn>  (<kind>, <file>:<line>)`; default (no flag) prints `## callees`, `## callers` at depth 1, and for classes `## supertypes`/`## subtypes` at depth 10. Hop line `  <kind:<10> <file:line:<40> <qn>` + marker `[ambiguous]`, `[unresolved]`, or `[name_match, N candidates]`; empty → `  (none)`; unresolved hop prints `ref.kind` and target name |
| `context` | `query`, `repo`, `--tokens` (8000), `--depth` (1), `-k` (10), `--db` | prints pack to stdout; summary `--- N symbols, ~T tokens, truncated=…, sources={…} ---` to stderr; empty → `No context found.` rc 1 |
Search/graph/symbols/context open the store `readonly=True`; `index`/`embed` open writable.
---
## 8. Error handling policy
- Parse failures are data, not exceptions: placeholder symbol `<parse-error>` (`parse_ok=0`) + manifest
  `error:<path>`. Search excludes them by default; doctor/rg oracle treat them as visible, known failures.
- Unreadable files are skipped (`OSError`) during indexing.
- Model mismatch / vector problems → `RuntimeError` (CLI prints and returns 1); hybrid swallows it and degrades.
- Subprocess timeouts are 60 s (git/rg listing, rg search).
- Corrupt index recovery = `codectx index <repo> --force` (clears files/symbols/refs; vectors survive and are
  re-resolved by stable identity).
## 9. Performance and complexity notes
- Open cost O(index size). `symbol_by_id`, `symbols_by_name`, `_resolve_by_qname`, `refs_to_name`, `refs_from`
  are linear scans; graph traversal is therefore O(depth × frontier × N). Acceptable at the stated scale;
  a name→symbols dict and id→symbol dict are the obvious optimization (keep semantics identical).
- BM25 is rebuilt per query (milliseconds for thousands of symbols).
- Semantic: full-matrix normalize + matvec per query; no cache.
- Lexical and graph commands must not import numpy (tests assert `numpy` not in `sys.modules` after those paths).
## 10. Security and safety
- No network use other than model2vec's model download. No credentials. Index contains source-derived
  text (names, signatures, docstrings) — treat `.codectx/` like source (add to `.gitignore` if the repo is
  shared). Discovery honors `.gitignore`, so ignored secrets (e.g. `secret.env`) are not indexed.
- Subprocess calls use argument lists (no shell). Paths come from the user's own repo.
## 11. Testing strategy (acceptance suite)
Fixture `tests/fixtures/sample_pkg/`: `pkg/__init__.py` (a module docstring, `parse_user_data`,
`UserController` with `__init__`/`get_user`/async `create_user`, `main`), `pkg/broken.py` (docstring then
`def broken_function(` — truncated), `ignored_dir/hidden.py`, `secret.env`, `tests/__init__.py`, and a
`.gitignore` listing `__pycache__/ *.pyc .venv/ ignored_dir/ secret.env`. Tests copy it to `tmp_path`,
run `git init/add/commit` (with `GIT_AUTHOR_*`/`GIT_COMMITTER_*` env) so `git ls-files` is the discovery path.
Test files and what each must prove (names are the originals):
- `test_index`: gitignore respected, default skip dirs, files table populated, idempotent second run,
  changed file reindexed, deleted file removed, `index` command writes JSONL + stats, on-disk files diffable
  and stable on no-op.
- `test_extract`: nested classes/methods, async def, decorated def, docstring, signature, syntax error recorded
  (not swallowed), persistence, `broken.py` recorded, `symbols` command.
- `test_java` / `test_groovy`: classes/methods/constructors (`<init>`)/interfaces/enums/fields/javadoc/
  signature/refs attribution/end-to-end index/syntax-error; Spock spec names, qualified names, docstring
  `Spock spec: …`, fields as `variable`, `@Unroll` doesn't break name restore, spec→production graph link.
- `test_inheritance`: Python single/multiple/generic/attribute bases, no edges for plain class; Java
  extends/implements/generics/interface-extends/combined; supertypes/subtypes/multi-hop/empty cases;
  inheritance edges absent from callees.
- `test_graph`: refs for calls, imports, attribute-call uses attribute name; callees/callers; depth 2;
  cycle-safe; `graph` command.
- `test_search`: split_identifier (camel/snake/mixed), query_tokens, BM25 ranking/empty/missing-term,
  naming-style match, exact name outranks docstring mention, `search` command.
- `test_semantic` (skipped if model can't load): embed writes vectors, relevant symbol ranks, no vectors →
  empty, model mismatch raises. `test_hybrid`: RRF both-sources beats one-sided, degrades without vectors,
  fuses both, command.
- `test_context`: seed present, `file:line` citation, source snippet, graph expansion, dedup, budget
  truncation, non-exact edge marker, command, fixture pack.
- `test_incremental`: lexical search and graph traversal do not import numpy/model2vec (checked via
  `sys.modules` in a subprocess), unchanged files skip extraction, orphan cleanup, byte-stable no-op, `--force` recovers
  a corrupted `symbols.jsonl`, vectors survive id renumbering, stale vector rows dropped.
- `test_rg_tools`: rg search hit/no-hit, definition enumeration, differential coverage clean / detects
  missing symbol / command. `test_doctor`: structured report, exit code, marker semantics, text lists
  every check, CLI returns code, `--repo` detects missing and corrupt index.
Quality gates: `ruff check` clean; `pytest` green (semantic tests need the model or skip).
Run with `UV_LINK_MODE=copy uv run --extra java --extra dev pytest` (copy mode avoids hardlink failures on
the `/home` ↔ `/mnt/c` split; use an out-of-tree `UV_PROJECT_ENVIRONMENT` if the repo sits on a filesystem
where venv creation misbehaves).
## 12. Build plan (recommended regeneration order)
1. Scaffold: `pyproject.toml`, `src/codectx/__init__.py`, `cli.py` with `doctor` + `doctor.py` → `codectx doctor` works.
2. `store.py` + `model.py` (round-trip tests).
3. `index.py` discovery + hashing + incremental (stub `extract_fn`) → `cmd_index`.
4. `languages/_util.py`, `languages/python.py`, `extract.py` → `cmd_symbols`.
5. `graph.py` (persist + callers/callees) → `cmd_graph`; then inheritance edges + supertypes/subtypes.
6. `tokens.py`, `bm25.py`, `search.py` → `cmd_search --mode lexical`.
7. `semantic.py` + `cmd_embed`; `store` vectors with stable-identity rows.
8. `hybrid.py` (RRF, then subtype boost).
9. `context.py` + `cmd_context`.
10. `languages/java.py`, then `languages/groovy.py` (+ registry entries, extension map).
11. `rg_tools.py`, doctor index-integrity checks, final byte-stability + `--force` tests.
## 13. Extension points
- New language: `languages/<lang>.py` with `extract`/`extract_refs`; register in `extract._load_module` and
  `_SUPPORTED_LANGS`; extend `index.SUPPORTED_CODE_EXTENSIONS` and `detect_language`.
- New edge kind: add to `graph.EDGE_KINDS`; put it in either `_INHERITANCE_KINDS` or the call-graph set.
- New command: `cmd_<name>.py` with `add_arguments(parser)` and `cmd(args) -> int`; register in `COMMANDS` and
  the handler map in `cli.build_parser`.
- Model swap: `CODECTX_MODEL_NAME`; re-run `codectx embed --force` (mismatch otherwise errors in semantic mode).
- Future: MCP server (extra already declared), CLI for the differential oracle, id/name dictionaries in `Store`.
---
## 14. Known defects / quirks of the original (decide: reproduce or fix)
Reproduce them for strict parity; fix them for a better rebuild (and adjust the tests accordingly).
1. **BM25 IDF has no logarithm** — docstring says `ln(...)`, code returns `(N-df+0.5)/(df+0.5)+1`.
   Standard Okapi: `ln((N-df+0.5)/(df+0.5)+1)`. Rankings still work in tests; fixing changes absolute scores.
2. **`pathspec` is a declared dependency but never imported** (doctor still requires it).
3. **Python `variable` symbols are never emitted** (`assignment` has no `name` field; `left` would be needed).
   README claims module/class-level variables. Java fields *are* emitted.
4. **Java `_walk_for_refs` contains an unreachable second inheritance block** (the scope-node branch returns
   first); inheritance is correctly emitted by `_extract_inheritance`. Safe to drop.
5. **Stale refs after reindex of a changed file**: pruning keeps refs whose `source_qualifier` matches *any*
   remaining symbol qualified name (not scoped to the file) and keeps all `<module>` refs, so (a) re-extracting
   a changed file duplicates its `<module>` import refs and (b) refs from a same-named qualifier in another
   file survive deletions. Fix: store `file_path` on `RefRecord` (format_version bump) and prune by file.
   Verified for (a): after editing `a.py` (`import os` + `def f(): g()`) and reindexing, `refs.jsonl` held
   two `('<module>','os','imports')` rows. (b) is inferred from the pruning code, not reproduced.
6. **Resolution at persist time sees partial state.** A ref to a symbol in a not-yet-indexed file is stored
   `unresolved`. Verified: `a.py` calling `g()` defined in `b.py` was stored `unresolved` on the first index
   (files are processed in `git ls-files` order). `callees`/`supertypes`/`subtypes` refresh it through
   `_live_resolution`, but `callers` returns the stored kind unrefreshed. The stored value is corrected
   only when the *source* file is re-extracted. Fix: resolve in a second pass after all files are extracted.
7. **`parent_id` repair uses a global qualified-name map** → collisions when two files define the same qualified name.
8. **`IndexStats.skipped`** counts reindexed files (`total - indexed - unchanged`).
9. **Qualified-name collisions** across files make `_resolve_by_qname`/`graph` pick the first match.
10. **`split_identifier("XMLParser")` yields only `['xmlparser']`** (verified); the docstring in `tokens.py` claims
    `xmlparser, xml, parser`. Fix by inserting a space in `([A-Z]+)([A-Z][a-z])` boundaries before the split.
11. **`extract_and_persist` skips ref extraction for parse-failed files** and Groovy forces `parse_ok=True`
    whenever any class symbol exists — intentional.
12. **Embedding at index time**: `embed` is separate; `index --force` leaves vectors in place on purpose.
13. **Hardcoded version string in three places**; `kind="import"` and edge kind `references` and
    `resolution_kind="ambiguous"` are declared but never produced.
14. **`rg_tools.differential_coverage` is Python-only and has no CLI entry** despite the README describing it.
15. **Index discovery includes untracked-but-not-ignored files** (`--others --exclude-standard`), although a
    docstring says "tracked files only". Verified: an untracked `u.py` appeared in `files.jsonl`.
16. **`index --stats` JSON key collision:** `{"index": <dir>, **IndexStats, **store.stats()}`. `store.stats()`
    also has an `index` key, which wins. Both hold the same path unless `--db` is relative.
## 15. Acceptance checklist for a regenerated project
- [ ] `codectx doctor` exits 0 with all required checks `[*]`; `--repo` reports index state.
- [ ] `codectx index <repo>` twice: second run reports 0 new, 0 changed; `symbols.jsonl` byte-identical.
- [ ] `.gitignore`d files/dirs never appear in `files.jsonl`.
- [ ] Truncated Python file yields a `<parse-error>` symbol with `parse_ok=0`, not silence.
- [ ] `codectx search "user controller"` ranks `UserController` first (lexical, no numpy import).
- [ ] After `codectx embed`, `--mode hybrid` output shows `[L#+S#]` tags; with `CODECTX_MODEL_NAME` changed,
      `--mode semantic` errors and `--mode hybrid` degrades to lexical.
- [ ] `graph main --callees` lists `parse_user_data`; `--callers parse_user_data` lists `main`.
- [ ] `graph <Base> --subtypes` / `<Child> --supertypes` traverse only `extends`/`implements`.
- [ ] `context "<q>" --tokens 50` truncates and reports `truncated=True`; graph-expanded blocks end with
      `[via <source>, <resolution_kind>]`.
- [ ] Groovy Spock spec method appears with its human-readable name; `callers(productionMethod)` returns it.
- [ ] Corrupting `symbols.jsonl` → `doctor --repo` flags it; `index --force` repairs it.
- [ ] `ruff check` and `pytest` pass.