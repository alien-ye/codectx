import json
import shutil

import pytest

from codectx.body import DATABASE, search_bodies
from codectx.cli import main
from codectx.doctor import diagnose
from codectx.hybrid import HybridSearcher
from codectx.store import Store


def test_upgrade_search_update_delete(tmp_path, capsys, monkeypatch):
    source = tmp_path / "src"
    source.mkdir()
    (source / "a.py").write_text("\n" * 20 + 'def f():\n    raise ValueError("sentinel")\n')
    (source / "b.py").write_text('def g():\n    return "preserved"\n')
    db = source / "custom index"
    repo = [str(source), "--db", str(db)]
    assert main(["index", *repo]) == 0
    assert main(["search", "sentinel", *repo, "--mode", "body"]) == 1
    assert "--bodies" in capsys.readouterr().err
    assert main(["index", *repo, "--bodies"]) == 0
    before = {
        p: p.stat().st_mtime_ns for p in db.iterdir() if p.suffix in {".jsonl", ".json", ".sqlite3"}
    }
    assert main(["index", *repo]) == 0
    assert before == {p: p.stat().st_mtime_ns for p in before}
    assert set(Store.open_at(db).get_files()) == {"a.py", "b.py"}
    capsys.readouterr()
    with monkeypatch.context() as patch:

        def unexpected_store_load(*args, **kwargs):
            pytest.fail("body search loaded the symbol store")

        patch.setattr(Store, "_load", unexpected_store_load)
        assert main(["context", "sentinel", *repo, "--mode", "body", "--tokens", "30"]) == 0
        output = capsys.readouterr().out
        assert "a.py:21-22" in output and 'raise ValueError("sentinel")' in output
        assert len(output) <= 120
        assert main(["context", "sentinel", *repo, "--mode", "body", "--tokens", "1"]) == 1
        assert not capsys.readouterr().out

    (source / "a.py").write_text("changed = 1\n")
    assert main(["index", *repo]) == 0
    assert not search_bodies(db, "sentinel")
    assert search_bodies(db, "changed")[0].path == "a.py"
    (source / "a.py").unlink()
    assert main(["index", *repo]) == 0
    assert not search_bodies(db, "changed")
    assert search_bodies(db, "preserved")[0].path == "b.py"

    manifest = db / "manifest.json"
    data = json.loads(manifest.read_bytes())
    data["indexed_at"] += 1
    manifest.write_text(json.dumps(data))
    with pytest.raises(RuntimeError, match="out of date"):
        search_bodies(db, "preserved")
    assert main(["index", *repo]) == 0
    assert search_bodies(db, "preserved")
    (db / DATABASE).write_bytes(b"corrupt")
    assert main(["index", *repo, "--force"]) == 0
    assert search_bodies(db, "preserved")


def test_exact_queries_route_around_boost(tmp_path):
    (tmp_path / "a.py").write_text(
        'class Service:\n    """Handles requests."""\n    def handle(self): pass\n'
        + "".join(f"class Child{i}(Service): pass\n" for i in range(5))
    )
    assert main(["index", str(tmp_path)]) == 0
    store = Store.open(tmp_path)
    searcher = HybridSearcher(store)
    for name in ("Service", "Service.handle"):
        assert searcher.search(name) == searcher.search(name, boost=False)
        assert searcher.search(name) != searcher.search(name, boost=True)
    assert searcher.search("handles requests") == searcher.search("handles requests", boost=True)


def test_external_store_respects_explicit_root(tmp_path, capsys):
    root = tmp_path / "old"
    root.mkdir()
    (root / "a.py").write_text("def helper(): pass\n")
    db = tmp_path / "store"
    assert main(["index", str(root), "--db", str(db)]) == 0
    new = root.rename(tmp_path / "moved")
    assert Store.open_at(db).root == root
    assert Store(db, new, readonly=True).root == new
    capsys.readouterr()
    assert main(["symbols", "subdir/../a.py", str(new), "--db", str(db), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["name"] == "helper"


def test_ripgrep_optional(tmp_path, monkeypatch, capsys):
    binary = shutil.which
    monkeypatch.setattr(shutil, "which", lambda name: None if name == "rg" else binary(name))
    report = diagnose()
    assert report.exit_code == 0
    assert any(c.name == "rg" and not c.ok and not c.required for c in report.checks)
    assert main(["index", str(tmp_path)]) == 0
    assert main(["coverage", str(tmp_path)]) == 1
    assert "requires ripgrep" in capsys.readouterr().err


def test_body_passages_keep_scopes_and_line_numbers(tmp_path):
    source = (
        "class Container:\n    def action(self):\n"
        + "        pass\n" * 50
        + "        return 'hallmark'\n"
        + "    def other(self):\n        return 'adjacent'\n"
    )
    (tmp_path / "a.py").write_text(source)
    assert main(["index", str(tmp_path), "--bodies"]) == 0
    db = tmp_path / ".codectx"
    hit = search_bodies(db, "hallmark")[0]
    assert hit.scope == "Container.action"
    assert hit.start_line <= 53 <= hit.end_line
    assert hit.end_line - hit.start_line < 48
    assert hit.body == "\n".join(source.splitlines()[hit.start_line - 1 : hit.end_line])
    assert search_bodies(db, "adjacent")[0].scope == "Container.other"
    assert not search_bodies(db, '() " *')


def test_body_transaction_after_failed_update(tmp_path):
    from codectx.index import index_files

    source = tmp_path / "a.py"
    source.write_text("first = 1\n")
    repo = [str(tmp_path), "--bodies"]
    assert main(["index", *repo]) == 0
    db = tmp_path / ".codectx"
    source.write_text("replacement = 1\n")
    (tmp_path / "b.py").write_text("second = 2\n")

    def fail_on_second(store, root, path, lang):
        from codectx.extract import extract_and_persist

        if path == "b.py":
            raise RuntimeError("simulated interruption")
        extract_and_persist(store, root, path, lang)

    with pytest.raises(RuntimeError, match="simulated interruption"):
        index_files(Store.open(tmp_path), tmp_path, extract_fn=fail_on_second)
    assert search_bodies(db, "first")
    assert not search_bodies(db, "replacement")
    assert main(["index", *repo]) == 0
    assert search_bodies(db, "replacement")
    assert not search_bodies(db, "first")
