"""Optional SQLite FTS5 index of line-numbered source passages."""

import json
import os
import sqlite3
from contextlib import closing, contextmanager
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from tempfile import NamedTemporaryFile

from .tokens import query_tokens

DATABASE = "bodies.sqlite3"
PASSAGE_LINES = 48


def _passages(source, symbols):
    """Keep short definitions together and give long ones bounded, named passages."""
    lines = source.split("\n")
    if lines[-1] == "":
        lines.pop()
    definitions = sorted(
        (s for s in symbols if s.parse_ok and s.kind in {"class", "method", "function"}),
        key=lambda s: (s.start_line, -s.end_line, s.start_byte),
    )
    boundary = {1, len(lines) + 1}
    for s in definitions:
        boundary.update((s.start_line, s.end_line + 1))
    starts = iter(definitions)
    upcoming = next(starts, None)
    active = []
    boundaries = sorted(b for b in boundary if 1 <= b <= len(lines) + 1)
    for first, stop in pairwise(boundaries):
        while active and active[-1].end_line < first:
            active.pop()
        while upcoming and upcoming.start_line == first:
            active.append(upcoming)
            upcoming = next(starts, None)
        scope = active[-1].qualified_name if active else ""
        for line in range(first, stop, PASSAGE_LINES):
            end = min(stop - 1, line + PASSAGE_LINES - 1)
            text = "\n".join(lines[line - 1 : end])
            if text.strip():
                yield text, scope, line, end


class BodyWriter:
    def __init__(self, db):
        self.db = db
        self.hashes = dict(db.execute("SELECT path, digest FROM files"))

    def remove(self, path):
        self.db.execute(
            "DELETE FROM passages WHERE rowid BETWEEN "
            "(SELECT first_row FROM files WHERE path=?) AND (SELECT last_row FROM files WHERE path=?)",
            (path, path),
        )
        self.db.execute("DELETE FROM files WHERE path=?", (path,))

    def update(self, path, digest, source, symbols):
        if path in self.hashes:
            self.remove(path)
        first = last = None
        for text, scope, start, end in _passages(source, symbols):
            last = self.db.execute(
                "INSERT INTO passages(body,scope,path,start_line,end_line) VALUES(?,?,?,?,?)",
                (text, scope, path, start, end),
            ).lastrowid
            if first is None:
                first = last
        self.db.execute("INSERT INTO files VALUES(?,?,?,?)", (path, digest, first, last))

    def finish(self, seen, generation):
        for path in self.hashes.keys() - seen:
            self.remove(path)
        self.db.execute(
            "INSERT INTO state(id,generation) VALUES(1,?) ON CONFLICT(id) DO UPDATE "
            "SET generation=excluded.generation WHERE generation != excluded.generation",
            (generation,),
        )


@contextmanager
def body_writer(directory, rebuild=False):
    path = directory / DATABASE
    directory.mkdir(parents=True, exist_ok=True)
    temp = None
    if rebuild or not path.exists():
        with NamedTemporaryFile(dir=directory, prefix=".bodies-", delete=False) as stream:
            temp = Path(stream.name)
    try:
        with closing(sqlite3.connect(temp or path, timeout=60)) as db, db:
            db.execute("BEGIN IMMEDIATE")
            if temp:
                db.execute(
                    "CREATE TABLE files(path TEXT PRIMARY KEY, digest TEXT, first_row INT, last_row INT)"
                )
                db.execute(
                    "CREATE TABLE state(id INTEGER PRIMARY KEY, generation INTEGER NOT NULL)"
                )
                db.execute(
                    "CREATE VIRTUAL TABLE passages USING fts5(body,scope,path UNINDEXED,start_line UNINDEXED,end_line UNINDEXED, tokenize='porter unicode61')"
                )
            yield BodyWriter(db)
        if temp:
            os.replace(temp, path)
    except sqlite3.Error as exc:
        raise RuntimeError(
            f"Body index at {path}: {exc}. Rebuild with index --force --bodies (requires SQLite FTS5)."
        ) from exc
    finally:
        if temp:
            temp.unlink(missing_ok=True)


@dataclass(frozen=True, slots=True)
class Passage:
    path: str
    start_line: int
    end_line: int
    body: str
    scope: str


def search_bodies(index_dir, query, k=10):
    directory = Path(index_dir).resolve()
    path = directory / DATABASE
    if not path.exists():
        raise RuntimeError("No body index. Run codectx index with --bodies first.")
    terms = dict.fromkeys(query_tokens(query))
    match = " OR ".join(f'"{term}"' for term in terms)
    try:
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
            db.execute("BEGIN")
            state = db.execute("SELECT generation FROM state WHERE id=1").fetchone()
            manifest = json.loads((directory / "manifest.json").read_bytes())
            if state != (manifest["indexed_at"],):
                raise RuntimeError("Body index is out of date. Run codectx index --bodies again.")
            if not match or k <= 0:
                return []
            rows = db.execute(
                "SELECT path,start_line,end_line,body,scope FROM passages WHERE passages MATCH ? "
                "ORDER BY bm25(passages,1,4), path, start_line LIMIT ?",
                (match, k),
            )
            return [Passage(*row) for row in rows]
    except sqlite3.Error as exc:
        raise RuntimeError(
            f"Cannot search body index: {exc}. Rebuild with index --force --bodies."
        ) from exc
