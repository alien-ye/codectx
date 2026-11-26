# codectx: assessment on five public source repositories

This is a new implementation rebuilt from the supplied design. The missing original source and its claimed 110-test suite were unavailable. See [methodology](README.md), [frozen natural-language labels](queries.json), and [implementation differences](../README.md).

## Corpus, indexing and storage

| Repository | Code files | Symbols | Files with parse errors | Initial s | No-op s | Index peak RSS MiB | Index + vectors MiB |
| --- | --- | --- | --- | --- | --- | --- | --- |
| langchain | 2672 | 27353 | 0 | 10.94 | 16.64 | 143 | 68.8 |
| django | 2943 | 60397 | 1 | 18.83 | 25.77 | 275 | 142.5 |
| spring-boot | 8467 | 83293 | 32 | 31.74 | 44.43 | 495 | 260.7 |
| kafka | 6510 | 128267 | 3 | 65.88 | 110.88 | 1076 | 478.3 |
| jdk21u | 50470 | 869718 | 199 | 313.58 | 322.97 | 1794 | 1988.2 |

All discovered source trees include tests/examples. Only Python, Java and Groovy are analyzed; unsupported files are still discovered/hashed. Parse-error counts can include intentional invalid fixtures, source templates or grammar limitations; they are not counts of broken upstream code. Peak RSS here is the index subprocess, not the later evaluation workload. These runs use cached files on a shared WSL host and are not controlled cold-disk timings. Initial runs occurred during implementation: streaming serialization, compact postings, selective reference loading, memory-mapped embeddings, immutable string pooling and iterative traversal were added during this phase; the retained recursion-failure log precedes the successful OpenJDK retry. No-op timing includes loading and rewriting the plain-file store. Source checkouts are on the Linux filesystem; indexes and the virtual environment are on the Windows-shared filesystem under ~/share, which affects I/O and cold imports. No alternate-filesystem benchmark was run.

The first OpenJDK no-op evaluation was deliberately interrupted after about five minutes and 2,479,440 KiB peak RSS while it was swapping heavily. It was restarted after pooling repeated immutable strings during JSONL load; see [the interruption record](results/jdk21u-memory-pressure.json). LangChain/Django/Spring Boot/Kafka timings were collected before this final pooling change, and the final OpenJDK evaluation afterward. Treat cross-repository timing comparisons as exploratory measurements rather than a frozen-version performance contest. Retrieval algorithms and labels were unchanged by pooling.

## Natural-language retrieval: ten questions per repository

| Repository | System | File R@1 | File R@10 | File MRR@10 | Symbol R@10 |
| --- | --- | --- | --- | --- | --- |
| langchain | lexical | 0.0% | 80.0% | 0.184 | 0.0% |
| langchain | semantic | 20.0% | 80.0% | 0.417 | 40.0% |
| langchain | hybrid | 40.0% | 80.0% | 0.523 | 40.0% |
| langchain | hybrid_no_boost | 10.0% | 60.0% | 0.275 | 10.0% |
| langchain | file_bm25 | 10.0% | 90.0% | 0.359 | — |
| langchain | rg_or | 0.0% | 0.0% | 0.000 | — |
| django | lexical | 10.0% | 60.0% | 0.243 | 10.0% |
| django | semantic | 20.0% | 80.0% | 0.366 | 20.0% |
| django | hybrid | 20.0% | 80.0% | 0.437 | 30.0% |
| django | hybrid_no_boost | 20.0% | 70.0% | 0.328 | 10.0% |
| django | file_bm25 | 20.0% | 70.0% | 0.364 | — |
| django | rg_or | 0.0% | 0.0% | 0.000 | — |
| spring-boot | lexical | 20.0% | 40.0% | 0.283 | 10.0% |
| spring-boot | semantic | 10.0% | 30.0% | 0.145 | 10.0% |
| spring-boot | hybrid | 10.0% | 70.0% | 0.252 | 30.0% |
| spring-boot | hybrid_no_boost | 20.0% | 60.0% | 0.281 | 20.0% |
| spring-boot | file_bm25 | 20.0% | 60.0% | 0.295 | — |
| spring-boot | rg_or | 0.0% | 0.0% | 0.000 | — |
| kafka | lexical | 30.0% | 30.0% | 0.300 | 0.0% |
| kafka | semantic | 20.0% | 50.0% | 0.261 | 30.0% |
| kafka | hybrid | 0.0% | 50.0% | 0.116 | 20.0% |
| kafka | hybrid_no_boost | 20.0% | 50.0% | 0.263 | 30.0% |
| kafka | file_bm25 | 0.0% | 70.0% | 0.202 | — |
| kafka | rg_or | 0.0% | 0.0% | 0.000 | — |
| jdk21u | lexical | 20.0% | 50.0% | 0.277 | 0.0% |
| jdk21u | semantic | 20.0% | 60.0% | 0.328 | 20.0% |
| jdk21u | hybrid | 20.0% | 70.0% | 0.331 | 40.0% |
| jdk21u | hybrid_no_boost | 20.0% | 50.0% | 0.278 | 0.0% |
| jdk21u | file_bm25 | 20.0% | 70.0% | 0.353 | — |
| jdk21u | rg_or | 0.0% | 0.0% | 0.000 | — |

