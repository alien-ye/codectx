"""Render only measured results; missing runs remain explicitly missing."""

import json
import random
import re
import statistics
from pathlib import Path

BASE = Path(__file__).parent
OUT = BASE / "results"
REPOS = ["langchain", "django", "spring-boot", "kafka", "jdk21u"]


def pct(value):
    return "—" if value is None else f"{value * 100:.1f}%"


def interval(values):
    rng = random.Random(1729)
    means = sorted(statistics.mean(rng.choices(values, k=len(values))) for _ in range(2000))
    return f"[{means[50]:.3f}, {means[1949]:.3f}]"


def table(headers, rows):
    return (
        "\n".join(
            [
                "| " + " | ".join(headers) + " |",
                "| " + " | ".join(["---"] * len(headers)) + " |",
                *["| " + " | ".join(map(str, r)) + " |" for r in rows],
            ]
        )
        + "\n"
    )


def main():
    results = {
        repo: json.loads((OUT / f"{repo}-evaluation.json").read_text())
        for repo in REPOS
        if (OUT / f"{repo}-evaluation.json").exists()
    }
    import math

    for repo, result in results.items():
        for kind, modes in result["summary"].items():
            subset = [row for row in result["rows"] if row["kind"] == kind]
            for mode, summary in modes.items():
                values = sorted(row["systems"][mode]["warm_ms"] for row in subset)
                summary["warm_p95_ms"] = values[math.ceil(len(values) * 0.95) - 1]
        (OUT / f"{repo}-evaluation.json").write_text(json.dumps(result, indent=2) + "\n")
    text = [
        "# codectx: assessment on five public source repositories\n",
        "This is a new implementation rebuilt from the supplied design. The missing original source and its claimed 110-test suite were unavailable. See [methodology](README.md), [frozen natural-language labels](queries.json), and [implementation differences](../README.md).\n",
    ]
    if len(results) != 5:
        text.append(
            "**Incomplete evaluations:** "
            + ", ".join(repo for repo in REPOS if repo not in results)
            + ". Inspect the corresponding evaluation logs; do not interpret missing metrics as zero.\n"
        )
    text.append("## Corpus, indexing and storage\n")
    rows = []
    for repo in REPOS:
        initial = OUT / f"{repo}-index-initial.json"
        noop = OUT / f"{repo}-index-noop.json"
        if not initial.exists():
            continue
        record = json.loads(initial.read_text())
        stats = json.loads(record["stdout"]) if record["returncode"] == 0 else {}
        second = json.loads(noop.read_text()) if noop.exists() else {}
        errors = results.get(repo, {}).get("parse_error_files", {})
        rss = re.search(
            r"Maximum resident set size \(kbytes\): (\d+)",
            (OUT / f"{repo}-index-initial.stderr").read_text(),
        )
        size = results.get(repo, {}).get("index_bytes")
        rows.append(
            [
                repo,
                stats.get("code_files", "failed"),
                stats.get("symbols_total", "—"),
                len(errors) if repo in results else "—",
                f"{record['seconds']:.2f}",
                f"{second['seconds']:.2f}" if second else "—",
                f"{int(rss[1]) / 1024:.0f}" if rss else "—",
                f"{size / 2**20:.1f}" if size else "—",
            ]
        )
    text.append(
        table(
            [
                "Repository",
                "Code files",
                "Symbols",
                "Files with parse errors",
                "Initial s",
                "No-op s",
                "Index peak RSS MiB",
                "Index + vectors MiB",
            ],
            rows,
        )
    )
    text.append(
        "All discovered source trees include tests/examples. Only Python, Java and Groovy are analyzed; unsupported files are still discovered/hashed. Parse-error counts can include intentional invalid fixtures, source templates or grammar limitations; they are not counts of broken upstream code. Peak RSS here is the index subprocess, not the later evaluation workload. These runs use cached files on a shared WSL host and are not controlled cold-disk timings. Initial runs occurred during implementation: streaming serialization, compact postings, selective reference loading, memory-mapped embeddings, immutable string pooling and iterative traversal were added during this phase; the retained recursion-failure log precedes the successful OpenJDK retry. No-op timing includes loading and rewriting the plain-file store. Source checkouts are on the Linux filesystem; indexes and the virtual environment are on the Windows-shared filesystem under ~/share, which affects I/O and cold imports. No alternate-filesystem benchmark was run.\n"
    )
    text.append(
        "The first OpenJDK no-op evaluation was deliberately interrupted after about five minutes and 2,479,440 KiB peak RSS while it was swapping heavily. It was restarted after pooling repeated immutable strings during JSONL load; see [the interruption record](results/jdk21u-memory-pressure.json). LangChain/Django/Spring Boot/Kafka timings were collected before this final pooling change, and the final OpenJDK evaluation afterward. Treat cross-repository timing comparisons as exploratory measurements rather than a frozen-version performance contest. Retrieval algorithms and labels were unchanged by pooling.\n"
    )
    text.append("## Natural-language retrieval: ten questions per repository\n")
    rows = []
    for repo, r in results.items():
        s = r["summary"]["natural_language"]
        for mode in ["lexical", "semantic", "hybrid", "hybrid_no_boost", "file_bm25", "rg_or"]:
            m = s[mode]
            rows.append(
                [
                    repo,
                    mode,
                    pct(m["file"]["R@1"]),
                    pct(m["file"]["R@10"]),
                    f"{m['file']['MRR@10']:.3f}",
                    pct(m.get("symbol", {}).get("R@10")),
                ]
            )
    text.append(
        table(["Repository", "System", "File R@1", "File R@10", "File MRR@10", "Symbol R@10"], rows)
    )
    pooled = []
    for mode in ["lexical", "semantic", "hybrid", "hybrid_no_boost", "file_bm25", "rg_or"]:
        rows = [
            row["systems"][mode]
            for r in results.values()
            for row in r["rows"]
            if row["kind"] == "natural_language"
        ]
        if not rows:
            continue
        rrs = [1 / row["file_rank"] if 0 < row["file_rank"] <= 10 else 0 for row in rows]
        pooled.append(
            [
                mode,
                len(rows),
                pct(statistics.mean(0 < row["file_rank"] <= 10 for row in rows)),
                f"{statistics.mean(rrs):.3f}",
                interval(rrs),
            ]
        )
    text.append("### Pooled results\n")
    text.append(
        table(
            ["System", "Questions", "File R@10", "File MRR@10", "MRR bootstrap 95% interval"],
            pooled,
        )
    )
    text.append(
        "These are descriptive results for 50 prominent-API questions, with one intended class/file per query. They do not establish broad superiority or represent all coding tasks. Intervals resample these fixed labels, not the wider task population. `rg_or` is a simple filename-ordered text baseline. File BM25 reads method bodies, literals and docs; codectx reads symbol metadata.\n"
    )
    text.append("## Exact-identifier lookup diagnostic\n")
    rows = []
    for repo, r in results.items():
        for mode in ["lexical", "semantic", "hybrid", "hybrid_no_boost", "file_bm25"]:
            s = r["summary"]["identifier"][mode]
            rows.append(
                [
                    repo,
                    mode,
                    s["n"],
                    pct(s["file"]["R@10"]),
                    f"{s['file']['MRR@10']:.3f}",
                    pct(s.get("symbol", {}).get("R@10")),
                ]
            )
    text.append(
        table(["Repository", "System", "Queries", "File R@10", "File MRR@10", "Symbol R@10"], rows)
    )
    text.append(
        "Names are sampled from parse-healthy indexed symbols and must be globally unique. This measures known-symbol lookup, excludes ambiguities, and cannot detect missing symbols. It is not natural-language accuracy.\n"
    )
    text.append("## Extraction and graph diagnostics\n")
    rows = []
    for repo, r in results.items():
        c = r["extraction"]
        calls = c["python_calls"]
        inheritance = c["python_inheritance"]
        rows.append(
            [
                repo,
                c["sample_size"],
                pct(c["definition_recall"]),
                calls["gold"],
                pct(calls["precision"]),
                pct(calls["recall"]),
                inheritance["gold"],
                pct(inheritance["recall"]),
                r["noop_byte_stable"],
            ]
        )
    text.append(
        table(
            [
                "Repository",
                "Definition sample",
                "Definition recall",
                "Python call edges gold",
                "Call precision",
                "Call recall",
                "Python base edges gold",
                "Base recall",
                "No-op JSONL stable",
            ],
            rows,
        )
    )
    text.append(
        "The definition oracle is CPython AST for Python and comment-stripped regex **type declarations only** for Java. Java method/field recall and Java graph precision are not measured. Python graph values compare syntactic calls and simple base names, not receiver resolution or runtime dispatch. Inspect the raw missing/extra edge samples before treating differences as extractor defects; independent oracle scope attribution can differ for decorators and definition-time expressions.\n"
    )
    rows = []
    for repo, r in results.items():
        counts = r["call_resolution"]
        n = sum(counts.values())
        rows.append(
            [
                repo,
                n,
                pct(counts.get("exact", 0) / max(1, n)),
                pct(counts.get("name_match", 0) / max(1, n)),
                pct(counts.get("unresolved", 0) / max(1, n)),
            ]
        )
    text.append(
        table(
            [
                "Repository",
                "Call references",
                "Unique bare-name candidate",
                "Multiple candidates",
                "No candidate",
            ],
            rows,
        )
    )
    text.append(
        "A unique bare-name candidate is labeled `exact` to match the design vocabulary. It is **not** proof of a correct semantic target. Overloads, shared method names, inheritance, reflection and dynamic calls limit this graph.\n"
    )
    text.append("## Performance: warm queries versus new CLI processes\n")
    rows = []
    for repo, r in results.items():
        h = r["summary"]["natural_language"]["hybrid"]
        rows.append(
            [
                repo,
                f"{r['load_seconds']:.2f}",
                f"{r['embed_seconds']:.2f}",
                f"{h['warm_median_ms']:.1f}",
                f"{h['warm_p95_ms']:.1f}",
                f"{r['cold_cli']['lexical']['median_seconds']:.2f}",
                f"{r['cold_cli']['hybrid']['median_seconds']:.2f}",
                f"{r['max_rss_kib'] / 1024:.0f}",
            ]
        )
    text.append(
        table(
            [
                "Repository",
                "Search view load s",
                "Embed s",
                "Warm hybrid median ms",
                "Warm hybrid p95 ms",
                "New CLI lexical s",
                "New CLI hybrid s",
                "Evaluation peak RSS MiB",
            ],
            rows,
        )
    )
    text.append(
        "Warm queries reuse the search view, packed postings, memory-mapped vectors with cached norms, and model, retrieving 100 candidates; CLI samples use three fresh processes per mode with k=10, except indexes above 500,000 symbols use one observation per mode. The OpenJDK values are single observations, not robust latency estimates. Search views load inheritance references for boosting; full references are streamed for diagnostics. Cold CLI subprocesses share this limited-memory host with the evaluator, which retains the warm search data and file baseline; contention can affect cold wall times, especially for OpenJDK. Evaluation peak memory is the evaluator process only, includes validation and the full-source BM25 baseline, and cannot be attributed solely to codectx. Offline inference uses one BLAS thread and no network. See each JSON for setup costs and raw timings.\n"
    )
    text.append("## Context packs and correctness checks\n")
    for repo, r in results.items():
        c = r["context"]
        text.append(
            f"* [{repo} sample](results/{repo}-context.md): {c['symbol_count']} symbols, ~{c['token_estimate']} estimated tokens in a {c['budget']}-token character budget; truncated={c['truncated']}; {c['seconds']:.2f}s.\n"
        )
    text.append(
        "\nThe budget uses four characters per token, not a model tokenizer. Saved benchmark packs use graph depth 0 to isolate retrieved snippets. Graph expansion and provenance are checked in acceptance tests. The acceptance test output is [retained here](results/acceptance-tests.txt); the suite covers ignored paths, edit/deletion cleanup, file collisions, ambiguity, graph edges, context budgets, language extraction, corruption recovery, stale vectors, lazy imports, semantic model mismatch, fusion and deeply nested Java expressions.\n"
    )
    text.append(
        "Parser diagnostics are available in [parse-diagnostics.json](results/parse-diagnostics.json). Examples include Spring Boot annotated Java varargs and Groovy DSL constructs, Kafka archetype resource templates, and Unicode identifier forms in OpenJDK tests. These observations describe parser failures, not compiler validation of the source.\n"
    )
    text.append("## Assessment and next work\n")
    if pooled:
        best = max(pooled, key=lambda row: float(row[3]))
        text.append(
            f"On this fixed natural-language set, **{best[0]}** has the highest pooled file MRR@10 ({best[3]}). This result is specific to these labels and snapshots. Compare hybrid and hybrid_no_boost before retaining the subtype boost.\n"
        )
    if results:

        def pooled_mrr(kind, mode):
            ranks = [
                row["systems"][mode]["file_rank"]
                for result in results.values()
                for row in result["rows"]
                if row["kind"] == kind
            ]
            return statistics.mean(1 / rank if 0 < rank <= 10 else 0 for rank in ranks)

        text.append(
            f"For exact-name lookup, pooled file MRR@10 is {pooled_mrr('identifier', 'lexical'):.3f} with lexical search, {pooled_mrr('identifier', 'hybrid'):.3f} with boosted hybrid, and {pooled_mrr('identifier', 'hybrid_no_boost'):.3f} without the boost. For natural-language questions, boosted/unboosted hybrid MRR@10 is {pooled_mrr('natural_language', 'hybrid'):.3f}/{pooled_mrr('natural_language', 'hybrid_no_boost'):.3f}. Route explicit names and open-ended questions according to these separate measurements; the subtype boost is not a universally helpful ranking rule.\n"
        )
        large = [
            f"{name}: {result['stats']['symbols_total']:,}"
            for name, result in results.items()
            if result["stats"]["symbols_total"] > 100000
        ]
        if large:
            text.append(
                "Indexes above the design's approximate 100,000-symbol assumption: "
                + "; ".join(large)
                + ". Their successful runs demonstrate feasibility on these snapshots, not an unlimited scale guarantee.\n"
            )
    text.append(
        "The implementation is useful as a local, inspectable source-location retriever. Its main structural limits are metadata-only lexical documents, heuristic name resolution, plain-file load/rewrite costs, and whole-index memory use. Kafka and OpenJDK should be checked against the design’s approximate 100,000-symbol scale assumption. Priorities are source-body retrieval/reranking experiments, type-aware graph resolution and overload identities, read-only cached index services, compact storage, stronger Java method/call oracles, and a larger externally authored task set. None of those are claimed implemented by this benchmark.\n"
    )
    text.append("## Reproducibility and evidence\n")
    for repo, r in results.items():
        text.append(
            f"* **{repo}** `{r['commit']}`: [raw evaluation](results/{repo}-evaluation.json), [execution log](results/{repo}-evaluation.log), [initial index](results/{repo}-index-initial.json), [no-op index](results/{repo}-index-noop.json).\n"
        )
    text.append(
        "\nEnvironment and locked dependency versions are in [environment.json](results/environment.json) and [uv.lock](../uv.lock). Run instructions are in [the protocol](README.md). No source repository test suites were run; this assesses codectx against their source snapshots.\n"
    )
    (BASE / "REPORT.md").write_text("\n".join(text))
    print(BASE / "REPORT.md")


if __name__ == "__main__":
    main()
