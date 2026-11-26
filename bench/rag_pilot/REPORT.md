# codectx RAG pilot

**Result:** with the existing potion-code-16M-v2 embeddings and the stock codectx packer, all labeled behavior-source spans were present for **8/10 behavior questions**, versus **3/10** for file BM25 plus window selection. This measures supplied evidence, not generated-answer accuracy.

This pilot has 20 questions over the same five pinned source snapshots: 10 behavior, 5 location, and 5 intentionally unanswerable deployment/runtime questions. It follows the [larger retrieval benchmark](../REPORT.md). Eight behavior questions explicitly name a method; the other two name a class/operation. This workload favors precise code navigation and does not replace the earlier open-ended natural-language benchmark.

## Objective context measurements

| Condition | Behavior: all reference spans | Behavior: reference claims covered | Location: intended file present |
| --- | --- | --- | --- |
| none | 0/10 | 0/25 | 0/5 |
| bm25 | 3/10 | 8/25 | 1/5 |
| codectx | 8/10 | 21/25 | 4/5 |
| gold | 10/10 | 25/25 | 5/5 |

Every context uses the same 6,000-character limit. Codectx uses k=10 and graph depth 0. BM25 ranks full supported-language files, then 30-line windows from its top ten files. Gold uses labeled source windows without reference answers. None contains no source evidence. No generation model is used to compute these measurements.

Reference-span coverage is conservative: equivalent evidence in a test or Javadoc may also answer a question without covering the labeled implementation lines. In particular, the BM25 ConcurrentHashMap excerpt includes method-contract statements about null arguments and recursion even though not all labeled body spans appear. Location questions are scored by intended file presence because a method belonging to a class can establish its location without the class declaration. Five deployment cases have no source-only gold answer and are excluded from coverage denominators.

## What the assistant walkthrough showed

* **S1, Spring profiles:** the no-context answer incorrectly expected a Spring assertion/IllegalArgumentException. Codectx supplied the actual setter: it replaces an unmodifiable LinkedHashSet through Arrays.asList. Null-array failure is NullPointerException under the JDK contract. The BM25 context instead showed similarly named builder/augmentation APIs, which cannot establish the setter behavior.

* **S2, availability defaults:** the no-context answer said liveness CORRECT. The actual default is **BROKEN**; readiness is REFUSING_TRAFFIC. Both codectx and BM25 supplied the relevant interface default methods.

* **D1, QuerySet slicing:** codectx found the intended file but packed the class header and neighboring tests, omitting __getitem__. BM25 supplied the actual negative-bound guard and stepped-slice branch.

* **K2, buffer shutdown:** both retrievers supplied related memory-waiter code but omitted the close methods. Normal memory-availability signaling does not prove the shutdown call chain. The reference shows RecordAccumulator.close → free.close → BufferPool.close → signal() on each waiter.

These examples demonstrate why learned API knowledge, intended-file hits and grounded answers are different measurements. They do not establish a causal answer-accuracy improvement.

## Answer artifacts and limits

The [80 answer artifacts](results/interactive-answers.jsonl) are the current assistant's interactive walkthrough: 20 frozen no-context answers, then 60 source-reviewed answers/abstentions for the other conditions. They were **not** produced by 80 independent API requests. The same assistant read references, answered and reviewed; later conditions share conversation state. Temperature, exact model-serving configuration, per-answer token counts and generation latency are unavailable and are recorded as missing. There is no independent or blind answer-quality score. Running record_interactive.py only packages the authored transcript; it does not execute a model.

All 50 recorded citations point to valid source ranges contained in the supplied context ranges. This is citation geometry, **not semantic support precision**. Use the [review worksheet](results/answer-review.csv) to grade correctness, faithfulness, citation support and abstention independently.

## Run any local generation model

The [model runner](run_model.py) supports Ollama and OpenAI-compatible local servers. It sends fresh stateless chats, uses the same questions/contexts for every model, records actual usage and wall time when supplied, and checkpoints every completed request. Failed requests are retryable. The [optional judge](judge_model.py) grades required claims against the reference and checks groundedness only against actual retrieved evidence; its results remain fallible and need independent review. See the [run instructions](README.md). No local answer-generator performance is claimed from mocked protocol tests.

All 80 reusable [model-server prompts](results/prompts/) are exported without reference answers. A separate model service allows real condition isolation; the interactive walkthrough cannot provide that isolation. There is no need to install another local LLM to inspect context quality or perform this walkthrough.

## Recommended tool changes

