"""Explicit natural-language labels, resolved from source files, never retrieval results."""

import json
import os
import re
from pathlib import Path

TARGETS = {
    "django": [
        (
            "QuerySet",
            "Build lazy database queries and filter model records",
            "django/db/models/query.py",
        ),
        (
            "Model",
            "Base class for persistent database objects and saving instances",
            "django/db/models/base.py",
        ),
        (
            "URLResolver",
            "Resolve incoming request paths against nested URL patterns",
            "django/urls/resolvers.py",
        ),
        ("Template", "Compile and render template text with a context", "django/template/base.py"),
        (
            "AuthenticationMiddleware",
            "Attach the authenticated user to each HTTP request",
            "django/contrib/auth/middleware.py",
        ),
        (
            "Paginator",
            "Divide a collection of results into numbered pages",
            "django/core/paginator.py",
        ),
        (
            "HttpResponse",
            "Represent an outgoing HTTP response with headers and content",
            "django/http/response.py",
        ),
        (
            "BaseCache",
            "Common interface for cache backends and key expiration",
            "django/core/cache/backends/base.py",
        ),
        (
            "BaseForm",
            "Validate submitted form fields and collect validation errors",
            "django/forms/forms.py",
        ),
        (
            "MigrationExecutor",
            "Plan and execute database schema migrations",
            "django/db/migrations/executor.py",
        ),
    ],
    "langchain": [
        (
            "RunnableSequence",
            "Compose processing steps so one output feeds the next",
            "libs/core/langchain_core/runnables/base.py",
        ),
        (
            "BaseChatModel",
            "Common interface for chat model invocation and streaming",
            "libs/core/langchain_core/language_models/chat_models.py",
        ),
        (
            "BaseRetriever",
            "Interface for retrieving relevant documents given a query",
            "libs/core/langchain_core/retrievers.py",
        ),
        (
            "ChatPromptTemplate",
            "Build chat prompts from templated messages",
            "libs/core/langchain_core/prompts/chat.py",
        ),
        (
            "BaseTool",
            "Define callable tools with input schemas and validation",
            "libs/core/langchain_core/tools/base.py",
        ),
        (
            "RecursiveCharacterTextSplitter",
            "Recursively split text into chunks using a list of separators",
            "libs/text-splitters/langchain_text_splitters/character.py",
        ),
        (
            "InMemoryVectorStore",
            "Store document embeddings in memory and find similar documents",
            "libs/core/langchain_core/vectorstores/in_memory.py",
        ),
        (
            "RunnableParallel",
            "Run multiple processing branches concurrently on the same input",
            "libs/core/langchain_core/runnables/base.py",
        ),
        (
            "JsonOutputParser",
            "Parse language model responses into JSON objects",
            "libs/core/langchain_core/output_parsers/json.py",
        ),
        (
            "RunnableWithMessageHistory",
            "Maintain conversation message history across runnable invocations",
            "libs/core/langchain_core/runnables/history.py",
        ),
    ],
    "spring-boot": [
        ("SpringApplication", "Bootstrap and launch a standalone Spring application", None),
        (
            "AutoConfigurationImportSelector",
            "Select which auto configuration classes should be imported",
            None,
        ),
        (
            "SpringBootApplication",
            "Annotation combining application configuration component scanning and auto configuration",
            None,
        ),
        (
            "ConfigurationPropertiesBinder",
            "Bind external property values to configuration properties beans",
            None,
        ),
        (
            "HealthEndpoint",
            "Expose application health information through an actuator endpoint",
            None,
        ),
        (
            "ApplicationAvailabilityBean",
            "Track application liveness and readiness state changes",
            None,
        ),
        (
            "LoggingApplicationListener",
            "Initialize the logging system during application startup events",
            None,
        ),
        ("FailureAnalyzer", "Analyze startup failures and provide actionable diagnostics", None),
        ("JarLauncher", "Launch an executable archive with nested dependency jars", None),
        (
            "RestClientAutoConfiguration",
            "Automatically configure the synchronous REST client builder",
            None,
        ),
    ],
    "kafka": [
        ("KafkaProducer", "Public client for publishing records to Kafka topics", None),
        ("KafkaConsumer", "Public client for subscribing to topics and consuming records", None),
        (
            "RecordAccumulator",
            "Accumulate records into batches before sending them to brokers",
            None,
        ),
        ("Sender", "Background producer thread that sends record batches to brokers", None),
        ("NetworkClient", "Manage nonblocking network connections and broker requests", None),
        (
            "ConsumerCoordinator",
            "Coordinate consumer group membership and partition assignment",
            None,
        ),
        (
            "TransactionManager",
            "Manage producer transactions and idempotent sequence numbers",
            None,
        ),
        ("StreamsBuilder", "Build a stream processing topology using the high level DSL", None),
        (
            "Topology",
            "Define the graph of processors for a stream processing application",
            "streams/src/main/java/org/apache/kafka/streams/Topology.java",
        ),
        (
            "KafkaAdminClient",
            "Implement administrative requests for topics brokers and consumer groups",
            None,
        ),
    ],
    "jdk21u": [
        (
            "HashMap",
            "Hash table implementation of the map interface allowing null keys",
            "src/java.base/share/classes/java/util/HashMap.java",
        ),
        (
            "ConcurrentHashMap",
            "Concurrent hash table supporting thread safe retrievals and updates",
            "src/java.base/share/classes/java/util/concurrent/ConcurrentHashMap.java",
        ),
        (
            "Thread",
            "Create and manage platform and virtual execution threads",
            "src/java.base/share/classes/java/lang/Thread.java",
        ),
        (
            "CompletableFuture",
            "Compose asynchronous computations with completion callbacks",
            "src/java.base/share/classes/java/util/concurrent/CompletableFuture.java",
        ),
        (
            "String",
            "Immutable sequence of characters with string manipulation operations",
            "src/java.base/share/classes/java/lang/String.java",
        ),
        (
            "ArrayList",
            "Resizable array implementation of an ordered list",
            "src/java.base/share/classes/java/util/ArrayList.java",
        ),
        (
            "ForkJoinPool",
            "Work stealing executor for fork join tasks",
            "src/java.base/share/classes/java/util/concurrent/ForkJoinPool.java",
        ),
        (
            "Files",
            "Utility methods to read write copy and traverse filesystem paths",
            "src/java.base/share/classes/java/nio/file/Files.java",
        ),
        (
            "Pattern",
            "Compile regular expressions for matching character sequences",
            "src/java.base/share/classes/java/util/regex/Pattern.java",
        ),
        (
            "HttpClient",
            "Send HTTP requests and receive responses synchronously or asynchronously",
            "src/java.net.http/share/classes/java/net/http/HttpClient.java",
        ),
    ],
}
queries = []
for repo, targets in TARGETS.items():
    root = Path(os.environ.get("CODECTX_BENCH_REPOS", Path.home() / "repo")) / repo
    java_files = list(root.rglob("*.java")) if any(t[2] is None for t in targets) else []
    for name, query, rel in targets:
        if rel is None:
            candidates = [
                p for p in java_files if p.name == name + ".java" and "/src/main/" in p.as_posix()
            ]
            assert len(candidates) == 1, (name, candidates)
            rel = candidates[0].relative_to(root).as_posix()
        source = (root / rel).read_text()
        match = re.search(r"\b(?:class|interface|enum|record|@interface)\s+" + name + r"\b", source)
        assert match, (repo, name, rel)
        line = source[: match.start()].count("\n") + 1
        queries.append(
            dict(repo=repo, query=query, name=name, file=rel, line=line, kind="natural_language")
        )
Path(__file__).with_name("queries.json").write_text(json.dumps(queries, indent=2) + "\n")
print(f"Validated {len(queries)} source labels")
