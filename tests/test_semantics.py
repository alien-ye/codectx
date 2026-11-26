import json

import pytest

from codectx import graph
from codectx.cli import main
from codectx.context import build_context
from codectx.index import index_files
from codectx.store import Store


def make_store(root, files):
    for name, source in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    index_files(Store.open(root), root)
    return Store.open(root, readonly=True)


def targets(store, operation, name):
    sid = graph.resolve_symbol(store, name).id
    return {
        (h.target.file_path, h.target.qualified_name, h.ref.resolution_kind)
        for h in operation(store, sid)
        if h.target
    }


def test_python_inheritance_dispatch_and_reflection(tmp_path):
    store = make_store(
        tmp_path,
        {
            "src/pkg/base.py": "class Repo:\n    def save(self): pass\nclass Meta(type): pass\n",
            "other.py": "class Repo:\n    def save(self): pass\n",
            "src/pkg/app.py": """from .base import Repo as R, Meta
from importlib import import_module as load
class Db(R, metaclass=Meta):
    @property
    def save(self): return super().save()
def run(svc: R, attr):
    svc.save()
    getattr(svc, "save")
    getattr(svc, attr)
    load("pkg.plugin")
""",
        },
    )
    assert targets(store, graph.supertypes, "Db") == {("src/pkg/base.py", "Repo", "qualified")}
    assert not targets(store, graph.subtypes, "other.py::Repo")
    assert targets(store, graph.overrides, "Db.save") == {
        ("src/pkg/base.py", "Repo.save", "override_candidate")
    }
    assert targets(store, graph.overridden_by, "src/pkg/base.py::Repo.save") == {
        ("src/pkg/app.py", "Db.save", "override_candidate")
    }
    assert ("src/pkg/base.py", "Repo.save", "receiver_match") in targets(
        store, graph.callees, "Db.save"
    )
    hits = graph.callees(store, graph.resolve_symbol(store, "run").id)
    assert {h.target.qualified_name for h in hits if h.ref.resolution_kind == "polymorphic"} == {
        "Repo.save",
        "Db.save",
    }
    assert not any(
        h.target and h.target.file_path == "other.py" and h.ref.kind == "calls" for h in hits
    )
    assert ("src/pkg/app.py", "run", "polymorphic") in targets(store, graph.callers, "Db.save")
    assert any(h.ref.evidence == "dynamic_dispatch" and h.target is None for h in hits)
    assert any(h.ref.kind == "references" and h.ref.resolution_kind == "reflective" for h in hits)
    assert any(h.ref.kind == "imports" and h.ref.target_name == "pkg.plugin" for h in hits)
    assert {("Repo", "R"), ("Meta", "Meta")} <= {
        (r.target_name, r.alias) for r in store.all_refs() if r.kind == "imports"
    }
    assert any(r.evidence == "metaclass" and r.target_name == "Meta" for r in store.all_refs())
    assert any(
        r.evidence == "decorator" and r.source_qualifier == "Db.save" for r in store.all_refs()
    )
    assert "dynamic_dispatch at src/pkg/app.py:9" in build_context(store, "run", k=1).text


def test_java_overloads_receiver_scope_and_reverse(tmp_path, capsys):
    store = make_store(
        tmp_path,
        {
            "api/Repo.java": "package api; public interface Repo { void save(int x); }",
            "other/Repo.java": "package other; public interface Repo { void save(int x); }",
            "app/Db.java": """package app;
import api.Repo;
class Db implements Repo {
  @Override public void save(int x) { log(x); }
  public void save(String x) { record(x); }
  void log(int x) {}
  void record(String x) {}
  void route(Repo r) { r.save(1); }
  void parse() { log(0); }
  void parse(int x) { record("x"); }
  void use() { parse(); }
}""",
        },
    )
    assert targets(store, graph.supertypes, "Db") == {("api/Repo.java", "Repo", "qualified")}
    assert not targets(store, graph.subtypes, "other/Repo.java::Repo")
    assert targets(store, graph.callees, "Db.parse/0") == {("app/Db.java", "Db.log", "arity_match")}
    assert targets(store, graph.callees, "Db.parse/1") == {
        ("app/Db.java", "Db.record", "arity_match")
    }
    assert targets(store, graph.callers, "Db.parse/0") == {("app/Db.java", "Db.use", "arity_match")}
    assert not targets(store, graph.callers, "Db.parse/1")
    with pytest.raises(ValueError, match="Ambiguous"):
        graph.resolve_symbol(store, "Db.save/1")
    assert targets(store, graph.callees, "Db.route") == {
        ("api/Repo.java", "Repo.save", "polymorphic"),
        ("app/Db.java", "Db.save", "polymorphic"),
    }
    base = graph.resolve_symbol(store, "api/Repo.java::Repo.save")
    assert [h.target.start_line for h in graph.overridden_by(store, base.id)] == [4]
    assert targets(store, graph.callers, "Db.save@4") == {
        ("app/Db.java", "Db.route", "polymorphic")
    }
    assert not targets(store, graph.callers, "Db.save@5")
    assert main(["graph", "api/Repo.java::Repo.save", str(tmp_path), "--overridden-by"]) == 0
    assert "Db.java:4 Db.save [override_candidate" in capsys.readouterr().out


