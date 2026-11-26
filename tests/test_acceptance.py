import shutil
import subprocess
import sys

import pytest

from codectx import graph
from codectx.cli import main
from codectx.context import build_context
from codectx.doctor import diagnose
from codectx.index import index_files
from codectx.search import search_lexical
from codectx.store import Store


@pytest.fixture
def repo(tmp_path):
    (tmp_path / ".gitignore").write_text("ignored/\nsecret.env\n")
    (tmp_path / "ignored").mkdir()
    (tmp_path / "ignored" / "hidden.py").write_text("def hidden(): pass")
    (tmp_path / "secret.env").write_text("secret")
    (tmp_path / "a.py").write_text('''import os
X = 1
class Base:
    """User controller base."""
    def handle(self):
        return helper()
class Child(Base):
    async def create_user(self, user: str) -> str:
        """Create an account."""
        return helper()
def helper():
    return 42
def main():
    return helper()
''')
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    store = Store.open(tmp_path)
    index_files(store, tmp_path)
    return tmp_path, store


def test_discovery_and_incremental(repo):
    root, store = repo
    assert "secret.env" not in store.get_files()
    assert not any("hidden" in s.name for s in store.all_symbols())
    before = {
        name: (store.index_dir / name).read_bytes()
        for name in ["files.jsonl", "symbols.jsonl", "refs.jsonl"]
    }
    result = index_files(store, root)
    assert result.indexed_files == result.reindexed == 0
    assert all((store.index_dir / name).read_bytes() == data for name, data in before.items())
    (root / "a.py").write_text("import sys\ndef main(): return 1\n")
    result = index_files(store, root)
    assert result.reindexed == 1
    assert [r.target_name for r in store.all_refs()] == ["sys"]
    assert store.symbols_by_name("helper") == []
    (root / "a.py").unlink()
    assert index_files(store, root).deleted == 1
    assert not store.all_symbols() and not store.all_refs()


def test_file_scoped_collisions(repo):
    root, store = repo
    (root / "b.py").write_text("def main(): other()\ndef other(): pass\n")
    index_files(store, root)
    with pytest.raises(ValueError, match="Ambiguous"):
        graph.resolve_symbol(store, "main")
    main_a = graph.resolve_symbol(store, "a.py::main")
    assert {h.target.name for h in graph.callees(store, main_a.id) if h.target} == {"helper"}
    (root / "a.py").write_text("def main(): pass\n")
    index_files(store, root)
    main_b = graph.resolve_symbol(store, "b.py::main")
    assert {h.target.name for h in graph.callees(store, main_b.id) if h.target} == {"other"}


def test_graph_and_search(repo):
    root, store = repo
    loaded = Store.open(root)
    assert [s.to_dict() for s in loaded.all_symbols()] == [s.to_dict() for s in store.all_symbols()]
    assert all(r.file_path is loaded.get_files()[r.file_path].path for r in loaded.all_refs())
    main_sym = graph.resolve_symbol(store, "main")
    helper = graph.resolve_symbol(store, "helper")
    assert "helper" in [h.target.name for h in graph.callees(store, main_sym.id) if h.target]
    assert "main" in [h.target.name for h in graph.callers(store, helper.id) if h.target]
    base, child = graph.resolve_symbol(store, "Base"), graph.resolve_symbol(store, "Child")
    assert graph.subtypes(store, base.id)[0].target.id == child.id
    assert graph.supertypes(store, child.id)[0].target.id == base.id
    assert not any(h.ref.kind == "extends" for h in graph.callees(store, child.id))
    assert store.symbol_by_id(search_lexical(store, "user controller")[0].symbol_id).name == "Base"
    assert store.symbols_by_name("X")


def test_errors_recovery_and_readonly(repo):
    root, store = repo
    (root / "broken.py").write_text("def broken(")
    index_files(store, root)
    assert store.get_meta("error:broken.py")
    assert not store.symbols_for_file("broken.py")[0].parse_ok
    readonly = Store.open(root, readonly=True)
    with pytest.raises(RuntimeError):
        readonly.commit()
    (store.index_dir / "symbols.jsonl").write_text("corrupt\n")
    assert any(not c.ok for c in diagnose(root).checks if c.name.startswith("index_"))
    assert main(["index", str(root), "--force"]) == 0
    assert Store.open(root).symbols_by_name("main")


def test_context_budget(repo):
    root, store = repo
    pack = build_context(store, "helper", root=root, token_budget=1000)
    assert "a.py:" in pack.text and pack.symbol_count
    assert "[via caller, exact]" in pack.text
    for tokens in [1, 5, 50, 200]:
        pack = build_context(store, "helper", root=root, token_budget=tokens)
        assert len(pack.text) <= tokens * 4
        assert pack.token_estimate <= tokens


