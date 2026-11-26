import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from . import graph
from .hybrid import search_hybrid

CHARS_PER_TOKEN = 4
DEFAULT_TOKEN_BUDGET = 8000
DEFAULT_GRAPH_DEPTH = 1
MAX_SNIPPET_LINES = 60


@dataclass(slots=True)
class PackedSymbol:
    symbol: object
    source: str
    via_edge_kind: str | None = None
    score: float = 0


@dataclass(slots=True)
class ContextPack:
    text: str
    symbol_count: int
    token_estimate: int
    truncated: bool
    sources: dict


def _render_symbol(p, root, store):
    s = p.symbol
    lines = [f"## {s.qualified_name}  ({s.kind})  {s.file_path}:{s.start_line}"]
    if s.signature:
        lines.append("signature: " + s.signature)
    if s.docstring:
        lines.append("doc: " + s.docstring)
    for ref in store.refs_from(s.id):
        if ref.evidence == "dynamic_dispatch":
            lines.append(f"[dynamic_dispatch at {ref.file_path}:{ref.line} via {ref.target_name}]")
    if root:
        path = (Path(root) / s.file_path).resolve()
        if path.is_relative_to(Path(root).resolve()):
            try:
                source = path.read_text(errors="replace").splitlines()[
                    s.start_line - 1 : s.end_line
                ]
                lines.extend(["```", *source[:MAX_SNIPPET_LINES]])
                if len(source) > MAX_SNIPPET_LINES:
                    lines.append(
                        f"    // ... ({len(source) - MAX_SNIPPET_LINES} more lines truncated)"
                    )
                lines.append("```")
            except OSError:
                pass
    if p.source != "search":
        lines.append(f"[via {p.source}, {p.via_edge_kind}]")
    return "\n".join(lines) + "\n\n"


def build_context(store, query, *, root=None, token_budget=8000, graph_depth=1, k=10):
    if token_budget < 1 or graph_depth < 0:
        raise ValueError("Token budget must be positive and depth nonnegative")
    seeds = [
        PackedSymbol(store.symbol_by_id(h.symbol_id), "search", score=h.score)
        for h in search_hybrid(store, query, k)
    ]
    seeds = [p for p in seeds if p.symbol and p.symbol.parse_ok]
    if not seeds:
        return ContextPack("", 0, 0, False, {})
    packed = list(seeds)
    seen = {p.symbol.id for p in seeds}
    for seed in seeds:
        operations = [
            ("caller", graph.callers, graph_depth),
            ("callee", graph.callees, graph_depth),
        ]
        if seed.symbol.kind == "class" and graph_depth:
            operations += [("subtype", graph.subtypes, 10), ("supertype", graph.supertypes, 10)]
        for source, fn, depth in operations:
            for hop in fn(store, seed.symbol.id, depth):
                if hop.target and hop.target.parse_ok and hop.target.id not in seen:
                    seen.add(hop.target.id)
                    packed.append(PackedSymbol(hop.target, source, hop.ref.resolution_kind))
    ranks = {"search": 0, "subtype": 1, "supertype": 2, "caller": 3, "callee": 4}
    packed.sort(key=lambda p: (ranks[p.source], -p.score))
    budget = token_budget * 4
    header = f"# Context for: {query}\n\n"
    text = header[:budget]
    counts = Counter()
    truncated = len(header) > budget
    for p in packed:
        block = _render_symbol(p, root, store)
        if len(text) + len(block) > budget:
            truncated = True
            continue  # A huge first symbol must not hide smaller useful ones.
        text += block
        counts[p.source] += 1
    if not counts:
        text = (header + "[truncated: no symbol fits the context budget]\n")[:budget]
    return ContextPack(
        text, sum(counts.values()), math.ceil(len(text) / 4), truncated, dict(counts)
    )
