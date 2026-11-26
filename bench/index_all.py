"""Serial subprocesses keep repository peaks isolated and avoid memory contention."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

OUT = Path(__file__).parent / "results"
OUT.mkdir(exist_ok=True)
for repo in ["langchain", "django", "spring-boot", "kafka", "jdk21u"]:
    root = Path(os.environ.get("CODECTX_BENCH_REPOS", Path.home() / "repo")) / repo
    db = OUT / "indexes" / repo
    cmd = [sys.executable, "-m", "codectx", "index", str(root), "--db", str(db), "--stats"]
    for run in ["initial", "noop"]:
        started = time.perf_counter()
        with (OUT / f"{repo}-index-{run}.stderr").open("w") as error:
            result = subprocess.run(
                ["/usr/bin/time", "-v", *cmd, *(["--force"] if run == "initial" else [])],
                stdout=subprocess.PIPE,
                stderr=error,
                text=True,
                env={**os.environ, "OPENBLAS_NUM_THREADS": "1", "HF_HUB_OFFLINE": "1"},
            )
        record = dict(
            repo=repo,
            run=run,
            seconds=time.perf_counter() - started,
            returncode=result.returncode,
            stdout=result.stdout,
        )
        (OUT / f"{repo}-index-{run}.json").write_text(json.dumps(record, indent=2))
        print(json.dumps(record), flush=True)
        if result.returncode:
            break
