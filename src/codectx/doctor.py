import importlib.util
import shutil
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from .store import Store


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    ok: bool
    required: bool
    detail: str

    def to_report_line(self):
        tag = "ok" if self.ok else "MISSING" if self.required else "missing (optional)"
        return f"[*] {self.name:<28} {tag:<20} {self.detail}"


@dataclass(slots=True)
class DoctorReport:
    checks: list[Check]

    @property
    def exit_code(self):
        return int(any(c.required and not c.ok for c in self.checks))

    def to_dict(self):
        return dict(checks=[asdict(c) for c in self.checks], exit_code=self.exit_code)

    def to_text(self):
        missing = [c.name for c in self.checks if c.required and not c.ok]
        return (
            "\n".join(c.to_report_line() for c in self.checks)
            + "\n\n"
            + (
                "Required capabilities missing: " + ", ".join(missing)
                if missing
                else "All required capabilities present."
            )
        )


def diagnose(repo=None, db=None):
    checks = [Check("python", sys.version_info >= (3, 12), True, sys.version.split()[0])]
    checks.extend(
        Check(
            binary,
            bool(shutil.which(binary)),
            binary != "rg",
            shutil.which(binary) or "not on PATH",
        )
        for binary in ("git", "rg")
    )
    for module in (
        "tree_sitter",
        "tree_sitter_python",
        "model2vec",
        "numpy",
        "orjson",
        "pathspec",
        "tree_sitter_java",
        "mcp",
    ):
        checks.append(
            Check(
                module,
                importlib.util.find_spec(module) is not None,
                module not in {"mcp", "tree_sitter_java"},
                "import availability",
            )
        )
    if repo:
        path = Path(db) if db else Path(repo) / ".codectx"
        checks.append(Check("index_exists", (path / "manifest.json").exists(), False, str(path)))
        if (path / "manifest.json").exists():
            try:
                store = Store.open_at(path, readonly=True)
                checks.append(
                    Check(
                        "index_symbol_count",
                        len(store.all_symbols()) == store.get_meta("symbol_count"),
                        False,
                        "manifest vs records",
                    )
                )
                checks.append(
                    Check(
                        "index_has_symbols",
                        not store.get_files() or bool(store.all_symbols()),
                        False,
                        "index --force to rebuild",
                    )
                )
                invalid = [r for r in store.all_refs() if r.file_path not in store.get_files()]
                checks.append(
                    Check(
                        "index_ref_files", not invalid, False, f"{len(invalid)} orphan references"
                    )
                )
                checks.append(
                    Check(
                        "index_parse_errors",
                        not any(k.startswith("error:") for k in store._manifest),
                        False,
                        f"{sum(k.startswith('error:') for k in store._manifest)} files with errors",
                    )
                )
            except (ValueError, OSError, RuntimeError, KeyError) as e:
                checks.append(Check("index_integrity", False, False, str(e)))
    return DoctorReport(checks)


def doctor(repo=None):
    return diagnose(repo)
