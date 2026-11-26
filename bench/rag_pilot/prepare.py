"""Prepare actual contexts without generation or answer-label leakage into queries."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

from codectx import context
from codectx.bm25 import BM25Index
from codectx.hybrid import HybridSearcher
from codectx.store import Store
from codectx.tokens import query_tokens, split_identifier, tokenize

BASE = Path(__file__).parent
REPOS = ["django", "langchain", "spring-boot", "kafka", "jdk21u"]


def merge_ranges(spans):
    result = []
    for file in sorted({s["file"] for s in spans}):
        for s in sorted((s for s in spans if s["file"] == file), key=lambda s: s["start"]):
            if result and result[-1]["file"] == file and s["start"] <= result[-1]["end"] + 1:
                result[-1]["end"] = max(result[-1]["end"], s["end"])
            else:
                result.append(dict(file=file, start=s["start"], end=s["end"]))
    return result


def render(root, spans, budget):
    text = ""
    used = []
    for span in spans:
        lines = (root / span["file"]).read_text(errors="replace").splitlines()
        block = (
            f"## {span['file']}:{span['start']}-{span['end']}\n```\n"
            + "\n".join(f"{i}: {lines[i - 1]}" for i in range(span["start"], span["end"] + 1))
            + "\n```\n\n"
        )
        if len(text) + len(block) <= budget:
            text += block
            used.append(span)
    return text, used


def metadata_doc_span(root, s):
    if not s.docstring or not s.file_path.endswith(".java"):
        return []
    source = (root / s.file_path).read_text(errors="replace")
    offset = sum(len(line) for line in source.splitlines(keepends=True)[: s.start_line - 1])
    start = source.rfind("/**", 0, offset)
    end = source.find("*/", start) if start >= 0 else -1
    if start >= 0 and end >= start and not source[end + 2 : offset].strip():
        return [
            dict(
                file=s.file_path,
                start=source[:start].count("\n") + 1,
                end=source[: end + 2].count("\n") + 1,
                via="metadata_javadoc",
            )
        ]
    return []


def packed_spans(store, root, text):
    result = []
    pattern = r"^## (.*?)  \(([^)]+)\)  (.*):(\d+)$"
    for m in re.finditer(pattern, text, re.M):
        name, kind, file, line = m.groups()
        line = int(line)
        matches = [
            s
            for s in store.by_file_qname.get((file, name), [])
            if s.start_line == line and s.kind == kind
        ]
        if not matches:
            continue
        s = matches[0]
        result.append(
            dict(
                file=file,
                start=s.start_line,
                end=min(s.end_line, s.start_line + 59),
                via="source_snippet",
            )
        )
        result.extend(metadata_doc_span(root, s))
    return result


def bm25_context(root, paths, index, question, budget):
    terms = query_tokens(question)
    files = [paths[i] for i, _ in index.search(terms, 10)]
    windows = []
    docs = []
    for file in files:
        lines = (root / file).read_text(errors="replace").splitlines()
        for start in range(0, len(lines), 20):
            end = min(start + 30, len(lines))
            windows.append(dict(file=file, start=start + 1, end=end))
            docs.append(
                [
                    part
                    for token in tokenize("\n".join(lines[start:end]))
                    for part in split_identifier(token)
                ]
            )
    hits = BM25Index.build(docs).search(terms, 30)
    selected = []
    counts = {}
    for i, _ in hits:
        span = windows[i]
        file = span["file"]
        if counts.get(file, 0) >= 3:
            continue
        if any(
            s["file"] == file and max(s["start"], span["start"]) <= min(s["end"], span["end"])
            for s in selected
        ):
            continue
        selected.append(span)
        counts[file] = counts.get(file, 0) + 1
    text, used = render(root, selected, budget)
    return text, used, files


def prepare(repo, budget):
    root = Path(os.environ.get("CODECTX_BENCH_REPOS", Path.home() / "repo")) / repo
    cases = [r for r in json.loads((BASE / "cases.reviewed.json").read_text()) if r["repo"] == repo]
    actual = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    assert all(r["commit"] == actual for r in cases), "Source snapshot changed"
    started = time.perf_counter()
    store = Store(
        BASE.parent / "results/indexes" / repo,
        root,
        readonly=True,
        ref_kinds={"extends", "implements"},
    )
    searcher = HybridSearcher(store)
    print(repo, "codectx ready", round(time.perf_counter() - started, 2), flush=True)
    paths = sorted(f.path for f in store.get_files().values() if f.lang != "unknown")
    index = BM25Index.build(
        [
            part
            for token in tokenize((root / file).read_text(errors="replace"))
            for part in split_identifier(token)
        ]
        for file in paths
    )
    print(repo, "file BM25 ready", round(time.perf_counter() - started, 2), flush=True)
    records = []
    dataset_hash = hashlib.sha256((BASE / "cases.reviewed.json").read_bytes()).hexdigest()
    for case in cases:
        for mode in ["none", "codectx", "bm25", "gold"]:
            start = time.perf_counter()
            files = []
            if mode == "none":
                text = ""
                spans = []
            elif mode == "codectx":
                # Reuse exactly the same hybrid scorer, replacing only its repeated construction.
                with patch.object(
                    context, "search_hybrid", lambda _store, q, k: searcher.search(q, k)
                ):
                    pack = context.build_context(
                        store,
                        case["question"],
                        root=root,
                        token_budget=budget // 4,
                        graph_depth=0,
                        k=10,
                    )
                text = pack.text
                spans = packed_spans(store, root, text)
            elif mode == "bm25":
                text, spans, files = bm25_context(root, paths, index, case["question"], budget)
            else:
                wanted = []
                for claim in case["essential_claims"]:
                    alternatives = (
                        claim["evidence"][:1]
                        if claim.get("evidence_mode") == "any"
                        else claim["evidence"]
                    )
                    for s in alternatives:
                        length = len((root / s["file"]).read_text().splitlines())
                        wanted.append(
                            dict(
                                file=s["file"],
                                start=max(1, s["start"] - 3),
                                end=min(length, s["end"] + 3),
                            )
                        )
                text, spans = render(root, merge_ranges(wanted), budget)
            assert len(text) <= budget
            record = dict(
                case_id=case["id"],
                repo=repo,
                mode=mode,
                question=case["question"],
                context=text,
                provided_spans=spans,
                ranked_files=files,
                context_characters=len(text),
                context_sha256=hashlib.sha256(text.encode()).hexdigest(),
                dataset_sha256=dataset_hash,
                commit=actual,
                preparation_seconds=time.perf_counter() - start,
                graph_depth=0,
                character_budget=budget,
            )
            records.append(record)
        print(repo, case["id"], "prepared", flush=True)
    out = BASE / "results/contexts"
    out.mkdir(exist_ok=True)
    (out / f"{repo}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
    print(repo, "DONE", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", choices=REPOS)
    parser.add_argument("--characters", type=int, default=6000)
    args = parser.parse_args()
    if args.characters < 100 or args.characters % 4:
        parser.error("characters must be >=100 and divisible by 4")
    if args.repo:
        prepare(args.repo, args.characters)
    else:
        for repo in REPOS:
            with (BASE / "results" / f"{repo}-prepare.log").open("w") as log:
                result = subprocess.run(
                    [
                        sys.executable,
                        __file__,
                        "--repo",
                        repo,
                        "--characters",
                        str(args.characters),
                    ],
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    env={
                        **os.environ,
                        "HF_HUB_OFFLINE": "1",
                        "OPENBLAS_NUM_THREADS": "1",
                        "OMP_NUM_THREADS": "1",
                        "TOKENIZERS_PARALLELISM": "false",
                    },
                )
            print(repo, result.returncode, flush=True)
            if result.returncode:
                print((BASE / "results" / f"{repo}-prepare.log").read_text()[-4000:], flush=True)
                raise SystemExit(result.returncode)