### Pooled results

| System | Questions | File R@10 | File MRR@10 | MRR bootstrap 95% interval |
| --- | --- | --- | --- | --- |
| lexical | 50 | 52.0% | 0.258 | [0.164, 0.359] |
| semantic | 50 | 60.0% | 0.303 | [0.209, 0.406] |
| hybrid | 50 | 70.0% | 0.332 | [0.236, 0.432] |
| hybrid_no_boost | 50 | 58.0% | 0.285 | [0.188, 0.390] |
| file_bm25 | 50 | 72.0% | 0.315 | [0.226, 0.406] |
| rg_or | 50 | 0.0% | 0.000 | [0.000, 0.000] |

These are descriptive results for 50 prominent-API questions, with one intended class/file per query. They do not establish broad superiority or represent all coding tasks. Intervals resample these fixed labels, not the wider task population. `rg_or` is a simple filename-ordered text baseline. File BM25 reads method bodies, literals and docs; codectx reads symbol metadata.

## Exact-identifier lookup diagnostic

| Repository | System | Queries | File R@10 | File MRR@10 | Symbol R@10 |
| --- | --- | --- | --- | --- | --- |
| langchain | lexical | 100 | 100.0% | 0.995 | 100.0% |
| langchain | semantic | 100 | 100.0% | 0.977 | 96.0% |
| langchain | hybrid | 100 | 100.0% | 0.857 | 96.0% |
| langchain | hybrid_no_boost | 100 | 100.0% | 0.985 | 99.0% |
| langchain | file_bm25 | 100 | 96.0% | 0.865 | — |
| django | lexical | 100 | 100.0% | 1.000 | 100.0% |
| django | semantic | 100 | 100.0% | 0.988 | 100.0% |
| django | hybrid | 100 | 94.0% | 0.630 | 90.0% |
| django | hybrid_no_boost | 100 | 100.0% | 0.995 | 100.0% |
| django | file_bm25 | 100 | 94.0% | 0.794 | — |
| spring-boot | lexical | 100 | 100.0% | 0.995 | 100.0% |
| spring-boot | semantic | 100 | 98.0% | 0.907 | 96.0% |
| spring-boot | hybrid | 100 | 99.0% | 0.827 | 99.0% |
| spring-boot | hybrid_no_boost | 100 | 100.0% | 0.968 | 100.0% |
| spring-boot | file_bm25 | 100 | 97.0% | 0.840 | — |
| kafka | lexical | 100 | 100.0% | 0.993 | 100.0% |
| kafka | semantic | 100 | 99.0% | 0.975 | 99.0% |
| kafka | hybrid | 100 | 99.0% | 0.911 | 98.0% |
| kafka | hybrid_no_boost | 100 | 100.0% | 0.991 | 99.0% |
| kafka | file_bm25 | 100 | 96.0% | 0.764 | — |
| jdk21u | lexical | 100 | 100.0% | 0.981 | 98.0% |
| jdk21u | semantic | 100 | 96.0% | 0.895 | 91.0% |
| jdk21u | hybrid | 100 | 91.0% | 0.609 | 88.0% |
| jdk21u | hybrid_no_boost | 100 | 98.0% | 0.937 | 96.0% |
| jdk21u | file_bm25 | 100 | 91.0% | 0.840 | — |

