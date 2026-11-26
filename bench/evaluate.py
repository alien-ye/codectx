"""Reproducible retrieval evaluation; each repo runs in a fresh process."""

import argparse
import ast
import hashlib
import json
import math
import os
import platform
import random
import re
import resource
import statistics
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

from codectx.bm25 import BM25Index
from codectx.hybrid import HybridSearcher
from codectx.search import LexicalSearcher
from codectx.semantic import SemanticSearcher, embed_symbols
from codectx.store import Store
from codectx.tokens import query_tokens, split_identifier, tokenize

BASE = Path(__file__).parent
OUT = BASE / "results"


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ref_records(store):
    with (store.index_dir / "refs.jsonl").open("rb") as stream:
        for line in stream:
            yield json.loads(line)


def clock(fn):
    t = time.perf_counter()
    value = fn()
    return value, time.perf_counter() - t


def collapse(hits, store):
    seen = []
    for h in hits:
        path = store.symbol_by_id(h.symbol_id).file_path
        if path not in seen:
            seen.append(path)
    return seen


def metrics(ranks):
    return {
        **{f"R@{k}": sum(0 < r <= k for r in ranks) / max(1, len(ranks)) for k in [1, 5, 10]},
        "MRR@10": sum(1 / r if 0 < r <= 10 else 0 for r in ranks) / max(1, len(ranks)),
    }


def rank(values, gold):
    return next((i for i, value in enumerate(values, 1) if value == gold), 0)


def coverage(store, root):
    """Independent CPython AST for definitions/calls, regex class oracle for Java."""
    symbol_gold = []
    calls_gold = []
    inheritance_gold = []
    parse_fail = []
    for file in store.get_files().values():
        if file.lang not in {"python", "java"}:
            continue
        source = (root / file.path).read_text(errors="replace")
        if file.lang == "python":
            try:
                tree = ast.parse(source)
            except SyntaxError:
                parse_fail.append(file.path)
                continue

            def walk(node, scope, file=file):
                decorators = []
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    decorators = node.decorator_list
                    for decorator in decorators:
                        walk(decorator, scope)
                    symbol_gold.append((file.path, node.name, node.lineno))
                    scope = scope + [node.name]
                    if isinstance(node, ast.ClassDef):
                        for base in node.bases:
                            while isinstance(base, ast.Subscript):
                                base = base.value
                            if isinstance(base, ast.Name):
                                inheritance_gold.append(
                                    (file.path, ".".join(scope), base.id, node.lineno)
                                )
                            elif isinstance(base, ast.Attribute):
                                inheritance_gold.append(
                                    (file.path, ".".join(scope), base.attr, node.lineno)
                                )
                if isinstance(node, ast.Call):
                    func = node.func
                    name = (
                        func.id
                        if isinstance(func, ast.Name)
                        else func.attr
                        if isinstance(func, ast.Attribute)
                        else None
                    )
                    if name:
                        calls_gold.append(
                            (file.path, ".".join(scope) or "<module>", name, node.lineno)
                        )
                for child in ast.iter_child_nodes(node):
                    if child not in decorators:
                        walk(child, scope)

            walk(tree, [])
        else:
            # Preserve newlines while removing comments and literals. This oracle is
            # intentionally limited to named type declarations, not Java methods.
            def blank(m):
                return "".join("\n" if c == "\n" else " " for c in m[0])

            clean = re.sub(
                r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'',
                blank,
                source,
                flags=re.S,
            )
            for m in re.finditer(r"\b(?:class|interface|enum|record)\s+(\w+)", clean):
                symbol_gold.append((file.path, m[1], clean[: m.start()].count("\n") + 1))
    present = {(s.file_path, s.name, s.start_line) for s in store.all_symbols() if s.parse_ok}
    # Java declaration starts at annotations/modifiers, so check name and file.
    present_java = {
        (s.file_path, s.name) for s in store.all_symbols() if s.parse_ok and s.kind == "class"
    }
    rng = random.Random(1729)
    sampled = rng.sample(symbol_gold, min(500, len(symbol_gold)))
    gaps = [
        g
        for g in sampled
        if ((g[0], g[1]) not in present_java if g[0].endswith(".java") else g not in present)
    ]
    actual_calls, actual_inheritance = set(), set()
    for r in ref_records(store):
        if not r["file_path"].endswith(".py"):
            continue
        edge = (r["file_path"], r["source_qualifier"], r["target_name"], r["line"])
        if r["kind"] == "calls":
            actual_calls.add(edge)
        elif r["kind"] == "extends":
            actual_inheritance.add(edge)

    def compare(gold, actual):
        gold = set(gold)
        # Compare only independently parseable Python files.
        paths = {f.path for f in store.get_files().values() if f.lang == "python"} - set(parse_fail)
        actual = {v for v in actual if v[0] in paths}
        tp = len(gold & actual)
        return dict(
            gold=len(gold),
            extracted=len(actual),
            precision=tp / len(actual) if actual else None,
            recall=tp / len(gold) if gold else None,
            missing_sample=list(sorted(gold - actual))[:20],
            extra_sample=list(sorted(actual - gold))[:20],
        )

    return dict(
        oracle="CPython AST definitions and Python call/base edges; comment-stripped regex Java types only",
        sample_size=len(sampled),
        definition_recall=1 - len(gaps) / max(1, len(sampled)),
        definition_gaps=gaps,
        python_ast_parse_failures=parse_fail,
        python_calls=compare(calls_gold, actual_calls),
        python_inheritance=compare(inheritance_gold, actual_inheritance),
    )


