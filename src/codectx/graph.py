import re
from dataclasses import dataclass, replace

from .store import RefRecord

EDGE_KINDS = {"calls", "imports", "references", "extends", "implements", "anonymous_base"}
_CALL_KINDS = {"calls", "imports", "references"}
_INHERITANCE_KINDS = {"extends", "implements", "anonymous_base"}


@dataclass(frozen=True, slots=True)
class GraphHop:
    ref: RefRecord
    target: object | None


def persist_refs(store, refs, file_path=""):
    for r in refs:
        store.add_ref(replace(r, file_path=file_path))


def _traverse(store, sid, depth, reverse, kinds):
    frontier = [sid]
    visited = {sid}
    result, emitted = [], set()
    for _ in range(depth):
        next_frontier = []
        for current in frontier:
            s = store.symbol_by_id(current)
            if not s:
                continue
            refs = store.refs_to_name(s.name) if reverse else store.refs_from(current)
            for ref in refs:
                if ref.kind not in kinds:
                    continue
                candidates, provenance = store.resolve_ref(ref)
                if reverse and not any(target.id == current for target in candidates):
                    continue
                live = replace(ref, candidate_count=len(candidates), resolution_kind=provenance)
                targets = store.ref_sources(ref) if reverse else candidates
                for target in targets or [None]:
                    key = (current, id(ref), target.id if target else None)
                    if key in emitted:
                        continue
                    emitted.add(key)
                    result.append(GraphHop(live, target))
                    if target and target.id not in visited:
                        visited.add(target.id)
                        next_frontier.append(target.id)
        frontier = next_frontier
        if not frontier:
            break
    return result


def callers(store, sid, depth=1):
    return _traverse(store, sid, depth, True, _CALL_KINDS)


def callees(store, sid, depth=1):
    return _traverse(store, sid, depth, False, _CALL_KINDS)


def supertypes(store, sid, depth=10):
    s = store.symbol_by_id(sid)
    return (
        _traverse(store, sid, depth, False, _INHERITANCE_KINDS) if s and s.kind == "class" else []
    )


def subtypes(store, sid, depth=10):
    s = store.symbol_by_id(sid)
    return _traverse(store, sid, depth, True, _INHERITANCE_KINDS) if s and s.kind == "class" else []


def _overrides(store, sid, depth, reverse):
    method = store.symbol_by_id(sid)
    if not method:
        return []
    candidates = store.methods.overrides(method, reverse=reverse, depth=depth)
    hops = []
    for other in candidates:
        child, base = (other, method) if reverse else (method, other)
        ref = RefRecord(
            child.qualified_name,
            base.name,
            "overrides",
            child.start_line,
            resolution_kind="override_candidate",
            candidate_count=len(candidates),
            file_path=child.file_path,
            source_start_byte=child.start_byte,
        )
        hops.append(GraphHop(ref, other))
    return hops


def overrides(store, sid, depth=1):
    return _overrides(store, sid, depth, False)


def overridden_by(store, sid, depth=1):
    return _overrides(store, sid, depth, True)


def resolve_symbol(store, name):
    # Optional file::qualified_name disambiguation.
    file, sep, qname = name.partition("::")
    selector = qname if sep else name
    match = re.fullmatch(r"(.+?)(?:/(\d+))?(?:@(\d+)(?::(\d+))?)?", selector)
    arity = line = offset = None
    if match:
        selector, arity, line, offset = match.groups()
    matches = (
        store.by_file_qname.get((file, selector), [])
        if sep
        else store.by_qname.get(selector, []) or store.symbols_by_name(selector)
    )
    matches = [
        s
        for s in matches
        if (arity is None or s.arity == int(arity))
        and (line is None or s.start_line == int(line))
        and (offset is None or s.start_byte == int(offset))
    ]
    if len(matches) != 1:
        choices = ", ".join(
            f"{s.file_path}::{s.qualified_name}@{s.start_line}:{s.start_byte}" for s in matches[:10]
        )
        raise ValueError(
            f"Ambiguous symbol {name}: {choices}" if matches else f"Symbol not found: {name}"
        )
    return matches[0]