def test_java_reflection_and_anonymous_class(tmp_path):
    store = make_store(
        tmp_path,
        {
            "Example.java": """package p;
interface Work { void run(); }
class Driver {}
class Example {
  Object make(String key) throws Exception {
    Class.forName("p.Driver");
    Class.forName(key);
    Driver.class.getDeclaredMethod("start");
    return new Work() { public void run() { inner(); } };
  }
  void inner() {}
}"""
        },
    )
    make = graph.resolve_symbol(store, "Example.make")
    hops = graph.callees(store, make.id)
    assert any(
        h.target and h.target.name == "Driver" and h.ref.resolution_kind == "reflective"
        for h in hops
    )
    assert any(
        h.target is None and h.ref.resolution_kind == "dynamic_dispatch" and h.ref.line == 7
        for h in hops
    )
    assert any(h.ref.target_name == "start" and h.ref.evidence == "reflective" for h in hops)
    assert not any(h.ref.target_name == "inner" for h in hops)
    anon = graph.subtypes(store, graph.resolve_symbol(store, "Work").id)[0].target
    assert anon.name.startswith("<anonymous@")
    method = graph.resolve_symbol(store, anon.qualified_name + ".run")
    assert any(h.target and h.target.name == "inner" for h in graph.callees(store, method.id))


def test_upgrade_old_records_then_noop(tmp_path):
    root = tmp_path
    db = root / ".codectx"
    old = make_store(
        root, {"a.py": 'def f(x): return getattr(x, "member")\n', "b.py": "def g(): pass\n"}
    )
    for filename, drop in [
        ("files", {"extraction_version"}),
        ("symbols", {"canonical_name", "arity", "variadic", "override_signature"}),
    ]:
        path = db / f"{filename}.jsonl"
        rows = [json.loads(line) for line in path.read_bytes().splitlines()]
        for row in rows:
            for key in drop:
                row.pop(key)
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    (db / "refs.jsonl").write_text(
        json.dumps(
            {
                "source_qualifier": "f",
                "target_name": "getattr",
                "kind": "calls",
                "line": 1,
                "file_path": "a.py",
            }
        )
        + "\n"
    )
    assert len(Store.open(root).all_refs()) == 1
    assert index_files(Store.open(root), root).reindexed == 2
    new = Store.open(root)
    assert len(new.all_symbols()) == len(old.all_symbols())
    assert len(new.all_refs()) == 2
    assert any(r.evidence == "reflective" for r in new.all_refs())
    before = {p: p.stat().st_mtime_ns for p in db.iterdir()}
    assert index_files(new, root).unchanged == 2
    assert before == {p: p.stat().st_mtime_ns for p in db.iterdir()}


def test_local_and_field_receivers(tmp_path):
    store = make_store(
        tmp_path,
        {
            "Types.java": """interface Sink { void write(); }
class Impl implements Sink { public void write() {} }
class Other { public void write() {} }
class Runner {
  Sink sink;
  void fromField() { this.sink.write(); }
  void fromLocal() { var local = new Impl(); local.write(); }
}""",
            "types.py": """class Client:
    def send(self): pass
class Noise:
    def send(self): pass
def annotated():
    instance: Client = build()
    instance.send()
def constructed():
    instance = Client()
    instance.send()
def unknown(obj):
    return obj.lower()
def lower(): pass
""",
        },
    )
    assert {
        q
        for _, q, label in targets(store, graph.callees, "Runner.fromField")
        if label == "polymorphic"
    } == {"Sink.write", "Impl.write"}
    assert {
        q
        for _, q, label in targets(store, graph.callees, "Runner.fromLocal")
        if label == "receiver_match"
    } == {"Impl.write"}
    for caller in ("annotated", "constructed"):
        assert {
            q for _, q, label in targets(store, graph.callees, caller) if label == "receiver_match"
        } == {"Client.send"}
    assert not targets(store, graph.callees, "unknown")


