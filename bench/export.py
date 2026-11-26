"""Export source and benchmark evidence without environments or large indexes."""

import hashlib
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

root = Path(__file__).resolve().parents[1]
env_path = root / "bench/results/environment.json"
env = json.loads(env_path.read_text())
env["finalized_at_utc"] = datetime.now(UTC).isoformat()
env["source_sha256"] = {
    str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in (root / "src").rglob("*.py")
}
env["benchmark_sha256"] = {
    str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in (root / "bench").rglob("*.py")
}
env["queries_sha256"] = hashlib.sha256((root / "bench/queries.json").read_bytes()).hexdigest()
env_path.write_text(json.dumps(env, indent=2) + "\n")
archive = root.parent / "codectx-assessment.zip"
excluded = {
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".git",
    "indexes",
    ".agents",
    ".codex",
    ".aws",
}
with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as output:
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if (
            path.is_file()
            and not excluded.intersection(relative.parts)
            and not path.name.endswith(".tmp")
        ):
            output.write(path, "codectx/" + relative.as_posix())
print(archive, archive.stat().st_size, "bytes")
