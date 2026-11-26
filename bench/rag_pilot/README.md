# Code RAG pilot and model-evaluation harness

This adds a source-grounded RAG audit to the earlier retrieval benchmark. The retrieval component is still the local **model2vec `minishlab/potion-code-16M-v2` embedding model**. It is not an answer generator.

## What is measured

* Twenty frozen questions: two behavior questions, one location question, and one deployment/runtime question per repository. Deployment cases deliberately require facts not supplied by a public source snapshot.
* Source-checked references and thirty essential claims, checked by the interactive assistant, not an independent human annotator. Questions and no-context answers were frozen before collecting new source evidence. Public-repository knowledge from training or the preceding conversation is not ruled out.
* Four real context conditions: none; codectx hybrid with its existing packer; file BM25 followed by BM25-ranked source windows; and reference source windows (gold). The same question is used in each condition. Expected answers and rubrics never enter generation prompts.
* Each context has the same **6,000-character** limit, not a guaranteed tokenizer budget. Codectx uses k=10 and graph depth 0, so this pilot evaluates retrieval/packing, not the benefit of graph expansion. BM25 uses the same supported-language file universe, top ten files, 30-line windows at stride twenty, then up to three nonoverlapping windows per file.
* Objective measurements are source-file availability and coverage of the frozen reference line spans. They are conservative reference coverage metrics: different but equally valid tests/docs may also support an answer. They are not generated-answer accuracy or semantic citation precision.
* Interactive answers and qualitative observations are exploratory: the same assistant collects references, answers, and reviews results, and conditions are not separate fresh model sessions. No independent or causal answer-quality score is claimed from that walkthrough.

A full model comparison uses `run_model.py`: every request is an independent stateless chat with identical system instructions. Compare the same model across context conditions, or repeat the matrix for multiple models. The optional model judge is explicitly configured; it is fallible and its grades should be human-audited. Grading with the same model as the generator is flagged. A human review worksheet is also exported.

## Reproduce context preparation

The five source checkouts and indexes from the first benchmark must be present (override the checkout parent via `CODECTX_BENCH_REPOS`, default `~/repo`). Commands run from the repository root:

```bash
.venv/bin/python bench/rag_pilot/make_cases.py
.venv/bin/python bench/rag_pilot/collect_references.py
.venv/bin/python bench/rag_pilot/review_references.py
OPENBLAS_NUM_THREADS=1 HF_HUB_OFFLINE=1 .venv/bin/python bench/rag_pilot/prepare.py
.venv/bin/python bench/rag_pilot/score_contexts.py
.venv/bin/python bench/rag_pilot/report.py
```

References are pinned to the actual Git commits. Case questions are frozen in `cases.json`. Reference review is encoded separately in `cases.reviewed.json`; this is not a randomly sampled or independently authored production benchmark. `results/baseline-freeze.json` records the original question and no-context-answer hashes.

## Evaluate a local generation model

These adapters implement [Ollama native chat](https://docs.ollama.com/api/chat) and [LM Studio's OpenAI-compatible chat](https://lmstudio.ai/docs/developer/openai-compat/chat-completions), also usable with compatible llama.cpp/vLLM servers. They do not require the OpenAI SDK or a cloud account. Native servers are not bundled or automatically downloaded. Local API requests bypass environment HTTP proxies.

Ollama example (replace the placeholder with a model already available on your server):

```bash
.venv/bin/python bench/rag_pilot/run_model.py \
  --protocol ollama --base-url http://127.0.0.1:11434 \
  --model YOUR_MODEL --limit 5 \
  --output bench/rag_pilot/results/local-model-answers.jsonl
```

LM Studio / OpenAI-compatible example:

```bash
.venv/bin/python bench/rag_pilot/run_model.py \
  --base-url http://127.0.0.1:1234/v1 --model YOUR_MODEL \
  --output bench/rag_pilot/results/local-model-answers.jsonl
```

Repeat `--model` to evaluate several models. Omit `--limit` for all twenty cases and all four conditions (80 requests per model). Use `--case-id S1 --case-id S2` for the two Spring Boot probes. Request settings are temperature 0, seed 1729, and maximum 512 output tokens; server support and deterministic sampling are model-specific. Configure sufficient server context length, and inspect returned prompt/completion token counts and finish reasons for truncation. A character budget alone cannot guarantee that a model accepts every token.

Runs append and flush each response. Successful requests are skipped only when their complete configuration, model, question/reference version and context hashes match; failures can be retried by rerunning the command. Missing token usage stays missing; no token costs, energy costs, latency or model-specific settings are invented. No local generator has been benchmarked merely by adding these adapters: unit tests use mocked transport responses.

## Score generated answers

First inspect `results/answer-review.csv` and the source-backed reference answers. Assess correctness, faithfulness, citation support, and abstention separately. A valid file/line citation can still fail to support the answer's claim.

An optional model judge can assist:

```bash
.venv/bin/python bench/rag_pilot/judge_model.py \
  --answers bench/rag_pilot/results/local-model-answers.jsonl \
  --base-url http://127.0.0.1:1234/v1 --model YOUR_JUDGE_MODEL \
  --output bench/rag_pilot/results/model-judgments.jsonl
```

The judge receives reference claims and actual supplied context separately. It grades every required claim once and cannot use gold-only source as retrieved evidence. Its requested explanation is brief. Use fresh held-out questions and independent review before making model-quality claims or changing retrieval parameters based on this pilot.

For model-version reproducibility, pass `--model-revision GGUF_SHA256_OR_MODEL_DIGEST` (one per `--model`). It becomes part of the checkpoint identity. Without it, the model revision is recorded as unrecorded; an alias alone does not pin weights. Judge/generator equality is an identifier comparison, not proof that differently named models have independent weights.
