"""Diffable store. Format 2 adds file-scoped refs and content-keyed vector identities."""

import hashlib
import json
import os
import re
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import asdict, dataclass, fields
from pathlib import Path

import orjson

FORMAT_VERSION = 2
VECTORS_IDS_VERSION = 2


class Record:
    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, value):
        return cls(**{f.name: value[f.name] for f in fields(cls) if f.name in value})


@dataclass(slots=True)
class FileRecord(Record):
    path: str
    lang: str
    content_hash: str
    mtime_ns: int
    size: int
    extraction_version: int = 0


@dataclass(slots=True)
class SymbolRecord(Record):
    file_path: str
    name: str
    qualified_name: str
    kind: str
    start_line: int = 1
    end_line: int = 1
    start_byte: int = 0
    end_byte: int = 0
    signature: str | None = None
    docstring: str | None = None
    parent_id: int | None = None
    parse_ok: bool = True
    id: int = 0
    canonical_name: str | None = None
    arity: int | None = None
    variadic: bool = False
    override_signature: str | None = None

    def accepts_arity(self, arity):
        return (
            arity is None
            or self.arity is None
            or self.arity == arity
            or (self.variadic and arity >= self.arity - 1)
        )


@dataclass(slots=True)
class RefRecord(Record):
    source_qualifier: str
    target_name: str
    kind: str
    line: int | None = None
    column: int | None = None
    resolution_kind: str = "unresolved"
    candidate_count: int = 0
    file_path: str = ""
    source_start_byte: int | None = None
    target_qualified: str | None = None
    receiver: str | None = None
    receiver_type: str | None = None
    arity: int | None = None
    evidence: str | None = None
    alias: str | None = None
    target_kind: str | None = None

    def to_dict(self):
        # Keep the original wire fields, eliding absent semantic hints on large indexes.
        row = {}
        for field in fields(self):
            value = getattr(self, field.name)
            if value is not None or field.name in {"line", "column"}:
                row[field.name] = value
        return row


def atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_bytes(data)
    os.replace(temp, path)


def jsonl(records):
    return b"".join((json.dumps(r.to_dict(), ensure_ascii=False) + "\n").encode() for r in records)


