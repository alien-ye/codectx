"""File-level metrics from saved ranks; one binary relevant file per query."""

import json
import math
from pathlib import Path

BASE = Path(__file__).parent
REPOS = ["django", "langchain", "spring-boot", "kafka", "jdk21u"]
MODES = ["lexical", "semantic", "hybrid", "hybrid_no_boost", "file_bm25"]


def single_target_metrics(ranks):
    if not ranks or any(type(r) is not int or r < 0 for r in ranks):
        raise ValueError("Expected nonempty nonnegative integer ranks; zero denotes a miss")
    n = len(ranks)
    return {
        **{f"Recall@{k}": sum(0 < r <= k for r in ranks) / n for k in [1, 5, 10]},
        "MRR@10": sum(1 / r if 0 < r <= 10 else 0 for r in ranks) / n,
        "nDCG@10": sum(1 / math.log2(r + 1) if 0 < r <= 10 else 0 for r in ranks) / n,
    }


def main():
    results = [
        json.loads((BASE / "results" / f"{repo}-evaluation.json").read_text()) for repo in REPOS
    ]
    output = dict(
        unit="file",
        relevance="one binary relevant file per query",
        cutoff=10,
        miss_rank=0,
        workloads={},
    )
    report = [
        "# Retrieval ranking metrics\n",
        "Calculated from the saved per-query ranks. No model or retrieval rerun was performed.\n",
        "All metrics below are **file level**, with one intended relevant file per question. Recall@K therefore equals a single-target hit rate. MRR is truncated at ten. nDCG uses binary relevance: a target at rank r <= 10 contributes 1/log2(r+1), otherwise zero; ideal DCG is one. These are not graded multi-document nDCG scores or answer-quality scores.\n",
    ]
    for kind in ["natural_language", "identifier"]:
        report.append(
            "## "
            + (
                "Natural-language questions (50)"
                if kind == "natural_language"
                else "Unique-identifier lookups (500)"
            )
            + "\n"
        )
        report.extend(
            [
                "| System | Recall@1 | Recall@5 | Recall@10 | MRR@10 | nDCG@10 |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        output["workloads"][kind] = {}
        for mode in MODES:
            ranks = [
                row["systems"][mode]["file_rank"]
                for result in results
                for row in result["rows"]
                if row["kind"] == kind
            ]
            m = single_target_metrics(ranks)
            output["workloads"][kind][mode] = dict(n=len(ranks), **m)
            report.append(
                f"| {mode} | {m['Recall@1']:.1%} | {m['Recall@5']:.1%} | {m['Recall@10']:.1%} | {m['MRR@10']:.3f} | {m['nDCG@10']:.3f} |"
            )
        report.append("")
    report.append("## Interpretation\n")
    report.append(
        "On the 50 fixed natural-language questions, hybrid improves rank-weighted metrics slightly over file BM25 but has lower recall at ten (70% vs 72%). This small curated set does not establish statistical superiority. Unique-identifier queries favor lexical search; they were sampled from healthy indexed symbols with globally unique names and do not measure missing-symbol coverage.\n"
    )
    report.append(
        "The [RAG pilot](rag_pilot/REPORT.md) measures packed reference evidence separately. Its 8/10 behavior-evidence result is not Recall@K of the ranked search list. For a richer code RAG benchmark, label all required supporting passages/functions, allow multiple relevant items, and assign relevance grades before interpreting graded nDCG.\n"
    )
    report.append(
        "Symbol-level natural-language Recall@10 in the original data is 32% for hybrid, compared with 70% at file level. The intended class can rank poorly even when another method in its file is retrieved. Do not substitute file scores for symbol or passage recall.\n"
    )
    (BASE / "results/ranking-metrics.json").write_text(json.dumps(output, indent=2) + "\n")
    (BASE / "RANKING_METRICS.md").write_text("\n".join(report))
    print(BASE / "RANKING_METRICS.md")


if __name__ == "__main__":
    main()
