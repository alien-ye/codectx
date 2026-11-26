"""Freeze pilot questions before collecting new source evidence."""

import hashlib
import json
from pathlib import Path

BASE = Path(__file__).parent
entries = [
    (
        "D1",
        "django",
        "behavior",
        "What happens when a QuerySet is indexed or sliced using a negative bound? What happens to a slice that specifies a step?",
    ),
    (
        "D2",
        "django",
        "behavior",
        "How does BaseCache.get_backend_timeout handle DEFAULT_TIMEOUT, None, and a timeout of zero?",
    ),
    (
        "D3",
        "django",
        "location",
        "Which production class and source file resolve incoming request paths against nested URL patterns?",
    ),
    (
        "D4",
        "django",
        "unanswerable",
        "What cache timeout value is configured in our production Django deployment right now?",
    ),
    (
        "L1",
        "langchain",
        "behavior",
        "In RunnableSequence.invoke, which step receives extra caller keyword arguments, and what happens to callbacks and the exception if a step fails?",
    ),
    (
        "L2",
        "langchain",
        "behavior",
        "In BaseRetriever.invoke, which lifecycle callback runs on failure, which runs on success, and is a retrieval exception returned or re-raised?",
    ),
    (
        "L3",
        "langchain",
        "location",
        "Which production class and source file parse language model output as a JSON object?",
    ),
    (
        "L4",
        "langchain",
        "unanswerable",
        "Which database endpoint and credentials does our deployed conversation-history service currently use?",
    ),
    (
        "S1",
        "spring-boot",
        "behavior",
        "Does SpringApplication.setAdditionalProfiles replace or append to its existing set, what happens to duplicates, and how is a null profiles array handled?",
    ),
    (
        "S2",
        "spring-boot",
        "behavior",
        "Before any availability state has been recorded, what do ApplicationAvailabilityBean.getLivenessState and getReadinessState return?",
    ),
    (
        "S3",
        "spring-boot",
        "location",
        "Which production class and source file select the auto-configuration classes to import?",
    ),
    (
        "S4",
        "spring-boot",
        "unanswerable",
        "What is the externally reachable actuator health URL and its access credential in our current production deployment?",
    ),
    (
        "K1",
        "kafka",
        "behavior",
        "In KafkaProducer.partition, how are an explicit record partition, a configured custom partitioner, and a serialized key handled? What changes when partitioner.ignore.keys is enabled?",
    ),
    (
        "K2",
        "kafka",
        "behavior",
        "When RecordAccumulator is closed, how are threads waiting for buffer memory awakened? Identify the call into the buffer pool and the operation that wakes waiters.",
    ),
    (
        "K3",
        "kafka",
        "location",
        "Which production class and source file build a stream-processing topology through the high-level DSL?",
    ),
    (
        "K4",
        "kafka",
        "unanswerable",
        "What bootstrap broker addresses and SASL credentials are being used by our production Kafka producer right now?",
    ),
    (
        "J1",
        "jdk21u",
        "behavior",
        "In HashMap.computeIfAbsent, what happens for an existing non-null value, for a null mapping-function result, and when the mapping function structurally modifies the map?",
    ),
    (
        "J2",
        "jdk21u",
        "behavior",
        "In ConcurrentHashMap.computeIfAbsent, what happens for a null key or mapping function, for a null computed value, and for a detectably recursive update?",
    ),
    (
        "J3",
        "jdk21u",
        "location",
        "Which production class and source file implement the work-stealing executor for fork/join tasks?",
    ),
    (
        "J4",
        "jdk21u",
        "unanswerable",
        "What is the actual common ForkJoinPool parallelism of our running production JVM, including its runtime overrides?",
    ),
]
cases = [dict(id=i, repo=r, kind=k, question=q) for i, r, k, q in entries]
path = BASE / "cases.json"
if path.exists():
    assert json.loads(path.read_text()) == cases, "Frozen cases differ"
else:
    path.write_text(json.dumps(cases, indent=2) + "\n")
print("cases", len(cases), "sha256", hashlib.sha256(path.read_bytes()).hexdigest())