1. Add body-aware retrieval or a lexical body/chunk fallback for questions such as negative-slice behavior.
2. Prefer the matching qualified method over broad classes or similarly named APIs.
3. Measure packed evidence after budget/truncation, not just whether a file was retrieved.
4. Evaluate graph expansion separately on cross-file questions such as shutdown signaling; it was disabled in this pilot.
5. Use independent, held-out questions and fresh generator/judge calls before reporting RAG answer accuracy or comparing local LLMs.

## Per-case evidence audit

| Case | Repository | Type | Codectx | BM25 | Actual prompts |
| --- | --- | --- | --- | --- | --- |
| D1 | django | behavior | 0/2 claim spans | 2/2 claim spans | [codectx](results/prompts/D1-codectx.json) / [BM25](results/prompts/D1-bm25.json) |
| D2 | django | behavior | 3/3 claim spans | 0/3 claim spans | [codectx](results/prompts/D2-codectx.json) / [BM25](results/prompts/D2-bm25.json) |
| D3 | django | location | file present | file absent | [codectx](results/prompts/D3-codectx.json) / [BM25](results/prompts/D3-bm25.json) |
| D4 | django | unanswerable | runtime evidence required | runtime evidence required | [codectx](results/prompts/D4-codectx.json) / [BM25](results/prompts/D4-bm25.json) |
| L1 | langchain | behavior | 2/2 claim spans | 0/2 claim spans | [codectx](results/prompts/L1-codectx.json) / [BM25](results/prompts/L1-bm25.json) |
| L2 | langchain | behavior | 2/2 claim spans | 0/2 claim spans | [codectx](results/prompts/L2-codectx.json) / [BM25](results/prompts/L2-bm25.json) |
| L3 | langchain | location | file present | file absent | [codectx](results/prompts/L3-codectx.json) / [BM25](results/prompts/L3-bm25.json) |
| L4 | langchain | unanswerable | runtime evidence required | runtime evidence required | [codectx](results/prompts/L4-codectx.json) / [BM25](results/prompts/L4-bm25.json) |
| S1 | spring-boot | behavior | 3/3 claim spans | 0/3 claim spans | [codectx](results/prompts/S1-codectx.json) / [BM25](results/prompts/S1-bm25.json) |
| S2 | spring-boot | behavior | 2/2 claim spans | 2/2 claim spans | [codectx](results/prompts/S2-codectx.json) / [BM25](results/prompts/S2-bm25.json) |
| S3 | spring-boot | location | file present | file absent | [codectx](results/prompts/S3-codectx.json) / [BM25](results/prompts/S3-bm25.json) |
| S4 | spring-boot | unanswerable | runtime evidence required | runtime evidence required | [codectx](results/prompts/S4-codectx.json) / [BM25](results/prompts/S4-bm25.json) |
| K1 | kafka | behavior | 3/3 claim spans | 3/3 claim spans | [codectx](results/prompts/K1-codectx.json) / [BM25](results/prompts/K1-bm25.json) |
| K2 | kafka | behavior | 0/2 claim spans | 0/2 claim spans | [codectx](results/prompts/K2-codectx.json) / [BM25](results/prompts/K2-bm25.json) |
| K3 | kafka | location | file absent | file absent | [codectx](results/prompts/K3-codectx.json) / [BM25](results/prompts/K3-bm25.json) |
| K4 | kafka | unanswerable | runtime evidence required | runtime evidence required | [codectx](results/prompts/K4-codectx.json) / [BM25](results/prompts/K4-bm25.json) |
| J1 | jdk21u | behavior | 3/3 claim spans | 0/3 claim spans | [codectx](results/prompts/J1-codectx.json) / [BM25](results/prompts/J1-bm25.json) |
| J2 | jdk21u | behavior | 3/3 claim spans | 1/3 claim spans | [codectx](results/prompts/J2-codectx.json) / [BM25](results/prompts/J2-bm25.json) |
| J3 | jdk21u | location | file present | file present | [codectx](results/prompts/J3-codectx.json) / [BM25](results/prompts/J3-bm25.json) |
| J4 | jdk21u | unanswerable | runtime evidence required | runtime evidence required | [codectx](results/prompts/J4-codectx.json) / [BM25](results/prompts/J4-bm25.json) |

## Evidence and checks

* [Frozen questions](cases.json), [source-checked references and rubric](cases.reviewed.json), [baseline freeze hashes](results/baseline-freeze.json).
* [Raw objective scores](results/context-scores.json), [summary JSON](results/summary.json), [test output](results/tests.txt).
* Source line references, actual contexts, hashes and commit IDs are retained for every condition. No source repository files were changed.
