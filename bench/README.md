# Benchmark protocol

The targets are the five shallow-cloned repository snapshots under `$CODECTX_BENCH_REPOS` (default `~/repo`): Django, LangChain, Spring Boot, Kafka, and OpenJDK jdk21u. Commit hashes are stored in each evaluation JSON. The complete discovered tree is indexed, including tests and examples. Unsupported files are counted/hashed, but only `.py`, `.java` and `.groovy` produce symbols. In particular, this does not evaluate Kafka's Scala code or OpenJDK's native C/C++ implementation.

## Workloads and relevance

`queries.json` contains **50 manually authored natural-language queries, ten per repository**, each with one intended class/interface and its source file. Targets are validated directly in source by `make_queries.py`, independently of search output. These labels cover prominent APIs, not a representative random sample of developer tasks. Other useful files may be penalized by the single-target gold set. The small sample cannot establish a general superiority claim.

Separately, each repository gets up to **100 exact-name lookup queries**, sampled with seed 1729 from parse-healthy classes/functions/methods whose bare names are unique across that index. This diagnostic intentionally avoids impossible same-name disambiguation. Names come from the index, so this workload cannot measure missing-symbol coverage or natural-language understanding. All generated labels and rankings are retained in evaluation JSON.

Systems: symbol BM25, static semantic embeddings, RRF hybrid with the design's subtype boost, RRF without the boost, and whole-file BM25. The file BM25 baseline reads full supported-language sources (bodies, strings, comments and docs), with the same identifier splitting and Okapi scoring; codectx reads symbol metadata. Natural-language queries also run a simple `rg -i -l` OR of non-stopword query tokens; results are sorted by filename. That is a basic text-search baseline without relevance ranking, not a claim about the best possible grep workflow.

For symbol metrics the intended symbol name+file is relevant (multiple overloads count as relevant). For file metrics, symbol hits are collapsed by first occurrence to distinct files. Each system requests 100 candidates; reported cutoffs are 1/5/10. File-level recall is a hit rate because each query has one gold file. MRR@10 is truncated at 10; a miss contributes zero. Results include symbol and file metrics separately. Pooled values weight queries equally. Bootstrap intervals, when shown, resample the fixed query set and do not establish population representativeness.

Source docs stay present for every system. This is an independent manually authored question set, not a docstring-to-symbol retrieval task. No prompt generation, LLM judging, external APIs, model fine-tuning or post-result query tuning is used.

## Timing and memory

Indexing and no-op reindexing run serially in fresh subprocesses with `/usr/bin/time -v`; wall time and peak RSS are retained. These are filesystem-cache-dependent runs on a shared WSL host, not controlled cold-disk benchmarks. Initial instrumentation was run while the implementation was being completed; any changes affecting these runs are recorded in the report. Evaluation includes an additional no-op byte-stability check in a separate subprocess. Search evaluation loads inheritance references only, matching the hybrid search command; full reference records are streamed for graph diagnostics. Saved benchmark context packs use depth 0 to isolate retrieved snippets; graph expansion is checked in acceptance tests.

Embedding is measured separately. All evaluation runs set `HF_HUB_OFFLINE=1`, `OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1`, and `TOKENIZERS_PARALLELISM=false`. The model is `minishlab/potion-code-16M-v2`, downloaded before offline evaluation.

Warm query latency reuses BM25 postings, memory-mapped vectors and cached norms, the model and store in one process; it requests 100 candidates and includes scoring, sorting and subtype boosts, but excludes first-time construction and store loading. The first query is retained; there is no hidden warmup removal. Cold CLI latency uses three new processes per mode with `-k 10` (one per mode for indexes above 500,000 symbols, due to their substantial startup cost; those values are single observations), including store/model loading and BM25 construction. It means a cold process, not an empty OS page cache. Peak RSS from the evaluation process also includes the full-source baseline and validation work, so it is not codectx-only serving memory.

The design's subtype boost is evaluated unchanged mathematically. Do not assume it improves accuracy; the no-boost ablation tests this explicitly.

## Independent extraction checks

* **Python**: the standard library AST parser supplies definition locations, call-name/source-scope edges and simple inheritance edges. Syntactically invalid files are listed and excluded from AST edge comparison.
* **Java**: a separate comment/string-stripped regex samples named type declarations only. It does not validate method/field coverage, overloaded dispatch, or call-graph precision. Regex limitations remain possible; gaps are retained for inspection.
* Definition coverage uses a deterministic sample of up to 500 per repository from these independent oracles. Python comparison includes line; Java comparison uses file+name to allow annotations to precede declaration lines.
* Python graph scores compare **syntactic edge extraction**, not actual runtime dispatch. Java graph target correctness is not independently scored. Resolution category counts are diagnostics, not correctness scores.

Parse errors are reported even if partial symbols were recovered. A separate 16-case acceptance suite checks incremental edits/deletions, collision pruning, stale vectors, ambiguity, parser languages, context budget, recovery and lazy imports. The original source and original 110-test suite are unavailable.

The first full-store OpenJDK no-op evaluation was deliberately interrupted due to memory pressure, then rerun with immutable string pooling. Earlier repository timing samples precede that loader-only change; final OpenJDK samples follow it. The raw interruption record is retained. This is an exploratory engineering assessment across implementation fixes, not a frozen-version performance comparison.

Cold CLI subprocesses run while the evaluator retains its warm search data and file-BM25 baseline. On the largest corpus this can cause shared-host memory contention; cold samples are exploratory observations, not isolated production latency estimates. Evaluation peak RSS in JSON is for the evaluator process and includes validation/baseline work; it is not a combined parent-plus-child memory figure.

Filesystem placement: source checkouts are under `~/repo` on the Linux filesystem. Benchmark indexes and the virtual environment were placed on the Windows-shared filesystem during initial runs, and the model cache is under the Linux home directory. This placement affects I/O and cold import/index loading; no alternative-filesystem timing comparison was performed.
