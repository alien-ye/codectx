import hashlib
import subprocess
from contextlib import nullcontext
from dataclasses import asdict, dataclass
from pathlib import Path

from .body import DATABASE, body_writer
from .extract import extract_and_persist
from .store import FileRecord

EXTRACTION_VERSIONS = {"python": 2, "java": 1, "groovy": 1}
SUPPORTED_CODE_EXTENSIONS = {".py", ".java", ".groovy"}
DEFAULT_SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".codectx",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    ".tox",
    "dist",
    "build",
}


@dataclass(frozen=True, slots=True)
class DiscoveredFile:
    path: Path
    rel_path: str
    extension: str


@dataclass(frozen=True, slots=True)
class IndexStats:
    total_files: int
    indexed_files: int
    code_files: int
    skipped: int
    reindexed: int
    unchanged: int
    deleted: int = 0

    def to_dict(self):
        return asdict(self)


def detect_language(path):
    return {".py": "python", ".java": "java", ".groovy": "groovy"}.get(
        Path(path).suffix.lower(), "unknown"
    )


def content_hash(text):
    return hashlib.sha256(text.encode()).hexdigest()


def discover_files(root, *, exclude_dir=None):
    root = Path(root).resolve()
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        timeout=60,
    )
    if result.returncode == 0:
        paths = result.stdout.decode(errors="replace").split("\0")
    else:
        # pathspec handles ignore files even when there is no Git repository.
        import pathspec

        paths = []

        def walk(directory, inherited):
            rules = list(inherited)
            for ignore in (".gitignore", ".ignore"):
                p = directory / ignore
                if p.exists():
                    rules.append(
                        (directory, pathspec.GitIgnoreSpec.from_lines(p.read_text().splitlines()))
                    )
            for p in sorted(directory.iterdir()):
                if p == exclude_dir or p.is_symlink() or p.name in DEFAULT_SKIP_DIRS:
                    continue
                if any(
                    spec.match_file(p.relative_to(base).as_posix() + ("/" if p.is_dir() else ""))
                    for base, spec in rules
                ):
                    continue
                if p.is_dir():
                    walk(p, rules)
                else:
                    paths.append(p.relative_to(root).as_posix())

        walk(root, [])
    for rel in sorted(set(paths)):
        if not rel or any(part in DEFAULT_SKIP_DIRS for part in Path(rel).parts):
            continue
        p = root / rel
        if exclude_dir and p.is_relative_to(exclude_dir):
            continue
        # Do not follow symlinks outside the source tree.
        if p.is_file() and not p.is_symlink() and p.resolve().is_relative_to(root):
            yield DiscoveredFile(p, rel, p.suffix.lower())


def index_files(store, root, *, extract_fn=None, bodies=False, rebuild_bodies=False):
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError(f"Not a directory: {root}")
    enabled = bodies or (store.index_dir / DATABASE).exists()
    writer = body_writer(store.index_dir, rebuild_bodies) if enabled else nullcontext()
    with writer as body:
        with store.batch_replacements() if extract_fn is None else nullcontext():
            seen, stats = _scan_files(store, root, extract_fn, body)
        store.root = root
        store.set_meta("last_index_root", str(root))
        store.commit()
        if body:
            body.finish(seen, store.get_meta("indexed_at"))
        return stats


def _scan_files(store, root, extract_fn, body):
    seen = set()
    new = changed = unchanged = code = skipped = 0
    exclude = store.index_dir if root in store.index_dir.parents else None
    for f in discover_files(root, exclude_dir=exclude):
        seen.add(f.rel_path)
        lang = detect_language(f.rel_path)
        try:
            if lang == "unknown":
                with f.path.open("rb") as stream:
                    digest = hashlib.file_digest(stream, "sha256").hexdigest()
            else:
                source = f.path.read_text(encoding="utf-8", errors="replace")
                digest = content_hash(source)
            stat = f.path.stat()
        except OSError as e:
            store.set_meta("error:" + f.rel_path, str(e))
            skipped += 1
            continue
        old = store.get_files().get(f.rel_path)
        code += lang != "unknown"
        version = EXTRACTION_VERSIONS.get(lang, 0)
        store.upsert_file(
            FileRecord(f.rel_path, lang, digest, stat.st_mtime_ns, stat.st_size, version)
        )
        if old and old.content_hash == digest and old.extraction_version == version:
            unchanged += 1
        else:
            new += old is None
            changed += old is not None
            if lang != "unknown":
                if extract_fn:
                    extract_fn(store, root, f.rel_path, lang)
                else:
                    extract_and_persist(store, root, f.rel_path, lang, source)
        if (
            body
            and lang != "unknown"
            and (
                body.hashes.get(f.rel_path) != digest or (old and old.extraction_version != version)
            )
        ):
            body.update(f.rel_path, digest, source, store.symbols_for_file(f.rel_path))
    deleted = set(store.get_files()) - seen
    for path in sorted(deleted):
        store.delete_file(path)
    return seen, IndexStats(len(seen), new, code, skipped, changed, unchanged, len(deleted))
