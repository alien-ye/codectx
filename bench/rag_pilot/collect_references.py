"""Select reference source directly, independent of the retrieval rankings."""

import json
import subprocess
from pathlib import Path

from codectx.extract import extract_symbols
from codectx.index import detect_language

BASE = Path(__file__).parent
ROOT = Path("/home/alien/repo")
TARGETS = {
    "D1": [("django/db/models/query.py", "QuerySet.__getitem__")],
    "D2": [("django/core/cache/backends/base.py", "BaseCache.get_backend_timeout")],
    "L1": [("libs/core/langchain_core/runnables/base.py", "RunnableSequence.invoke")],
    "L2": [("libs/core/langchain_core/retrievers.py", "BaseRetriever.invoke")],
    "S1": [
        (
            "core/spring-boot/src/main/java/org/springframework/boot/SpringApplication.java",
            "SpringApplication.setAdditionalProfiles",
        )
    ],
    "S2": [
        (
            "core/spring-boot/src/main/java/org/springframework/boot/availability/ApplicationAvailability.java",
            "ApplicationAvailability.getLivenessState",
        ),
        (
            "core/spring-boot/src/main/java/org/springframework/boot/availability/ApplicationAvailability.java",
            "ApplicationAvailability.getReadinessState",
        ),
        (
            "core/spring-boot/src/main/java/org/springframework/boot/availability/ApplicationAvailabilityBean.java",
            "ApplicationAvailabilityBean.getState",
        ),
    ],
    "K1": [
        (
            "clients/src/main/java/org/apache/kafka/clients/producer/KafkaProducer.java",
            "KafkaProducer.partition",
        )
    ],
    "K2": [
        (
            "clients/src/main/java/org/apache/kafka/clients/producer/internals/RecordAccumulator.java",
            "RecordAccumulator.close",
        ),
        (
            "clients/src/main/java/org/apache/kafka/clients/producer/internals/BufferPool.java",
            "BufferPool.close",
        ),
    ],
    "J1": [("src/java.base/share/classes/java/util/HashMap.java", "HashMap.computeIfAbsent")],
    "J2": [
        (
            "src/java.base/share/classes/java/util/concurrent/ConcurrentHashMap.java",
            "ConcurrentHashMap.computeIfAbsent",
        )
    ],
    "D3": [("django/urls/resolvers.py", "URLResolver")],
    "L3": [("libs/core/langchain_core/output_parsers/json.py", "JsonOutputParser")],
    "S3": [
        (
            "core/spring-boot-autoconfigure/src/main/java/org/springframework/boot/autoconfigure/AutoConfigurationImportSelector.java",
            "AutoConfigurationImportSelector",
        )
    ],
    "K3": [
        ("streams/src/main/java/org/apache/kafka/streams/StreamsBuilder.java", "StreamsBuilder")
    ],
    "J3": [("src/java.base/share/classes/java/util/concurrent/ForkJoinPool.java", "ForkJoinPool")],
}
records = []
for case in json.loads((BASE / "cases.json").read_text()):
    root = ROOT / case["repo"]
    spans = []
    for file, qname in TARGETS.get(case["id"], []):
        source = (root / file).read_text()
        matches = [
            s
            for s in extract_symbols(source, file, detect_language(file)).symbols
            if s.qualified_name == qname
        ]
        assert matches, (case["id"], qname)
        for symbol in matches:
            end = (
                min(symbol.end_line, symbol.start_line + 14)
                if case["kind"] == "location"
                else symbol.end_line
            )
            spans.append(
                dict(
                    file=file,
                    start=symbol.start_line,
                    end=end,
                    qualified_name=qname,
                    text="\n".join(source.splitlines()[symbol.start_line - 1 : end]),
                )
            )
    records.append(
        {
            **case,
            "reference_spans": spans,
            "commit": subprocess.check_output(
                ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
            ).strip(),
            "reference_answer": None,
            "essential_claims": [],
            "review_status": "needs_source_review",
        }
    )
(BASE / "results/reference_drafts.json").write_text(json.dumps(records, indent=2) + "\n")
for record in records:
    if record["kind"] == "behavior":
        print("\n###", record["id"], record["question"])
        for span in record["reference_spans"]:
            print(span["file"], span["start"], span["end"])
            print(
                "\n".join(
                    f"{span['start'] + i}: {line}"
                    for i, line in enumerate(span["text"].splitlines())
                )
            )
