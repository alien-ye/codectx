"""Method candidates from explicit receiver types and indexed inheritance."""

from collections import defaultdict

from .store import Store


class MethodResolver:
    def __init__(self, store: Store):
        self.store = store
        self.parents = defaultdict(list)
        self.superclasses = defaultdict(list)
        self.children = defaultdict(list)
        self.cache = {}
        for ref in store.all_refs():
            if ref.kind not in {"extends", "implements", "anonymous_base"}:
                continue
            bases, _ = store.resolve_ref(ref)
            if len(bases) != 1:
                continue
            for child in store.ref_sources(ref):
                if child.kind == "class":
                    self.parents[child.id].append(bases[0].id)
                    self.children[bases[0].id].append(child.id)
                    if ref.kind != "implements":
                        self.superclasses[child.id].append(bases[0].id)

    def _members(self, cid, name):
        cls = self.store.symbol_by_id(cid)
        return self.store.by_file_qname.get((cls.file_path, f"{cls.qualified_name}.{name}"), ())

    def _relatives(self, start, edges, depth=None):
        seen = {start}
        frontier = [start]
        level = 0
        while frontier and (depth is None or level < depth):
            following = []
            for cid in frontier:
                for neighbor in edges.get(cid, ()):
                    if neighbor not in seen:
                        seen.add(neighbor)
                        following.append(neighbor)
                        yield neighbor
            frontier = following
            level += 1

    def overrides(self, method, *, reverse=False, depth=None):
        if not method.parent_id or method.kind != "method" or method.name == "<init>":
            return []
        python = method.file_path.endswith(".py")
        if not python and method.override_signature is None:
            return []
        edges = self.children if reverse else self.parents
        return [
            candidate
            for cid in self._relatives(method.parent_id, edges, depth)
            for candidate in self._members(cid, method.name)
            if candidate.kind == "method"
            and (python or candidate.override_signature == method.override_signature)
        ]

    def _lookup(self, owner, name, arity, is_super):
        key = owner, name, arity, is_super
        if key in self.cache:
            return self.cache[key]
        seen = set()
        roots = self.superclasses.get(owner, ()) if is_super else [owner]
        stack = [(cid, frozenset()) for cid in roots]
        found = {}
        while stack:
            cid, shadowed = stack.pop()
            if (cid, shadowed) in seen:
                continue
            seen.add((cid, shadowed))
            members = [
                s for s in self._members(cid, name) if s.kind == "method" and s.accepts_arity(arity)
            ]
            for s in members:
                if s.override_signature not in shadowed:
                    found[s.id] = s
            if not members or arity is not None:
                hidden = shadowed.union(
                    s.override_signature for s in members if s.override_signature is not None
                )
                stack.extend((parent, hidden) for parent in self.parents.get(cid, ()))
        targets = dict(found)
        signatures = {
            s.override_signature
            for s in found.values()
            if s.file_path.endswith(".py") or s.override_signature is not None
        }
        if signatures and not is_super:
            for cid in self._relatives(owner, self.children):
                for other in self._members(cid, name):
                    if other.kind == "method" and other.override_signature in signatures:
                        targets[other.id] = other
        result = (
            tuple(targets.values()),
            "polymorphic" if targets.keys() != found.keys() else "receiver_match",
        )
        self.cache[key] = result
        return result

    def resolve(self, ref):
        if ref.receiver_type:
            classes = self.store.type_candidates(ref.receiver_type, ref.file_path)
        else:
            classes = [
                self.store.symbol_by_id(s.parent_id)
                for s in self.store.ref_sources(ref)
                if s.kind == "method"
            ]
            classes = [c for c in classes if c and c.kind == "class"]
        if len(classes) != 1:
            return (), "unresolved"
        targets, label = self._lookup(
            classes[0].id, ref.target_name, ref.arity, ref.receiver in {"super", "super()"}
        )
        return targets, label if targets else "unresolved"
