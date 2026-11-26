"""Source-checked rubric. This is an assistant review, not independent human review."""

import json
from pathlib import Path

BASE = Path(__file__).parent
rows = json.loads((BASE / "results/reference_drafts.json").read_text())
F = {
    "D1": (
        "Negative integer indices and negative start/stop bounds raise ValueError before the result-cache shortcut. Cached results use Python indexing. An uncached slice clones the queryset, sets query limits, and applies a truthy step to list(qs); without a truthy step it returns qs.",
        [
            (0, 506, 513, "Negative integer/start/stop bounds raise ValueError."),
            (
                0,
                518,
                529,
                "An uncached truthy-step slice materializes a list; otherwise it returns the limited queryset.",
            ),
        ],
    ),
    "D2": (
        "The sentinel selects self.default_timeout. An explicit zero becomes -1, producing a timestamp one second in the past. None remains None; other numeric values become time.time() + timeout.",
        [
            (0, 92, 93, "DEFAULT_TIMEOUT selects self.default_timeout."),
            (0, 94, 97, "Explicit zero is changed to -1 before adding time.time()."),
            (0, 97, 97, "None stays None; numeric timeouts become absolute timestamps."),
        ],
    ),
    "L1": (
        "Only the first step receives **kwargs. Each step gets child-run callbacks. A BaseException triggers on_chain_error and a bare raise; successful completion invokes on_chain_end and returns the last output.",
        [
            (
                0,
                3472,
                3481,
                "Extra kwargs are passed only to the first step; child callback config is propagated.",
            ),
            (0, 3483, 3485, "Failure calls on_chain_error and re-raises."),
        ],
    ),
    "L2": (
        "Failure invokes on_retriever_error and re-raises the exception. Success invokes on_retriever_end(result) and returns result.",
        [
            (0, 227, 229, "Failure calls on_retriever_error and re-raises."),
            (0, 230, 234, "Success calls on_retriever_end and returns the documents."),
        ],
    ),
    "S1": (
        "The setter replaces this.additionalProfiles with an unmodifiable LinkedHashSet built from Arrays.asList(profiles). Duplicates are removed and encounter order is preserved. There is no Assert.notNull check here: passing a null array reaches Arrays.asList and causes NullPointerException under the JDK API contract, rather than a Spring assertion IllegalArgumentException.",
        [
            (0, 1095, 1097, "Replaces the existing set rather than adding to it."),
            (0, 1096, 1096, "LinkedHashSet removes duplicates and preserves encounter order."),
            (
                0,
                1096,
                1096,
                "Null-array behavior follows Arrays.asList: NullPointerException, not an Assert.notNull IllegalArgumentException.",
            ),
        ],
    ),
    "S2": (
        "The methods are inherited default methods on ApplicationAvailability. Liveness defaults to BROKEN and readiness defaults to REFUSING_TRAFFIC. ApplicationAvailabilityBean.getState returns its supplied default when no recorded state is found.",
        [
            (0, 29, 31, "Liveness defaults to LivenessState.BROKEN."),
            (1, 37, 39, "Readiness defaults to ReadinessState.REFUSING_TRAFFIC."),
        ],
    ),
    "K1": (
        "An explicit record partition is returned first. A custom partitioner is called next, and a negative result throws IllegalArgumentException. Otherwise a non-null serialized key is passed to BuiltInPartitioner.partitionForKey unless partitionerIgnoreKeys is true; the fallback is RecordMetadata.UNKNOWN_PARTITION.",
        [
            (0, 1687, 1688, "An explicit record partition takes precedence."),
            (
                0,
                1690,
                1697,
                "A configured custom partitioner is called and negative results are rejected.",
            ),
            (
                0,
                1700,
                1704,
                "A serialized key is hashed unless ignore-keys is enabled; otherwise UNKNOWN_PARTITION is returned.",
            ),
        ],
    ),
    "K2": (
        "RecordAccumulator.close sets closed and calls this.free.close(). BufferPool.close takes its lock, sets its own closed flag, and calls waiter.signal() for every Condition in waiters, unlocking in finally. It does not call a single shared Condition.signalAll().",
        [
            (0, 1335, 1338, "Accumulator closure calls this.free.close()."),
            (
                1,
                575,
                584,
                "BufferPool.close locks, sets closed, signals each waiter with waiter.signal(), and unlocks in finally.",
            ),
        ],
    ),
    "J1": (
        "An existing non-null value is returned without applying the function. A null computed value is not installed. The method snapshots modCount around mappingFunction.apply and throws ConcurrentModificationException if the count changes, before handling a null result.",
        [
            (0, 1221, 1224, "An existing non-null value is returned before mappingFunction.apply."),
            (0, 1227, 1231, "A null result does not install a value."),
            (0, 1227, 1229, "Changed modCount after apply causes ConcurrentModificationException."),
        ],
    ),
    "J2": (
        'Null key or null mapping function throws NullPointerException. A null computed value is not installed. Detectable recursive updates throw IllegalStateException("Recursive update"), including a changed predecessor link or a ReservationNode encountered during computation.',
        [
            (0, 1691, 1693, "Null key or mapping function throws NullPointerException."),
            (0, 1706, 1711, "A null computed result does not install a node."),
            (0, 1738, 1744, "A detectably recursive link update throws IllegalStateException."),
        ],
    ),
}
for row in rows:
    if row["kind"] == "behavior":
        answer, claims = F[row["id"]]
        row["reference_answer"] = answer
        row["essential_claims"] = [
            dict(
                id=f"{row['id']}.{i}",
                text=text,
                evidence=[dict(file=row["reference_spans"][span]["file"], start=start, end=end)],
            )
            for i, (span, start, end, text) in enumerate(claims, 1)
        ]
    elif row["kind"] == "location":
        span = row["reference_spans"][0]
        row["reference_answer"] = f"{span['qualified_name']} in {span['file']}."
        row["essential_claims"] = [
            dict(
                id=row["id"] + ".1",
                text=row["reference_answer"],
                evidence=[dict(file=span["file"], start=span["start"], end=span["start"])],
            )
        ]
    else:
        row["reference_answer"] = (
            "Insufficient deployment/runtime evidence in this source snapshot; do not invent the requested production value or credential."
        )
        row["essential_claims"] = []
    if row["id"] == "J2":
        row["essential_claims"][-1]["text"] = (
            "A detectably recursive update throws IllegalStateException."
        )
        row["essential_claims"][-1]["evidence"].append(
            dict(file=row["reference_spans"][0]["file"], start=1762, end=1763)
        )
        row["essential_claims"][-1]["evidence_mode"] = "any"
    row["answerable"] = row["kind"] != "unanswerable"
    row["review_status"] = "assistant_source_checked_not_independent_human_review"
    if row["id"] == "S1":
        row["inference_note"] = (
            "NullPointerException relies on standard JDK Arrays.asList null-array semantics in addition to the shown setter source."
        )
    for claim in row["essential_claims"]:
        for span in claim["evidence"]:
            source = (
                (Path("/home/alien/repo") / row["repo"] / span["file"]).read_text().splitlines()
            )
            assert 1 <= span["start"] <= span["end"] <= len(source)
            span["text"] = "\n".join(source[span["start"] - 1 : span["end"]])
(BASE / "cases.reviewed.json").write_text(json.dumps(rows, indent=2) + "\n")
print(
    len(rows),
    "source-checked cases;",
    sum(len(r["essential_claims"]) for r in rows),
    "essential claims",
)
