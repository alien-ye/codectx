"""Package answers authored during this interactive walkthrough.

Executing this file does NOT run a model. The constants are the current assistant's
source-reviewed answers, with non-isolation and self-review explicitly recorded.
Use run_model.py for actual independent model-server requests.
"""

import hashlib
import json
from pathlib import Path

from score_contexts import citation_geometry

BASE = Path(__file__).parent
UNKNOWN = "The supplied repository excerpts cannot establish this deployment-specific runtime value. Effective deployment settings or an operator-provided runtime snapshot are needed; I will not invent the requested value or credential."

# (answer text, abstain, citations as (file or reference-span index, first line, last line)).
CODECTX = {
    "D1": (
        "The pack identifies QuerySet but omits __getitem__, its negative-bound checks, and its stepped-slice branch. The slicing-related tests shown concern different operations. I cannot verify the requested behavior from this context.",
        True,
        [],
    ),
    "D2": (
        "DEFAULT_TIMEOUT selects self.default_timeout. An explicit zero is changed to -1, so it becomes time.time() - 1. None is returned unchanged; other numeric timeouts become time.time() + timeout.",
        False,
        [(0, 87, 97)],
    ),
    "D3": (
        "URLResolver, in django/urls/resolvers.py. The pack includes URLResolver.resolve and its url_patterns property.",
        False,
        [(0, 671, 671), (0, 728, 728)],
    ),
    "L1": (
        "Only the first step receives **kwargs; subsequent steps receive input and config without them. Each step gets a child callback configuration. A BaseException calls on_chain_error and is re-raised; success calls on_chain_end and returns the output.",
        False,
        [(0, 3472, 3488)],
    ),
    "L2": (
        "On failure, invoke calls on_retriever_error(e) and re-raises. On success it calls on_retriever_end(result) and returns the documents.",
        False,
        [(0, 227, 234)],
    ),
    "L3": (
        "JsonOutputParser in libs/core/langchain_core/output_parsers/json.py. Its parse and parse_result methods are supplied.",
        False,
        [(0, 97, 97), (0, 62, 62)],
    ),
    "S1": (
        "The setter replaces additionalProfiles with an unmodifiable LinkedHashSet created from Arrays.asList(profiles). The set deduplicates while preserving encounter order. There is no Spring assertion here: a null array reaches Arrays.asList and causes NullPointerException under the standard JDK contract.",
        False,
        [(0, 1095, 1097)],
    ),
    "S2": (
        "Liveness defaults to LivenessState.BROKEN and readiness to ReadinessState.REFUSING_TRAFFIC. These values appear in the inherited ApplicationAvailability default methods; the supplied bean getter returns null when no event exists.",
        False,
        [(0, 29, 31), (1, 37, 39), (3, 50, 54)],
    ),
    "S3": (
        "AutoConfigurationImportSelector in core/spring-boot-autoconfigure/src/main/java/org/springframework/boot/autoconfigure/AutoConfigurationImportSelector.java. Its production selectImports method is included.",
        False,
        [(0, 106, 106)],
    ),
    "K1": (
        "The explicit record partition wins. Otherwise a custom partitioner is called and a negative result causes IllegalArgumentException. Without a custom partitioner, a non-null serialized key is hashed using BuiltInPartitioner.partitionForKey unless ignore-keys is enabled; the fallback is UNKNOWN_PARTITION. The supplied configuration documentation says ignore-keys does not affect a custom partitioner.",
        False,
        [
            (0, 1687, 1705),
            (
                "clients/src/main/java/org/apache/kafka/clients/producer/ProducerConfig.java",
                124,
                126,
            ),
        ],
    ),
    "K2": (
        "The pack shows normal memory-availability signaling of the first waiter, but neither close implementation. That helper is not proof of the shutdown path. I cannot verify the close-to-buffer-pool chain or how shutdown wakes all waiters from the supplied evidence.",
        True,
        [(1, 422, 425)],
    ),
    "K3": (
        "The excerpts show KafkaStreams and an unrelated connector, not the high-level builder implementation. They do not establish the requested production builder source file.",
        True,
        [],
    ),
    "J1": (
        "An existing non-null value is returned before applying the mapping function. A null computed value is returned without installing a value. modCount is saved around apply; a changed count causes ConcurrentModificationException before the null-result check.",
        False,
        [(0, 1221, 1235)],
    ),
    "J2": (
        "A null key or mapping function throws NullPointerException. A null computed result does not create a node. A detectably recursive update throws IllegalStateException; the visible predecessor-link check and method documentation establish this. The source snippet is truncated before the later ReservationNode branch, which I cannot quote from this pack.",
        False,
        [(0, 1691, 1711), (0, 1738, 1744)],
    ),
    "J3": (
        "The excerpts point to ForkJoinPool, in src/java.base/share/classes/java/util/concurrent/ForkJoinPool.java. They show its nested WorkQueue field and a worker class managed by that pool, rather than the pool class declaration or full scheduling implementation.",
        False,
        [
            (0, 1062, 1062),
            ("src/java.base/share/classes/java/util/concurrent/ForkJoinWorkerThread.java", 59, 72),
        ],
    ),
}
BM25 = {
    "D1": (
        "Negative integer indices and negative start/stop bounds raise ValueError before the result-cache shortcut. For an uncached slice, limits are applied to a cloned queryset; a truthy step produces list(qs)[::step], otherwise qs is returned. Cached results use Python indexing directly.",
        False,
        [(0, 506, 529)],
    ),
    "D2": (
        "The pack shows Redis and memcached-specific timeout code, but not BaseCache.get_backend_timeout itself. Those overrides do not establish the base implementation's exact handling of None and explicit zero, so I cannot verify the full answer from these excerpts.",
        True,
        [],
    ),
    "D3": (
        "The provided excerpts are URL-pattern and related tests, not the production nested resolver implementation. I cannot verify its production class and source path from this context.",
        True,
        [],
    ),
    "L1": (
        "The shown callback/error code belongs to a futures-based mapping of steps, not the requested sequential first-step branch. It is not sufficient to establish which RunnableSequence step receives kwargs or to verify its specific failure path.",
        True,
        [],
    ),
    "L2": (
        "The snippets show a caller invoking a retriever and other callback infrastructure, but omit BaseRetriever.invoke. They do not verify its error/end callbacks or re-raise behavior.",
        True,
        [],
    ),
    "L3": (
        "The tests import a name JsonOutputParser, but the pack does not include its production implementation or its source path. I cannot verify the requested class/file pair from this evidence.",
        True,
        [],
    ),
    "S1": (
        "The excerpts show Augmented.withAdditionalProfiles merging a set and builder methods calling the application setter. These are different APIs from SpringApplication.setAdditionalProfiles. The actual setter is absent, so its replacement and null-array behavior cannot be established from this pack.",
        True,
        [],
    ),
    "S2": (
        "The defaults are LivenessState.BROKEN and ReadinessState.REFUSING_TRAFFIC. Both constants are explicit in ApplicationAvailability's default methods, and the included bean test confirms the no-event liveness result.",
        False,
        [
            (0, 29, 39),
            (
                "core/spring-boot/src/test/java/org/springframework/boot/availability/ApplicationAvailabilityBeanTests.java",
                46,
                49,
            ),
        ],
    ),
    "S3": (
        "The annotation excerpt refers to ImportAutoConfigurationImportSelector, but no selector implementation file is included. That reference does not verify the intended production selector's implementation path.",
        True,
        [],
    ),
    "K1": (
        "An explicit partition is returned first. A custom partitioner is called next and negative results are rejected. Otherwise the serialized key is hashed only when non-null and ignore-keys is false; the fallback is UNKNOWN_PARTITION. The ignore-keys option has no effect on custom partitioning.",
        False,
        [
            (0, 1686, 1705),
            (
                "clients/src/main/java/org/apache/kafka/clients/producer/ProducerConfig.java",
                123,
                126,
            ),
        ],
    ),
    "K2": (
        "The snippets describe memory waiters and normal signaling when memory becomes available. They do not include RecordAccumulator.close or BufferPool.close. I cannot establish the requested shutdown call chain or wake-up operation.",
        True,
        [],
    ),
    "K3": (
        "The example imports StreamsBuilder and describes topology wiring through it. Its production implementation file is not supplied, so I can identify that class reference but cannot verify the requested implementation path from the pack.",
        True,
        [
            (
                "streams/quickstart/java/src/main/resources/archetype-resources/src/main/java/Pipe.java",
                19,
                23,
            ),
            (
                "streams/examples/src/main/java/org/apache/kafka/streams/examples/wordcount/WordCountTransformerDemo.java",
                55,
                57,
            ),
        ],
    ),
    "J1": (
        "The Map default-method excerpts compute only when get returns null and install a non-null result. They recommend modification detection for overrides, but do not show HashMap's override. I cannot verify that implementation's modCount behavior from this evidence.",
        True,
        [("src/java.base/share/classes/java/util/Map.java", 1015, 1028)],
    ),
    "J2": (
        "The ConcurrentHashMap contract says null key or function causes NullPointerException, a null computed value is returned as null, and detectable recursive updates cause IllegalStateException. The shown empty-bin branch creates a node only for a non-null result. The remaining insertion branches are not supplied.",
        False,
        [(0, 1681, 1709)],
    ),
    "J3": (
        "ForkJoinPool in src/java.base/share/classes/java/util/concurrent/ForkJoinPool.java is the work-stealing executor. Its class declaration and overview are supplied, and Executors.newWorkStealingPool directly constructs it.",
        False,
        [
            (0, 186, 205),
            ("src/java.base/share/classes/java/util/concurrent/Executors.java", 114, 118),
        ],
    ),
}
GOLD = {
    "D1": (
        "Negative integer and start/stop slice bounds raise ValueError before cache lookup. Cached results use Python indexing. For an uncached slice, a truthy step materializes list(qs) and slices it; otherwise the limited queryset is returned.",
        False,
        [(0, 506, 529)],
    ),
    "D2": (
        "The sentinel selects default_timeout; explicit zero becomes -1 before adding current time. None stays None; numeric timeouts become absolute timestamps.",
        False,
        [(0, 92, 97)],
    ),
    "D3": ("URLResolver in django/urls/resolvers.py.", False, [(0, 504, 504)]),
    "L1": (
        "Only step zero receives **kwargs. Failure calls on_chain_error and re-raises; successful completion calls on_chain_end and returns the final output.",
        False,
        [(0, 3472, 3488)],
    ),
    "L2": (
        "Failures call on_retriever_error and re-raise; success calls on_retriever_end and returns result.",
        False,
        [(0, 227, 234)],
    ),
    "L3": ("JsonOutputParser in libs/core/langchain_core/output_parsers/json.py.", False, []),
    "S1": (
        "The setter replaces the set with an unmodifiable LinkedHashSet, preserving encounter order and removing duplicates. A null array fails through Arrays.asList with NullPointerException under the standard JDK contract; there is no explicit Spring null assertion.",
        False,
        [(0, 1095, 1097)],
    ),
    "S2": (
        "The interface defaults are BROKEN for liveness and REFUSING_TRAFFIC for readiness, not CORRECT for liveness.",
        False,
        [(0, 29, 31), (1, 37, 39)],
    ),
    "S3": (
        "AutoConfigurationImportSelector in core/spring-boot-autoconfigure/src/main/java/org/springframework/boot/autoconfigure/AutoConfigurationImportSelector.java.",
        False,
        [],
    ),
    "K1": (
        "An explicit partition wins. Otherwise a custom partitioner is used and negative results are rejected. A key is hashed only when present and ignore-keys is false; other built-in cases return UNKNOWN_PARTITION.",
        False,
        [(0, 1687, 1705)],
    ),
    "K2": (
        "Accumulator closure sets closed and calls this.free.close(). BufferPool.close holds its lock, sets closed, calls signal() on every waiter Condition, and releases the lock in finally.",
        False,
        [(0, 1335, 1338), (1, 575, 584)],
    ),
    "K3": (
        "StreamsBuilder in streams/src/main/java/org/apache/kafka/streams/StreamsBuilder.java.",
        False,
        [],
    ),
    "J1": (
        "An existing non-null value is returned without computation. A null computed value is not installed. A changed modCount after mappingFunction.apply triggers ConcurrentModificationException before checking for a null result.",
        False,
        [(0, 1221, 1231)],
    ),
    "J2": (
        "Null key/function throws NullPointerException. A null computation does not create a node. Detectably recursive updates throw IllegalStateException, as demonstrated by the shown predecessor-link check.",
        False,
        [(0, 1691, 1693), (0, 1706, 1711), (0, 1738, 1744)],
    ),
    "J3": (
        "ForkJoinPool in src/java.base/share/classes/java/util/concurrent/ForkJoinPool.java.",
        False,
        [],
    ),
}