def test_java_and_groovy(tmp_path):
    from codectx.languages import groovy, java

    src = """/** A service. */
class Child extends Base<String> implements Runnable {
  int count;
  Child() { run(); }
  public void run() { work(); }
}
interface More extends Runnable, Other {}
record Person(String name) {}
"""
    result, refs = java.analyze(src, "Service.java")
    assert result.parse_ok
    assert {"Child", "count", "<init>", "run", "More", "Person"} <= {s.name for s in result.symbols}
    assert {
        ("extends", "Base"),
        ("implements", "Runnable"),
        ("extends", "Other"),
        ("calls", "work"),
    } <= {(r.kind, r.target_name) for r in refs}
    src = """class ServiceSpec extends Specification {
    def "works correctly"() {
        when:
        service.work()
        then:
        true
    }
}
"""
    result, refs = groovy.analyze(src, "ServiceSpec.groovy")
    assert "works correctly" in {s.name for s in result.symbols}
    assert any(
        r.source_qualifier == "ServiceSpec.works correctly" and r.target_name == "work"
        for r in refs
    )


def test_vectors_stale_and_renumber(repo):
    import numpy as np

    root, store = repo
    ids = [s.id for s in store.all_symbols()]
    store.set_vectors(ids, np.eye(len(ids), dtype=np.float32), "test")
    store.commit()
    old_keys = {store.vector_key(store.symbol_by_id(i)) for i in ids}
    (root / "0.py").write_text("def aaa(): pass\n")
    index_files(store, root)
    got, matrix, model = store.get_vectors()
    assert model == "test" and len(got) == len(ids)
    assert {store.vector_key(store.symbol_by_id(i)) for i in got} == old_keys
    assert np.array_equal(matrix, np.eye(len(ids)))
    (root / "a.py").write_text("def main(): return 999\n")
    index_files(store, root)
    assert store.get_vectors() is None


def test_lexical_graph_lazy_imports(repo):
    root, _ = repo
    code = """import sys
from codectx.store import Store
from codectx.search import search_lexical
from codectx.graph import callers
s=Store.open(sys.argv[1], readonly=True)
search_lexical(s,'helper')
callers(s,1)
assert 'numpy' not in sys.modules
assert 'model2vec' not in sys.modules
"""
    subprocess.run([sys.executable, "-c", code, str(root)], check=True)


def test_tokens_bm25():
    from codectx.bm25 import BM25Index
    from codectx.tokens import split_identifier

    assert split_identifier("XMLParser") == ["xmlparser", "xml", "parser"]
    assert split_identifier("get_user") == ["get_user", "get", "user"]
    index = BM25Index.build([["user", "user"], ["other"]])
    assert index.search(["user"])[0][0] == 0
    assert index.search(["absent"]) == []
    assert 0 < index.idf("user") < 1


@pytest.mark.skipif(not shutil.which("rg"), reason="coverage uses ripgrep")
def test_rg_coverage(repo):
    from codectx.rg_tools import differential_coverage, rg_search

    root, store = repo
    assert rg_search(root, "def helper")
    assert not differential_coverage(store, root, 100)
    store._symbols = [s for s in store._symbols if s.name != "helper"]
    assert any(g.name == "helper" for g in differential_coverage(store, root, 100))


def test_semantic_and_fusion(repo, monkeypatch):
    from codectx.hybrid import HybridSearcher
    from codectx.semantic import SemanticSearcher, embed_symbols

    root, store = repo
    assert SemanticSearcher(store).search("account") == []
    embed_symbols(store, [s for s in store.all_symbols() if s.parse_ok])
    store.commit()
    hits = HybridSearcher(store).search("create user account")
    assert any(h.lexical_rank is not None and h.semantic_rank is not None for h in hits)
    assert SemanticSearcher(store).search("create account")
    monkeypatch.setenv("CODECTX_MODEL_NAME", "different/model")
    with pytest.raises(RuntimeError, match="embed --force"):
        SemanticSearcher(store)
    with pytest.warns(UserWarning):
        assert HybridSearcher(store).search("helper")


@pytest.mark.parametrize("command", [[], ["--version"], ["doctor", "--json"]])
def test_cli_basics(command):
    result = subprocess.run(
        [sys.executable, "-m", "codectx", *command], capture_output=True, text=True
    )
    assert result.returncode == (2 if not command else 0)


def test_deep_java_expression_uses_iterative_walk():
    from codectx.languages.java import analyze

    source = "class Deep { int f() { return " + "+".join(["g()"] * 2500) + "; } }"
    result, refs = analyze(source, "Deep.java")
    assert result.parse_ok
    assert len([r for r in refs if r.kind == "calls"]) == 2500


def test_partial_reference_view_preserves_full_index(repo):
    from codectx.semantic import embed_symbols

    root, store = repo
    before = (store.index_dir / "refs.jsonl").read_bytes()
    partial = Store(store.index_dir, root, ref_kinds={"extends", "implements"})
    assert all(r.kind == "extends" for r in partial.all_refs())
    with pytest.raises(RuntimeError, match="Partial"):
        partial.delete_file("a.py")
    embed_symbols(partial, [s for s in partial.all_symbols() if s.parse_ok])
    partial.commit()
    assert (store.index_dir / "refs.jsonl").read_bytes() == before
    complete = Store.open(root)
    assert complete.get_vectors() is not None
    from codectx.hybrid import HybridSearcher

    a = HybridSearcher(partial).search("user controller")
    b = HybridSearcher(complete).search("user controller")
    assert [(h.symbol_id, h.score) for h in a] == [(h.symbol_id, h.score) for h in b]
