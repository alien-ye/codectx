# Retrieval ranking metrics

Calculated from the saved per-query ranks. No model or retrieval rerun was performed.

All metrics below are **file level**, with one intended relevant file per question. Recall@K therefore equals a single-target hit rate. MRR is truncated at ten. nDCG uses binary relevance: a target at rank r <= 10 contributes 1/log2(r+1), otherwise zero; ideal DCG is one. These are not graded multi-document nDCG scores or answer-quality scores.

## Natural-language questions (50)

| System | Recall@1 | Recall@5 | Recall@10 | MRR@10 | nDCG@10 |
| --- | --- | --- | --- | --- | --- |
| lexical | 16.0% | 40.0% | 52.0% | 0.258 | 0.319 |
| semantic | 18.0% | 50.0% | 60.0% | 0.303 | 0.374 |
| hybrid | 18.0% | 54.0% | 70.0% | 0.332 | 0.419 |
| hybrid_no_boost | 18.0% | 42.0% | 58.0% | 0.285 | 0.355 |
| file_bm25 | 14.0% | 54.0% | 72.0% | 0.315 | 0.411 |

## Unique-identifier lookups (500)

| System | Recall@1 | Recall@5 | Recall@10 | MRR@10 | nDCG@10 |
| --- | --- | --- | --- | --- | --- |
| lexical | 98.8% | 99.8% | 100.0% | 0.993 | 0.995 |
| semantic | 92.8% | 97.6% | 98.6% | 0.948 | 0.958 |
| hybrid | 64.6% | 93.2% | 96.6% | 0.767 | 0.816 |
| hybrid_no_boost | 96.0% | 99.4% | 99.6% | 0.975 | 0.980 |
| file_bm25 | 74.8% | 91.8% | 94.8% | 0.821 | 0.852 |

## Interpretation

On the 50 fixed natural-language questions, hybrid improves rank-weighted metrics slightly over file BM25 but has lower recall at ten (70% vs 72%). This small curated set does not establish statistical superiority. Unique-identifier queries favor lexical search; they were sampled from healthy indexed symbols with globally unique names and do not measure missing-symbol coverage.

The [RAG pilot](codectx/bench/rag_pilot/REPORT.md) measures packed reference evidence separately. Its 8/10 behavior-evidence result is not Recall@K of the ranked search list. For a richer code RAG benchmark, label all required supporting passages/functions, allow multiple relevant items, and assign relevance grades before interpreting graded nDCG.

Symbol-level natural-language Recall@10 in the original data is 32% for hybrid, compared with 70% at file level. The intended class can rank poorly even when another method in its file is retrieved. Do not substitute file scores for symbol or passage recall.