def test_java_varargs_and_same_line_source_selectors(tmp_path):
    store = make_store(
        tmp_path,
        {
            "C.java": """class C {
  void log(String... xs) {}
  void parse(int x) { log(); } void parse(String x) { log("one","two"); }
  void use() { parse(1); }
}"""
        },
    )
    with pytest.raises(ValueError, match="Ambiguous") as error:
        graph.resolve_symbol(store, "C.parse/1")
    for selector in str(error.value).partition(": ")[2].split(", "):
        method = graph.resolve_symbol(store, selector)
        calls = graph.callees(store, method.id)
        assert len(calls) == 1 and calls[0].target.name == "log"
        assert calls[0].ref.arity == (0 if "int" in method.signature else 2)
    assert len(graph.callees(store, graph.resolve_symbol(store, "C.use").id)) == 2


def test_instance_fields_across_methods(tmp_path):
    store = make_store(
        tmp_path,
        {
            "backend.py": "class Store:\n    def lookup(self): pass\n",
            "client.py": """from backend import Store as Backend
class Noise:
    def lookup(self): pass
class Client:
    def use(obj):
        obj.injected.lookup()
        obj.created.lookup()
        obj.declared.lookup()
        obj.annotated.lookup()
    declared: Backend
    def __init__(self, store: "Backend"):
        self.injected = store
        self.created = Backend()
        self.annotated: Backend
    def rebound(self, unknown):
        self.created = unknown
        self.created.lookup()
    @staticmethod
    def static(self): self.created.lookup()
    @classmethod
    def class_method(self): self.created.lookup()
    class Nested:
        def use(self): self.created.lookup()
""",
        },
    )
    hits = graph.callees(store, graph.resolve_symbol(store, "Client.use").id)
    assert {
        (h.ref.receiver, h.ref.receiver_type, h.target.qualified_name, h.ref.resolution_kind)
        for h in hits
    } == {
        (f"obj.{field}", "backend.Store", "Store.lookup", "receiver_match")
        for field in ("injected", "created", "declared", "annotated")
    }
    for method in ("Client.rebound", "Client.static", "Client.class_method", "Client.Nested.use"):
        calls = [
            h
            for h in graph.callees(store, graph.resolve_symbol(store, method).id)
            if h.ref.kind == "calls"
        ]
        assert calls and all(
            h.ref.receiver_type is None and h.ref.resolution_kind == "name_match" for h in calls
        )
    assert ("client.py", "Client.use", "receiver_match") in targets(
        store, graph.callers, "Store.lookup"
    )
    assert not any(
        name == "Client.use" for _, name, _ in targets(store, graph.callers, "Noise.lookup")
    )


def test_container_receivers_keep_unknown_and_custom_matches(tmp_path):
    store = make_store(
        tmp_path,
        {
            "containers.py": """class Custom:
    def update(self): pass
    def sort(self): pass
class Job:
    def __init__(self):
        self.cache = {}
        self.items = list()
    def work(self, unknown):
        self.cache.update()
        self.items.sort()
        scratch = dict()
        scratch.update()
        [].sort()
        unknown.update()
def shadow(dict):
    scratch = dict()
    scratch.update()
def custom():
    import builtins
    scratch = Custom()
    scratch.update()
    builtins.dict().update()
"""
        },
    )
    hits = graph.callees(store, graph.resolve_symbol(store, "Job.work").id)
    assert {
        (h.ref.receiver, h.ref.receiver_type)
        for h in hits
        if h.ref.resolution_kind == "builtin_receiver" and h.target is None
    } == {
        ("self.cache", "builtins.dict"),
        ("self.items", "builtins.list"),
        ("scratch", "builtins.dict"),
        ("[]", "builtins.list"),
    }
    assert any(
        h.target and h.target.qualified_name == "Custom.update" and h.ref.receiver == "unknown"
        for h in hits
    )
    callers = graph.callers(store, graph.resolve_symbol(store, "Custom.update").id)
    assert {(h.target.qualified_name, h.ref.receiver, h.ref.resolution_kind) for h in callers} == {
        ("Job.work", "unknown", "name_match"),
        ("shadow", "scratch", "name_match"),
        ("custom", "scratch", "receiver_match"),
    }
    assert not graph.callers(store, graph.resolve_symbol(store, "Custom.sort").id)
