import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RgHit:
    file: str
    line: int
    column: int
    text: str


@dataclass(frozen=True, slots=True)
class CoverageGap:
    name: str
    file: str
    line: int


def rg_search(root, pattern, fixed_string=True):
    cmd = ["rg", "--line-number", "--column", "--no-heading", "--color=never"]
    if fixed_string:
        cmd.append("--fixed-strings")
    result = subprocess.run(
        [*cmd, "--", pattern, "."], cwd=root, capture_output=True, text=True, timeout=60
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr)
    hits = []
    for line in result.stdout.splitlines():
        file, row, col, text = line.split(":", 3)
        hits.append(RgHit(file.removeprefix("./"), int(row), int(col), text))
    return hits


def enumerate_python_definitions(root):
    if not shutil.which("rg"):
        raise RuntimeError("The coverage command requires ripgrep (rg) on PATH.")
    result = subprocess.run(
        [
            "rg",
            "-n",
            "--no-heading",
            "--color=never",
            "-g",
            "*.py",
            "-o",
            r"^\s*(?:async\s+def|def|class)\s+[A-Za-z_]\w*",
            ".",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr)
    found = {}
    for line in result.stdout.splitlines():
        file, row, text = line.split(":", 2)
        name = re.split(r"\s+", text.strip())[-1]
        found.setdefault(name, []).append((file.removeprefix("./"), int(row)))
    return found


def differential_coverage(store, root, sample_size=50, out=None):
    flat = sorted(
        (name, file, line)
        for name, locations in enumerate_python_definitions(root).items()
        for file, line in locations
    )
    present = {(s.name, s.file_path, s.start_line) for s in store.all_symbols() if s.parse_ok}
    sample = flat[:: max(1, len(flat) // max(1, sample_size))][:sample_size]
    gaps = [
        CoverageGap(name, file, line)
        for name, file, line in sample
        if (name, file, line) not in present
    ]
    if out:
        print(f"{len(sample)} sampled, {len(gaps)} missing", file=out)
    return gaps


def iter_python_files(root):
    return Path(root).rglob("*.py")
