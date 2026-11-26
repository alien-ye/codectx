"""Best-effort Groovy normalization. Never claim complete Groovy parse coverage."""

import re

from . import java


def _normalize(source):
    result, names = [], {}
    for _i, line in enumerate(source.splitlines(keepends=True), 1):
        if line.strip() in {
            x + ":" for x in ("given", "when", "then", "expect", "where", "and", "cleanup")
        }:
            line = "\n"
        match = re.match(r"""(\s*)def\s+(["'])([^"']+)\2\s*\(\s*\)\s*\{""", line)
        if match:
            name = match[3]
            safe = "__spock_" + re.sub(r"[^a-zA-Z0-9_]", "_", name)
            names[safe] = name
            line = f"{match[1]}Object {safe}() {{\n"
        else:
            line = re.sub(r"\bdef\s+(?=[A-Za-z_]\w*\s*\()", "Object ", line)
            if re.match(r"^\s+\w+(?:<[^>]+>)?\s+\w+\s*$", line) and not line.lstrip().startswith(
                ("return ", "throw ")
            ):
                line = line.rstrip() + ";\n"
        stripped = line.strip()
        if stripped in {"true", "false"}:
            line = line[: len(line) - len(line.lstrip())] + "assert " + stripped + ";\n"
        elif stripped.endswith(")") or stripped.startswith(("import ", "package ")):
            line = line.rstrip() + ";\n"
        result.append(line)
    return "".join(result), names


def analyze(source, file_path):
    normalized, names = _normalize(source)
    result, refs = java.analyze(normalized, file_path)

    def restore(qname):
        parent, dot, tail = qname.rpartition(".")
        return parent + dot + names.get(tail, tail)

    offsets = {}
    for s in result.symbols:
        owner = s.qualified_name, s.start_byte
        if s.name in names:
            s.name = names[s.name]
            s.docstring = s.docstring or "Spock spec: " + s.name
        s.qualified_name = restore(s.qualified_name)
        # Normalization preserves lines but changes bytes. Restore original offsets.
        lines = source.encode().splitlines(keepends=True)
        s.start_byte = sum(map(len, lines[: s.start_line - 1]))
        s.end_byte = sum(map(len, lines[: s.end_line]))
        offsets[owner] = s.start_byte
    for ref in refs:
        ref.source_start_byte = offsets.get((ref.source_qualifier, ref.source_start_byte))
        ref.source_qualifier = restore(ref.source_qualifier)
    return result, refs


def extract(source, file_path):
    return analyze(source, file_path)[0]


def extract_refs(source, file_path):
    return analyze(source, file_path)[1]