def main():
    cases = {r["id"]: r for r in json.loads((BASE / "cases.reviewed.json").read_text())}
    contexts = {
        (r["case_id"], r["mode"]): r
        for p in (BASE / "results/contexts").glob("*.jsonl")
        for line in p.read_text().splitlines()
        if (r := json.loads(line))
    }
    baseline = json.loads((BASE / "results/no_context_answers.json").read_text())["answers"]
    rows = []
    for cid, case in cases.items():
        for mode, table in [("none", None), ("codectx", CODECTX), ("bm25", BM25), ("gold", GOLD)]:
            ctx = contexts[cid, mode]
            if mode == "none":
                answer = baseline[cid]
            else:
                text, abstain, citations = (
                    (UNKNOWN, True, []) if not case["answerable"] else table[cid]
                )
                if mode == "gold" and case["kind"] == "location" and not citations:
                    s = case["reference_spans"][0]
                    citations = [(s["file"], s["start"], s["start"])]
                cite = [
                    dict(
                        file=case["reference_spans"][file]["file"]
                        if isinstance(file, int)
                        else file,
                        start=start,
                        end=end,
                    )
                    for file, start, end in citations
                ]
                for c in cite:
                    geometry = citation_geometry(c, ctx, Path("/home/alien/repo") / case["repo"])
                    assert (
                        geometry["valid_source_range"] and geometry["within_supplied_evidence"]
                    ), (cid, mode, c, geometry)
                answer = dict(answer=text, abstain=abstain, citations=cite)
            key = hashlib.sha256(
                json.dumps(
                    dict(case_id=cid, mode=mode, answer=answer, origin="interactive_nonisolated"),
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            rows.append(
                dict(
                    run_key=key,
                    case_id=cid,
                    mode=mode,
                    model="current Codex assistant (interactive, non-isolated)",
                    status="ok",
                    answer=answer,
                    answer_origin="interactive_source_review_not_model_server_request",
                    condition_isolation=False,
                    independent_human_review=False,
                    dataset_sha256=ctx["dataset_sha256"],
                    context_sha256=ctx["context_sha256"],
                    prompt_sha256=None,
                    temperature=None,
                    seed=None,
                    seconds=None,
                    usage=None,
                    format_valid=True,
                )
            )
    (BASE / "results/interactive-answers.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows)
    )
    print(len(rows), "interactive answer artifacts; no model-server requests performed")


if __name__ == "__main__":
    main()
