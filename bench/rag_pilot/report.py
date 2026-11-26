"""Render measured context coverage and a transparent interactive walkthrough."""

import csv
import hashlib
import json
from pathlib import Path

from run_model import messages
from score_contexts import citation_geometry

BASE = Path(__file__).parent


def table(headers, rows):
    return (
        "\n".join(
            [
                "| " + " | ".join(headers) + " |",
                "| " + " | ".join(["---"] * len(headers)) + " |",
                *["| " + " | ".join(map(str, row)) + " |" for row in rows],
            ]
        )
        + "\n"
    )


def describe_score(row):
    if row["kind"] == "behavior":
        return f"{sum(x['available'] for x in row['claims'])}/{len(row['claims'])} claim spans"
    if row["kind"] == "location":
        return "file present" if row["file_evidence_recall"] == 1 else "file absent"
    return "runtime evidence required"


def main():
    cases = {c["id"]: c for c in json.loads((BASE / "cases.reviewed.json").read_text())}
    contexts = {
        (c["case_id"], c["mode"]): c
        for p in (BASE / "results/contexts").glob("*.jsonl")
        for line in p.read_text().splitlines()
        if (c := json.loads(line))
    }
    scores = json.loads((BASE / "results/context-scores.json").read_text())
    answers = [
        json.loads(line)
        for line in (BASE / "results/interactive-answers.jsonl").read_text().splitlines()
        if line
    ]
    assert len(contexts) == len(answers) == 80
    freeze = json.loads((BASE / "results/baseline-freeze.json").read_text())
    assert (
        hashlib.sha256((BASE / "cases.json").read_bytes()).hexdigest()
        == freeze["sha256"]["cases.json"]
    )
    assert (
        hashlib.sha256((BASE / "results/no_context_answers.json").read_bytes()).hexdigest()
        == freeze["sha256"]["no_context_answers.json"]
    )
    prompt_dir = BASE / "results/prompts"
    prompt_dir.mkdir(exist_ok=True)
    for (cid, mode), ctx in contexts.items():
        case = cases[cid]
        chat = messages(case, ctx)
        (prompt_dir / f"{cid}-{mode}.json").write_text(
            json.dumps(
                dict(
                    case_id=cid,
                    mode=mode,
                    messages=chat,
                    dataset_sha256=ctx["dataset_sha256"],
                    context_sha256=ctx["context_sha256"],
                ),
                indent=2,
            )
            + "\n"
        )
    summary = []
    for mode in ["none", "bm25", "codectx", "gold"]:
        behavior = [r for r in scores if r["mode"] == mode and r["kind"] == "behavior"]
        location = [r for r in scores if r["mode"] == mode and r["kind"] == "location"]
        summary.append(
            dict(
                mode=mode,
                behavior_complete=sum(r["all_required_evidence"] for r in behavior),
                behavior_total=len(behavior),
                behavior_reference_claims_available=sum(
                    sum(c["available"] for c in r["claims"]) for r in behavior
                ),
                behavior_reference_claims_total=sum(len(r["claims"]) for r in behavior),
                location_gold_file_present=sum(r["file_evidence_recall"] == 1 for r in location),
                location_total=len(location),
            )
        )
    (BASE / "results/summary.json").write_text(
        json.dumps(
            dict(
                context_conditions=len(contexts),
                questions=len(cases),
                summary=summary,
                generator="interactive assistant, not isolated model-server calls",
                independent_answer_accuracy=None,
            ),
            indent=2,
        )
        + "\n"
    )
    text = [
        "# codectx RAG pilot\n",
        "**Result:** with the existing potion-code-16M-v2 embeddings and the stock codectx packer, all labeled behavior-source spans were present for **8/10 behavior questions**, versus **3/10** for file BM25 plus window selection. This measures supplied evidence, not generated-answer accuracy.\n",
        "This pilot has 20 questions over the same five pinned source snapshots: 10 behavior, 5 location, and 5 intentionally unanswerable deployment/runtime questions. It follows the [larger retrieval benchmark](../REPORT.md). Eight behavior questions explicitly name a method; the other two name a class/operation. This workload favors precise code navigation and does not replace the earlier open-ended natural-language benchmark.\n",
        "## Objective context measurements\n",
    ]
    text.append(
        table(
            [
                "Condition",
                "Behavior: all reference spans",
                "Behavior: reference claims covered",
                "Location: intended file present",
            ],
            [
                [
                    r["mode"],
                    f"{r['behavior_complete']}/{r['behavior_total']}",
                    f"{r['behavior_reference_claims_available']}/{r['behavior_reference_claims_total']}",
                    f"{r['location_gold_file_present']}/{r['location_total']}",
                ]
                for r in summary
            ],
        )
    )
    text.append(
        "Every context uses the same 6,000-character limit. Codectx uses k=10 and graph depth 0. BM25 ranks full supported-language files, then 30-line windows from its top ten files. Gold uses labeled source windows without reference answers. None contains no source evidence. No generation model is used to compute these measurements.\n"
    )
    text.append(
        "Reference-span coverage is conservative: equivalent evidence in a test or Javadoc may also answer a question without covering the labeled implementation lines. In particular, the BM25 ConcurrentHashMap excerpt includes method-contract statements about null arguments and recursion even though not all labeled body spans appear. Location questions are scored by intended file presence because a method belonging to a class can establish its location without the class declaration. Five deployment cases have no source-only gold answer and are excluded from coverage denominators.\n"
    )
    text.append("## What the assistant walkthrough showed\n")
    text.append(
        "* **S1, Spring profiles:** the no-context answer incorrectly expected a Spring assertion/IllegalArgumentException. Codectx supplied the actual setter: it replaces an unmodifiable LinkedHashSet through Arrays.asList. Null-array failure is NullPointerException under the JDK contract. The BM25 context instead showed similarly named builder/augmentation APIs, which cannot establish the setter behavior.\n"
    )
    text.append(
        "* **S2, availability defaults:** the no-context answer said liveness CORRECT. The actual default is **BROKEN**; readiness is REFUSING_TRAFFIC. Both codectx and BM25 supplied the relevant interface default methods.\n"
    )
    text.append(
        "* **D1, QuerySet slicing:** codectx found the intended file but packed the class header and neighboring tests, omitting __getitem__. BM25 supplied the actual negative-bound guard and stepped-slice branch.\n"
    )
    text.append(
        "* **K2, buffer shutdown:** both retrievers supplied related memory-waiter code but omitted the close methods. Normal memory-availability signaling does not prove the shutdown call chain. The reference shows RecordAccumulator.close → free.close → BufferPool.close → signal() on each waiter.\n"
    )
    text.append(
        "These examples demonstrate why learned API knowledge, intended-file hits and grounded answers are different measurements. They do not establish a causal answer-accuracy improvement.\n"
    )
    text.append("## Answer artifacts and limits\n")
    text.append(
        "The [80 answer artifacts](results/interactive-answers.jsonl) are the current assistant's interactive walkthrough: 20 frozen no-context answers, then 60 source-reviewed answers/abstentions for the other conditions. They were **not** produced by 80 independent API requests. The same assistant read references, answered and reviewed; later conditions share conversation state. Temperature, exact model-serving configuration, per-answer token counts and generation latency are unavailable and are recorded as missing. There is no independent or blind answer-quality score. Running record_interactive.py only packages the authored transcript; it does not execute a model.\n"
    )
    rows = []
    n_citations = 0
    for row in answers:
        case = cases[row["case_id"]]
        ctx = contexts[row["case_id"], row["mode"]]
        for citation in row["answer"]["citations"]:
            geometry = citation_geometry(citation, ctx, Path("/home/alien/repo") / case["repo"])
            assert geometry["valid_source_range"] and geometry["within_supplied_evidence"]
            n_citations += 1
        rows.append(
            dict(
                case_id=row["case_id"],
                mode=row["mode"],
                model=row["model"],
                answer_correctness="",
                faithfulness="",
                citation_support="",
                abstention_correct="",
                reviewer="",
                notes="Interactive, non-isolated walkthrough; independent grading pending.",
            )
        )
    text.append(
        f"All {n_citations} recorded citations point to valid source ranges contained in the supplied context ranges. This is citation geometry, **not semantic support precision**. Use the [review worksheet](results/answer-review.csv) to grade correctness, faithfulness, citation support and abstention independently.\n"
    )
    with (BASE / "results/interactive-review-template.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    worksheet = BASE / "results/answer-review.csv"
    if not worksheet.exists():
        worksheet.write_bytes((BASE / "results/interactive-review-template.csv").read_bytes())
    text.append("## Run any local generation model\n")
    text.append(
        "The [model runner](run_model.py) supports Ollama and OpenAI-compatible local servers. It sends fresh stateless chats, uses the same questions/contexts for every model, records actual usage and wall time when supplied, and checkpoints every completed request. Failed requests are retryable. The [optional judge](judge_model.py) grades required claims against the reference and checks groundedness only against actual retrieved evidence; its results remain fallible and need independent review. See the [run instructions](README.md). No local answer-generator performance is claimed from mocked protocol tests.\n"
    )
    text.append(
        "All 80 reusable [model-server prompts](results/prompts/) are exported without reference answers. A separate model service allows real condition isolation; the interactive walkthrough cannot provide that isolation. There is no need to install another local LLM to inspect context quality or perform this walkthrough.\n"
    )
    text.append("## Recommended tool changes\n")
    text.append(
        "1. Add body-aware retrieval or a lexical body/chunk fallback for questions such as negative-slice behavior.\n2. Prefer the matching qualified method over broad classes or similarly named APIs.\n3. Measure packed evidence after budget/truncation, not just whether a file was retrieved.\n4. Evaluate graph expansion separately on cross-file questions such as shutdown signaling; it was disabled in this pilot.\n5. Use independent, held-out questions and fresh generator/judge calls before reporting RAG answer accuracy or comparing local LLMs.\n"
    )
    text.append("## Per-case evidence audit\n")
    audit = []
    by_score = {(r["case_id"], r["mode"]): r for r in scores}
    for case in cases.values():
        c = by_score[case["id"], "codectx"]
        b = by_score[case["id"], "bm25"]
        audit.append(
            [
                case["id"],
                case["repo"],
                case["kind"],
                describe_score(c),
                describe_score(b),
                f"[codectx](results/prompts/{case['id']}-codectx.json) / [BM25](results/prompts/{case['id']}-bm25.json)",
            ]
        )
    text.append(table(["Case", "Repository", "Type", "Codectx", "BM25", "Actual prompts"], audit))
    text.append("## Evidence and checks\n")
    text.append(
        "* [Frozen questions](cases.json), [source-checked references and rubric](cases.reviewed.json), [baseline freeze hashes](results/baseline-freeze.json).\n* [Raw objective scores](results/context-scores.json), [summary JSON](results/summary.json), [test output](results/tests.txt).\n* Source line references, actual contexts, hashes and commit IDs are retained for every condition. No source repository files were changed.\n"
    )
    (BASE / "REPORT.md").write_text("\n".join(text))
    print(BASE / "REPORT.md")
    print("verified contexts", len(contexts), "answers", len(answers), "citations", n_citations)


if __name__ == "__main__":
    main()