Names are sampled from parse-healthy indexed symbols and must be globally unique. This measures known-symbol lookup, excludes ambiguities, and cannot detect missing symbols. It is not natural-language accuracy.

## Extraction and graph diagnostics

| Repository | Definition sample | Definition recall | Python call edges gold | Call precision | Call recall | Python base edges gold | Base recall | No-op JSONL stable |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| langchain | 500 | 100.0% | 73763 | 99.7% | 100.0% | 2091 | 100.0% | True |
| django | 500 | 100.0% | 189046 | 100.0% | 100.0% | 9834 | 100.0% | True |
| spring-boot | 500 | 99.8% | 0 | — | — | 0 | — | True |
| kafka | 500 | 100.0% | 9927 | 100.0% | 100.0% | 202 | 100.0% | True |
| jdk21u | 500 | 99.0% | 13 | 100.0% | 100.0% | 0 | — | True |

The definition oracle is CPython AST for Python and comment-stripped regex **type declarations only** for Java. Java method/field recall and Java graph precision are not measured. Python graph values compare syntactic calls and simple base names, not receiver resolution or runtime dispatch. Inspect the raw missing/extra edge samples before treating differences as extractor defects; independent oracle scope attribution can differ for decorators and definition-time expressions.

| Repository | Call references | Unique bare-name candidate | Multiple candidates | No candidate |
| --- | --- | --- | --- | --- |
| langchain | 74819 | 34.4% | 29.9% | 35.8% |
| django | 191485 | 29.8% | 41.2% | 29.0% |
| spring-boot | 249762 | 15.6% | 65.3% | 19.1% |
| kafka | 764523 | 16.1% | 64.0% | 19.9% |
| jdk21u | 1941028 | 10.5% | 89.3% | 0.2% |

A unique bare-name candidate is labeled `exact` to match the design vocabulary. It is **not** proof of a correct semantic target. Overloads, shared method names, inheritance, reflection and dynamic calls limit this graph.

## Performance: warm queries versus new CLI processes

| Repository | Search view load s | Embed s | Warm hybrid median ms | Warm hybrid p95 ms | New CLI lexical s | New CLI hybrid s | Evaluation peak RSS MiB |
| --- | --- | --- | --- | --- | --- | --- | --- |
| langchain | 3.18 | 9.79 | 17.9 | 20.5 | 2.12 | 8.48 | 215 |
| django | 5.81 | 11.86 | 26.5 | 255.5 | 3.62 | 12.55 | 360 |
| spring-boot | 11.46 | 21.55 | 34.4 | 86.0 | 7.01 | 23.05 | 369 |
| kafka | 36.83 | 64.32 | 86.4 | 150.4 | 11.94 | 35.90 | 501 |
| jdk21u | 77.72 | 156.85 | 262.4 | 558.1 | 72.99 | 138.83 | 2263 |

Warm queries reuse the search view, packed postings, memory-mapped vectors with cached norms, and model, retrieving 100 candidates; CLI samples use three fresh processes per mode with k=10, except indexes above 500,000 symbols use one observation per mode. The OpenJDK values are single observations, not robust latency estimates. Search views load inheritance references for boosting; full references are streamed for diagnostics. Cold CLI subprocesses share this limited-memory host with the evaluator, which retains the warm search data and file baseline; contention can affect cold wall times, especially for OpenJDK. Evaluation peak memory is the evaluator process only, includes validation and the full-source BM25 baseline, and cannot be attributed solely to codectx. Offline inference uses one BLAS thread and no network. See each JSON for setup costs and raw timings.

## Context packs and correctness checks

* [langchain sample](results/langchain-context.md): 5 symbols, ~965 estimated tokens in a 4000-token character budget; truncated=False; 1.39s.

* [django sample](results/django-context.md): 5 symbols, ~1621 estimated tokens in a 4000-token character budget; truncated=False; 3.85s.