def atomic_records(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with temp.open("wb") as stream:
        for record in records:
            stream.write((json.dumps(record.to_dict(), ensure_ascii=False) + "\n").encode())
    os.replace(temp, path)


def _safe_filename(model_id):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", model_id)


class Store:
    def __init__(self, index_dir, root=None, readonly=False, recover=False, ref_kinds=None):
        self.index_dir = Path(index_dir).resolve()
        self.root = Path(root or self.index_dir.parent).resolve()
        self.readonly = readonly
        self._ref_kinds = frozenset(ref_kinds) if ref_kinds is not None else None
        self._manifest = {}
        self._files = {}
        self._symbols = []
        self._refs = []
        self._next_id = 1
        self._dirty = False
        self._replacements = None
        if self.index_dir.exists() and not recover:
            self._load(use_manifest_root=root is None)
        self._rebuild_maps()

    @classmethod
    def open(cls, root, readonly=False, recover=False):
        return cls(Path(root).resolve() / ".codectx", root, readonly, recover)

    @classmethod
    def open_at(cls, index_dir, readonly=False, recover=False):
        return cls(index_dir, readonly=readonly, recover=recover)

    def _load(self, *, use_manifest_root):
        strings = {}
        pooled_fields = {
            "path",
            "file_path",
            "lang",
            "name",
            "qualified_name",
            "source_qualifier",
            "target_name",
            "kind",
            "resolution_kind",
            "content_hash",
            "receiver",
            "evidence",
            "target_qualified",
        }
        p = self.index_dir / "manifest.json"
        if p.exists():
            self._manifest = json.loads(p.read_bytes())
            if self._manifest.get("format_version") != FORMAT_VERSION:
                raise RuntimeError("Unsupported index format; rebuild using index --force")
            if use_manifest_root:
                self.root = Path(self._manifest.get("root", self.root))
        for name, cls, attr in [
            ("files", FileRecord, "_files"),
            ("symbols", SymbolRecord, "_symbols"),
            ("refs", RefRecord, "_refs"),
        ]:
            p = self.index_dir / f"{name}.jsonl"
            if name == "refs" and self._ref_kinds == frozenset():
                self._refs = []
                continue
            records = []
            if p.exists():
                with p.open("rb") as stream:
                    for line in stream:
                        if line.strip():
                            value = orjson.loads(line)
                            if (
                                name == "refs"
                                and self._ref_kinds is not None
                                and value["kind"] not in self._ref_kinds
                            ):
                                continue
                            for key in pooled_fields.intersection(value):
                                text = value[key]
                                if isinstance(text, str):
                                    value[key] = strings.setdefault(text, text)
                            records.append(cls.from_dict(value))
            setattr(self, attr, {r.path: r for r in records} if name == "files" else records)
        self._next_id = max((s.id for s in self._symbols), default=0) + 1

    def _rebuild_maps(self):
        self._source_files = {s.file_path for s in self._symbols} | {
            r.file_path for r in self._refs
        }
        self._arity_cache = {}
        self._receiver_names = {}
        self._methods = None
        self.by_id = {s.id: s for s in self._symbols}
        self.by_file = defaultdict(list)
        self.by_name = defaultdict(list)
        self.by_qname = defaultdict(list)
        self.by_file_qname = defaultdict(list)
        self.outgoing = defaultdict(list)
        self.incoming = defaultdict(list)
        for s in self._symbols:
            self.by_file[s.file_path].append(s)
            self.by_name[s.name].append(s)
            self.by_qname[s.qualified_name].append(s)
            self.by_file_qname[s.file_path, s.qualified_name].append(s)
        for r in self._refs:
            self.outgoing[r.file_path, r.source_qualifier].append(r)
            self.incoming[r.target_name].append(r)

    def _write_check(self, metadata=False, *, changed=True):
        if self.readonly:
            raise RuntimeError("Store is read-only")
        if self._ref_kinds is not None and not metadata:
            raise RuntimeError("Partial reference views permit vector metadata writes only")
        self._dirty |= changed

    def get_files(self):
        return self._files

    def upsert_file(self, rec):
        self._write_check(changed=self._files.get(rec.path) != rec)
        self._files[rec.path] = rec

    @contextmanager
    def batch_replacements(self):
        """The index scan replaces each discovered file once. Compact the old rows in one pass."""
        symbols, refs = len(self._symbols), len(self._refs)
        self._replacements = set()
        try:
            yield
        finally:
            paths, self._replacements = self._replacements, None
            if paths:
                self._symbols[:symbols] = [
                    s for s in self._symbols[:symbols] if s.file_path not in paths
                ]
                self._refs[:refs] = [r for r in self._refs[:refs] if r.file_path not in paths]

    def clear_file_symbols(self, path):
        self._write_check()
        if path not in self._source_files:
            return
        self._source_files.discard(path)
        self.by_file.pop(path, None)
        if self._replacements is not None:
            self._replacements.add(path)
            return
        self._symbols = [s for s in self._symbols if s.file_path != path]
        self._refs = [r for r in self._refs if r.file_path != path]

    def delete_file(self, path):
        self.clear_file_symbols(path)
        self._files.pop(path, None)
        self._manifest.pop("error:" + path, None)

    def clear(self):
        self._write_check()
        self._files, self._symbols, self._refs = {}, [], []
        self._manifest = {}
        self._next_id = 1
        self._rebuild_maps()

    def add_symbol(self, rec):
        self._write_check()
        rec.id = self._next_id
        self._next_id += 1
        self._symbols.append(rec)
        self.by_file[rec.file_path].append(rec)
        self._source_files.add(rec.file_path)
        return rec.id

    def all_symbols(self):
        return self._symbols

    def symbols_for_file(self, path):
        return sorted(self.by_file.get(path, ()), key=lambda s: s.start_line)

    def symbol_by_id(self, sid):
        return self.by_id.get(sid)

    def symbols_by_name(self, name):
        return self.by_name.get(name, [])

    def add_ref(self, rec):
        self._write_check()
        self._refs.append(rec)
        self._source_files.add(rec.file_path)

    def all_refs(self):
        return self._refs

    def refs_from(self, sid):
        s = self.symbol_by_id(sid)
        if not s:
            return []
        return [
            r
            for r in self.outgoing.get((s.file_path, s.qualified_name), ())
            if r.source_start_byte is None or r.source_start_byte == s.start_byte
        ]

    def ref_sources(self, ref):
        candidates = self.by_file_qname.get((ref.file_path, ref.source_qualifier), ())
        return [
            s
            for s in candidates
            if ref.source_start_byte is None or s.start_byte == ref.source_start_byte
        ]

    @property
    def methods(self):
        if self._methods is None:
            from .dispatch import MethodResolver

            self._methods = MethodResolver(self)
        return self._methods

    def type_candidates(self, name, file):
        python = file.endswith(".py")
        candidates = [
            s
            for s in self.by_name.get(name.rsplit(".", 1)[-1], ())
            if s.kind == "class" and s.file_path.endswith(".py") == python
        ]
        if "." in name:
            return [
                s
                for s in candidates
                if s.canonical_name == name
                or (python and s.canonical_name and s.canonical_name.endswith("." + name))
            ]
        local = [s for s in candidates if s.file_path == file]
        return local or candidates

    def resolve_ref(self, ref):
        if ref.evidence == "dynamic_dispatch":
            return (), "dynamic_dispatch"
        if (
            ref.kind == "calls"
            and ref.file_path.endswith(".py")
            and (ref.receiver_type or "").startswith("builtins.")
        ):
            return (), "builtin_receiver"
        if ref.kind == "calls" and (
            ref.receiver_type or ref.receiver in {"self", "this", "super", "super()"}
        ):
            return self.methods.resolve(ref)
        candidates = self.by_name.get(ref.target_name, ())
        if ref.target_qualified:
            name = ref.target_qualified
            python = ref.file_path.endswith(".py")
            candidates = [
                s
                for s in candidates
                if s.canonical_name
                and s.file_path.endswith(".py") == python
                and (s.canonical_name == name or (python and s.canonical_name.endswith("." + name)))
            ]
        if ref.kind in {"extends", "implements", "anonymous_base"}:
            candidates = [
                s
                for s in candidates
                if s.kind == "class"
                and s.file_path.endswith(".py") == ref.file_path.endswith(".py")
            ]
            if ref.file_path.endswith(".py") and not ref.target_qualified:
                prefix = ref.source_qualifier.rpartition(".")[0]
                while True:
                    qname = prefix + "." + ref.target_name if prefix else ref.target_name
                    local = [
                        s
                        for s in self.by_file_qname.get((ref.file_path, qname), ())
                        if s.kind == "class" and (ref.line is None or s.start_line < ref.line)
                    ]
                    if local:
                        return local, "scope_match" if len(local) == 1 else "name_match"
                    if not prefix:
                        break
                    prefix = prefix.rpartition(".")[0]
        if (
            ref.receiver
            and ref.kind == "calls"
            and not ref.target_qualified
            and ref.file_path.endswith(".py")
        ):
            if ref.target_name not in self._receiver_names:
                self._receiver_names[ref.target_name] = [
                    s for s in candidates if s.kind == "method" and s.file_path.endswith(".py")
                ]
            methods = self._receiver_names[ref.target_name]
            return methods, "name_match" if methods else "unresolved"
        if ref.arity is not None:
            key = (ref.target_name, ref.arity)
            if key not in self._arity_cache:
                self._arity_cache[key] = [
                    s
                    for s in self.by_name.get(ref.target_name, ())
                    if s.kind == "method"
                    and not s.file_path.endswith(".py")
                    and s.accepts_arity(ref.arity)
                ]
            candidates = self._arity_cache[key]
        if ref.evidence and not ref.target_qualified:
            candidates = [
                s
                for s in candidates
                if s.file_path.endswith(".py") == ref.file_path.endswith(".py")
            ]
        if ref.target_kind:
            candidates = [s for s in candidates if s.kind == ref.target_kind]
        if ref.evidence == "reflective":
            return candidates, "reflective"
        if not candidates:
            return (), "unresolved"
        if len(candidates) > 1:
            return candidates, "name_match"
        if ref.target_qualified:
            return candidates, "qualified"
        if ref.arity is not None:
            return candidates, "arity_match"
        return candidates, "exact" if len(self.by_name[ref.target_name]) == 1 else "name_match"

    def refs_to_name(self, name):
        return self.incoming.get(name, [])

    def get_meta(self, name, default=None):
        return self._manifest.get(name, default)

    def set_meta(self, name, value):
        changed = name not in self._manifest or self._manifest[name] != value
        self._write_check(metadata=name.startswith("vector_"), changed=changed)
        self._manifest[name] = value

    def commit(self):
        if self.readonly:
            raise RuntimeError("Store is read-only")
        if not self._dirty:
            return
        if self._ref_kinds is not None:
            atomic(self.index_dir / "manifest.json", json.dumps(self._manifest, indent=2).encode())
            self._dirty = False
            return
        self._symbols.sort(key=lambda s: (s.file_path, s.start_line, s.start_byte))
        for i, s in enumerate(self._symbols, 1):
            s.id = i
        self._rebuild_maps()
        for s in self._symbols:
            parent = self.by_file_qname.get((s.file_path, s.qualified_name.rpartition(".")[0]), [])
            s.parent_id = parent[0].id if len(parent) == 1 else None
        for r in self._refs:
            candidates, r.resolution_kind = self.resolve_ref(r)
            r.candidate_count = len(candidates)
        self._refs.sort(
            key=lambda r: (r.file_path, r.line or 0, r.source_qualifier, r.kind, r.target_name)
        )
        self._manifest.update(
            format_version=FORMAT_VERSION,
            root=str(self.root),
            indexed_at=time.time_ns(),
            file_count=len(self._files),
            symbol_count=len(self._symbols),
            ref_count=len(self._refs),
        )
        for name, records in [
            ("files", sorted(self._files.values(), key=lambda r: r.path)),
            ("symbols", self._symbols),
            ("refs", self._refs),
        ]:
            atomic_records(self.index_dir / f"{name}.jsonl", records)
        atomic(self.index_dir / "manifest.json", json.dumps(self._manifest, indent=2).encode())
        self._next_id = len(self._symbols) + 1
        self._dirty = False

    def vector_key(self, s):
        return (s.file_path, s.qualified_name, s.start_byte, self._files[s.file_path].content_hash)

    def set_vectors(self, ids, matrix, model_id):
        import numpy as np

        self._write_check(metadata=True)
        vector_dir = self.index_dir / "vectors"
        vector_dir.mkdir(parents=True, exist_ok=True)
        matrix = np.asarray(matrix, dtype=np.float32)
        if len(ids) != len(matrix):
            raise ValueError("Vector row count mismatch")
        path = vector_dir / (_safe_filename(model_id) + ".npy")
        with path.with_suffix(".tmp").open("wb") as f:
            np.save(f, matrix, allow_pickle=False)
        ids_path = vector_dir / "ids.jsonl"
        temp = ids_path.with_suffix(".tmp")
        with temp.open("wb") as stream:
            for i, sid in enumerate(ids):
                s = self.symbol_by_id(sid)
                if s is None:
                    raise ValueError(f"Unknown symbol id {sid}")
                row = dict(
                    v=2,
                    row=i,
                    file_path=s.file_path,
                    qualified_name=s.qualified_name,
                    start_byte=s.start_byte,
                    content_hash=self._files[s.file_path].content_hash,
                )
                stream.write((json.dumps(row) + "\n").encode())
        os.replace(path.with_suffix(".tmp"), path)
        os.replace(temp, ids_path)
        self._manifest.update(
            vector_model_id=model_id, vector_dim=matrix.shape[1], vector_count=len(ids)
        )

    def get_vectors(self):
        import numpy as np

        model = self.get_meta("vector_model_id")
        if not model:
            return None
        path = self.index_dir / "vectors"
        matrix_path = path / (_safe_filename(model) + ".npy")
        if not (path / "ids.jsonl").exists() or not matrix_path.exists():
            return None
        matrix = np.load(matrix_path, allow_pickle=False, mmap_mode="r")
        ids, rows = [], []
        with (path / "ids.jsonl").open("rb") as stream:
            for line in stream:
                r = orjson.loads(line)
                if r.get("v") != 2:
                    return None
                file = self._files.get(r["file_path"])
                if file is None or file.content_hash != r.get("content_hash"):
                    continue
                candidates = self.by_file_qname.get((r["file_path"], r["qualified_name"]), ())
                s = next((s for s in candidates if s.start_byte == r.get("start_byte")), None)
                if s and 0 <= r["row"] < len(matrix):
                    ids.append(s.id)
                    rows.append(r["row"])
        if not ids:
            return None
        if len(rows) == len(matrix) and all(i == row for i, row in enumerate(rows)):
            return ids, matrix, model
        return ids, matrix[rows], model

    def fingerprint(self):
        digest = hashlib.sha256()
        for symbol in self._symbols:
            digest.update(jsonl([symbol]))
        return digest.hexdigest()

    def stats(self):
        return dict(
            files_total=len(self._files),
            files_by_language=dict(Counter(r.lang for r in self._files.values())),
            symbols_total=len(self._symbols),
            refs_total=self._manifest.get("ref_count", len(self._refs))
            if self._ref_kinds is not None
            else len(self._refs),
            index=str(self.index_dir),
        )

    def close(self):
        pass

    def is_empty(self):
        return not self._files