def evaluate(repo):
    root = Path("/home/alien/repo") / repo
    db = OUT / "indexes" / repo
    commit = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    names = ["files.jsonl", "symbols.jsonl", "refs.jsonl"]
    print(repo, "no-op stability check started", flush=True)
    before = {name: file_hash(db / name) for name in names}
    started = time.perf_counter()
    with (OUT / f"{repo}-index-noop.stderr").open("w") as error:
        proc = subprocess.run(
            [
                "/usr/bin/time",
                "-v",
                sys.executable,
                "-m",
                "codectx",
                "index",
                str(root),
                "--db",
                str(db),
                "--stats",
            ],
            capture_output=False,
            stdout=subprocess.PIPE,
            stderr=error,
            text=True,
        )
    noop_time = time.perf_counter() - started
    assert proc.returncode == 0, f"No-op indexing failed for {repo}"
    noop = json.loads(proc.stdout)
    (OUT / f"{repo}-index-noop.json").write_text(
        json.dumps(
            dict(
                repo=repo,
                run="noop",
                seconds=noop_time,
                returncode=proc.returncode,
                stdout=proc.stdout,
            ),
            indent=2,
        )
    )
    stable = all(file_hash(db / name) == value for name, value in before.items())
    store, load_seconds = clock(lambda: Store(db, root, ref_kinds={"extends", "implements", "anonymous_base"}))
    stats = store.stats()
    print(repo, "loaded", stats, flush=True)
    extraction = coverage(store, root)
    print(repo, "coverage complete", flush=True)
    embed_n, embed_seconds = clock(
        lambda: embed_symbols(store, [s for s in store.all_symbols() if s.parse_ok])
    )
    store.commit()
    print(repo, "embedded", embed_n, "in", embed_seconds, flush=True)
    lex, lex_build = clock(lambda: LexicalSearcher(store))
    sem, sem_build = clock(lambda: SemanticSearcher(store))
    hybrid = HybridSearcher(store, lex, sem)
    # Full-source file BM25 reads the same supported-language file universe.
    paths = sorted(f.path for f in store.get_files().values() if f.lang != "unknown")

    def build_files():
        return BM25Index.build(
            [
                part
                for tok in tokenize((root / p).read_text(errors="replace"))
                for part in split_identifier(tok)
            ]
            for p in paths
        )

    print(repo, "building full-source BM25 baseline", flush=True)
    file_index, file_build = clock(build_files)
    print(repo, "file BM25 ready", file_build, "seconds", flush=True)
    curated = [q for q in json.loads((BASE / "queries.json").read_text()) if q["repo"] == repo]
    symbols = store.all_symbols()
    counts = Counter(s.name for s in symbols)
    unique = [
        s
        for s in symbols
        if s.parse_ok
        and s.kind in {"class", "function", "method"}
        and counts[s.name] == 1
        and not s.name.startswith("_")
    ]
    picked = random.Random(1729).sample(unique, min(100, len(unique)))
    identifiers = [
        dict(
            repo=repo,
            query=s.name,
            name=s.name,
            file=s.file_path,
            line=s.start_line,
            kind="identifier",
        )
        for s in picked
    ]
    rows = []

    def rg_files(query):
        terms = list(dict.fromkeys(query_tokens(query)))
        if not terms:
            return []
        cmd = [
            "rg",
            "-i",
            "-l",
            "--glob",
            "*.py",
            "--glob",
            "*.java",
            "--glob",
            "*.groovy",
            "--",
            "|".join(re.escape(t) for t in terms),
            ".",
        ]
        result = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=60)
        if result.returncode not in [0, 1]:
            raise RuntimeError(result.stderr)
        return sorted(line.removeprefix("./") for line in result.stdout.splitlines())

    for q in curated + identifiers:
        row = {**q, "systems": {}}
        golds = {s.id for s in symbols if s.file_path == q["file"] and s.name == q["name"]}
        assert golds, (repo, q)
        functions = {
            "lexical": lambda q=q: lex.search(q["query"], 100),
            "semantic": lambda q=q: sem.search(q["query"], 100),
            "hybrid": lambda q=q: hybrid.search(q["query"], 100),
            "hybrid_no_boost": lambda q=q: hybrid.search(q["query"], 100, boost=False),
        }
        for mode, fn in functions.items():
            hits, elapsed = clock(fn)
            row["systems"][mode] = dict(
                symbol_rank=next((i for i, h in enumerate(hits, 1) if h.symbol_id in golds), 0),
                file_rank=rank(collapse(hits, store), q["file"]),
                warm_ms=elapsed * 1000,
                top_files=collapse(hits, store)[:10],
            )
        files, elapsed = clock(lambda q=q: file_index.search(query_tokens(q["query"]), 100))
        ranked_files = [paths[i] for i, _ in files]
        row["systems"]["file_bm25"] = dict(
            file_rank=rank(ranked_files, q["file"]),
            warm_ms=elapsed * 1000,
            top_files=ranked_files[:10],
        )
        if q["kind"] == "natural_language":
            files, elapsed = clock(lambda q=q: rg_files(q["query"]))
            row["systems"]["rg_or"] = dict(
                file_rank=rank(files, q["file"]), warm_ms=elapsed * 1000, top_files=files[:10]
            )
        rows.append(row)
        if len(rows) % 25 == 0:
            print(repo, "queries evaluated", len(rows), flush=True)
    print(repo, "queries complete", flush=True)
    summaries = {}
    for kind in ["natural_language", "identifier"]:
        subset = [r for r in rows if r["kind"] == kind]
        summaries[kind] = {}
        for mode in subset[0]["systems"]:
            results = [r["systems"][mode] for r in subset]
            summaries[kind][mode] = dict(
                n=len(results),
                file=metrics([r["file_rank"] for r in results]),
                warm_median_ms=statistics.median(r["warm_ms"] for r in results),
                warm_p95_ms=sorted(r["warm_ms"] for r in results)[
                    max(0, math.ceil(len(results) * 0.95) - 1)
                ],
            )
            if "symbol_rank" in results[0]:
                summaries[kind][mode]["symbol"] = metrics([r["symbol_rank"] for r in results])
    # Cold CLI latency includes process start, JSONL loading, BM25 construction,
    # vector normalization/model loading. Three independent invocations per mode.
    print(repo, "cold CLI timing started", flush=True)
    cold = {}
    for mode in ["lexical", "hybrid"]:
        timings = []
        for q in curated[: 1 if len(symbols) > 500000 else 3]:
            result, elapsed = clock(
                lambda q=q, mode=mode: subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "codectx",
                        "search",
                        q["query"],
                        str(root),
                        "--db",
                        str(db),
                        "--mode",
                        mode,
                        "-k",
                        "10",
                    ],
                    capture_output=True,
                    text=True,
                    env={**os.environ, "HF_HUB_OFFLINE": "1"},
                )
            )
            assert result.returncode == 0, result.stderr
            timings.append(elapsed)
        print(repo, "cold", mode, "samples", timings, flush=True)
        cold[mode] = dict(samples_seconds=timings, median_seconds=statistics.median(timings))
    from codectx.context import build_context

    pack, context_seconds = clock(
        lambda: build_context(
            store, curated[0]["query"], root=root, token_budget=4000, k=5, graph_depth=0
        )
    )
    (OUT / f"{repo}-context.md").write_text(pack.text)
    ref_kinds = Counter(r["resolution_kind"] for r in ref_records(store) if r["kind"] == "calls")
    index_bytes = sum(p.stat().st_size for p in db.rglob("*") if p.is_file())
    result = dict(
        repo=repo,
        commit=commit,
        stats=stats,
        parse_error_files={k[6:]: v for k, v in store._manifest.items() if k.startswith("error:")},
        extraction=extraction,
        call_resolution=dict(ref_kinds),
        load_seconds=load_seconds,
        embed_seconds=embed_seconds,
        embedded_symbols=embed_n,
        lexical_build_seconds=lex_build,
        semantic_build_seconds=sem_build,
        file_bm25_build_seconds=file_build,
        index_bytes=index_bytes,
        noop_byte_stable=stable,
        noop_stats=noop,
        summary=summaries,
        cold_cli=cold,
        context=dict(
            graph_depth=0,
            seconds=context_seconds,
            symbol_count=pack.symbol_count,
            token_estimate=pack.token_estimate,
            truncated=pack.truncated,
            budget=4000,
            sources=pack.sources,
        ),
        rows=rows,
        max_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        environment=dict(
            python=sys.version,
            platform=platform.platform(),
            threads=os.environ.get("OPENBLAS_NUM_THREADS"),
            offline=os.environ.get("HF_HUB_OFFLINE"),
        ),
    )
    (OUT / f"{repo}-evaluation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(repo, "DONE", json.dumps(summaries["natural_language"]), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", choices=["langchain", "django", "spring-boot", "kafka", "jdk21u"])
    evaluate(parser.parse_args().repo)