* [spring-boot sample](results/spring-boot-context.md): 5 symbols, ~1199 estimated tokens in a 4000-token character budget; truncated=False; 6.07s.

* [kafka sample](results/kafka-context.md): 5 symbols, ~2088 estimated tokens in a 4000-token character budget; truncated=False; 8.89s.

* [jdk21u sample](results/jdk21u-context.md): 5 symbols, ~3029 estimated tokens in a 4000-token character budget; truncated=False; 50.14s.


The budget uses four characters per token, not a model tokenizer. Saved benchmark packs use graph depth 0 to isolate retrieved snippets. Graph expansion and provenance are checked in acceptance tests. The acceptance test output is [retained here](results/acceptance-tests.txt); the suite covers ignored paths, edit/deletion cleanup, file collisions, ambiguity, graph edges, context budgets, language extraction, corruption recovery, stale vectors, lazy imports, semantic model mismatch, fusion and deeply nested Java expressions.

Parser diagnostics are available in [parse-diagnostics.json](results/parse-diagnostics.json). Examples include Spring Boot annotated Java varargs and Groovy DSL constructs, Kafka archetype resource templates, and Unicode identifier forms in OpenJDK tests. These observations describe parser failures, not compiler validation of the source.

## Assessment and next work

On this fixed natural-language set, **hybrid** has the highest pooled file MRR@10 (0.332). This result is specific to these labels and snapshots. Compare hybrid and hybrid_no_boost before retaining the subtype boost.

For exact-name lookup, pooled file MRR@10 is 0.993 with lexical search, 0.767 with boosted hybrid, and 0.975 without the boost. For natural-language questions, boosted/unboosted hybrid MRR@10 is 0.332/0.285. Route explicit names and open-ended questions according to these separate measurements; the subtype boost is not a universally helpful ranking rule.

Indexes above the design's approximate 100,000-symbol assumption: kafka: 128,267; jdk21u: 869,718. Their successful runs demonstrate feasibility on these snapshots, not an unlimited scale guarantee.

The implementation is useful as a local, inspectable source-location retriever. Its main structural limits are metadata-only lexical documents, heuristic name resolution, plain-file load/rewrite costs, and whole-index memory use. Kafka and OpenJDK should be checked against the design’s approximate 100,000-symbol scale assumption. Priorities are source-body retrieval/reranking experiments, type-aware graph resolution and overload identities, read-only cached index services, compact storage, stronger Java method/call oracles, and a larger externally authored task set. None of those are claimed implemented by this benchmark.

## Reproducibility and evidence

* **langchain** `fb10639a73d980ce05ea8614a84deaf08d572550`: [raw evaluation](results/langchain-evaluation.json), [execution log](results/langchain-evaluation.log), [initial index](results/langchain-index-initial.json), [no-op index](results/langchain-index-noop.json).

* **django** `f14af5a88472ca10e2e94b37d6c17ee48cbdeb4d`: [raw evaluation](results/django-evaluation.json), [execution log](results/django-evaluation.log), [initial index](results/django-index-initial.json), [no-op index](results/django-index-noop.json).

* **spring-boot** `ebb5e11c70c50469c45f8aada56dd6d477c6b77f`: [raw evaluation](results/spring-boot-evaluation.json), [execution log](results/spring-boot-evaluation.log), [initial index](results/spring-boot-index-initial.json), [no-op index](results/spring-boot-index-noop.json).

* **kafka** `259b43a58e5dbe3276c727601c97de1b2c008c45`: [raw evaluation](results/kafka-evaluation.json), [execution log](results/kafka-evaluation.log), [initial index](results/kafka-index-initial.json), [no-op index](results/kafka-index-noop.json).

* **jdk21u** `5d9cac4049895a80fcdefa9bb1b81e021fdabb33`: [raw evaluation](results/jdk21u-evaluation.json), [execution log](results/jdk21u-evaluation.log), [initial index](results/jdk21u-index-initial.json), [no-op index](results/jdk21u-index-noop.json).


Environment and locked dependency versions are in [environment.json](results/environment.json) and [uv.lock](../uv.lock). Run instructions are in [the protocol](README.md). No source repository test suites were run; this assesses codectx against their source snapshots.
