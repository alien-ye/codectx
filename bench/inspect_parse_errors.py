"""Parser diagnostics, not an independent correctness oracle."""

import json
import os
from pathlib import Path

from codectx.index import detect_language
from codectx.languages._util import node_text, parser
from codectx.languages.groovy import _normalize

base = Path(__file__).parent
output = {}
for repo in ["langchain", "django", "spring-boot", "kafka", "jdk21u"]:
    manifest = json.loads((base / "results/indexes" / repo / "manifest.json").read_text())
    records = []
    for key, error in manifest.items():
        if not key.startswith("error:"):
            continue
        rel = key[6:]
        language = detect_language(rel)
        if language == "unknown":
            records.append(dict(file=rel, error=error))
            continue
        source = (
            Path(os.environ.get("CODECTX_BENCH_REPOS", Path.home() / "repo")) / repo / rel
        ).read_text(errors="replace")
        normalized = _normalize(source)[0] if language == "groovy" else source
        data = normalized.encode()
        tree = parser("java" if language == "groovy" else language).parse(data)
        stack, problems = [tree.root_node], []
        while stack and len(problems) < 3:
            node = stack.pop()
            if node.type == "ERROR" or node.is_missing:
                problems.append(
                    dict(
                        line=node.start_point.row + 1,
                        type=node.type,
                        missing=node.is_missing,
                        text=node_text(node, data)[:160],
                    )
                )
            elif node.has_error:
                stack.extend(reversed(node.children))
        records.append(
            dict(
                file=rel,
                language=language,
                error=error,
                diagnostics=problems,
                groovy_text_normalized=language == "groovy",
            )
        )
    output[repo] = records
(base / "results/parse-diagnostics.json").write_text(json.dumps(output, indent=2) + "\n")
for repo, records in output.items():
    print(repo, len(records), "files with parse errors")
    for record in records[:3]:
        print(record["file"], record.get("diagnostics"))
