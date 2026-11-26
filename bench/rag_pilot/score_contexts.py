"""Objective evidence availability and citation geometry, never an LLM quality score."""

import csv
import json
from pathlib import Path

BASE = Path(__file__).parent


def covered(required, provided):
    position = required["start"]
    for span in sorted(
        (s for s in provided if s["file"] == required["file"]), key=lambda s: s["start"]
    ):
        if span["start"] > position:
            break
        if span["end"] >= position:
            position = span["end"] + 1
        if position > required["end"]:
            return True
    return False


def score(case, context):
    spans = context["provided_spans"]
    required = case["essential_claims"]
    claim_results = []
    for claim in required:
        checks = [covered(s, spans) for s in claim["evidence"]]
        ok = any(checks) if claim.get("evidence_mode") == "any" else all(checks)
        claim_results.append(dict(claim_id=claim["id"], available=ok))
    files = {s["file"] for claim in required for s in claim["evidence"]}
    present = {s["file"] for s in spans}
    return dict(
        case_id=case["id"],
        repo=case["repo"],
        kind=case["kind"],
        mode=context["mode"],
        answerable=case["answerable"],
        file_evidence_recall=len(files & present) / len(files) if files else None,
        claim_evidence_recall=sum(c["available"] for c in claim_results) / len(required)
        if required
        else None,
        all_required_evidence=all(c["available"] for c in claim_results) if required else None,
        claims=claim_results,
        context_characters=context["context_characters"],
        context_sha256=context["context_sha256"],
    )


def citation_geometry(citation, context, root):
    file = citation.get("file", "")
    start = citation.get("start")
    end = citation.get("end")
    if not isinstance(file, str) or type(start) is not int or type(end) is not int:
        return dict(
            valid_source_range=False,
            within_supplied_evidence=False,
            semantic_support="requires_review",
        )
    path = (root / file).resolve()
    valid = (
        isinstance(file, str)
        and type(start) is int
        and type(end) is int
        and 1 <= start <= end
        and path.is_relative_to(root.resolve())
        and path.is_file()
    )
    if valid:
        valid = end <= len(path.read_text(errors="replace").splitlines())
    return dict(
        valid_source_range=valid,
        within_supplied_evidence=valid and covered(citation, context["provided_spans"]),
        semantic_support="requires_review",
    )


def main():
    cases = {r["id"]: r for r in json.loads((BASE / "cases.reviewed.json").read_text())}
    contexts = [
        json.loads(line)
        for p in sorted((BASE / "results/contexts").glob("*.jsonl"))
        for line in p.read_text().splitlines()
        if line
    ]
    assert len(contexts) == len(cases) * 4, "Incomplete context preparation"
    results = [score(cases[c["case_id"]], c) for c in contexts]
    (BASE / "results/context-scores.json").write_text(json.dumps(results, indent=2) + "\n")
    with (BASE / "results/answer-review-template.csv").open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "case_id",
                "mode",
                "model",
                "answer_correctness",
                "faithfulness",
                "citation_support",
                "abstention_correct",
                "reviewer",
                "notes",
            ],
        )
        writer.writeheader()
        for c in contexts:
            writer.writerow(dict(case_id=c["case_id"], mode=c["mode"], model=""))
    worksheet = BASE / "results/answer-review.csv"
    if not worksheet.exists():
        worksheet.write_bytes((BASE / "results/answer-review-template.csv").read_bytes())
    for mode in ["none", "bm25", "codectx", "gold"]:
        group = [r for r in results if r["mode"] == mode and r["answerable"]]
        print(
            mode,
            "complete_evidence",
            sum(r["all_required_evidence"] for r in group),
            "/",
            len(group),
            "claim_coverage",
            sum(sum(c["available"] for c in r["claims"]) for r in group),
            "/",
            sum(len(r["claims"]) for r in group),
        )


if __name__ == "__main__":
    main()
