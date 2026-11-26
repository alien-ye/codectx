import os
import subprocess
import sys
from pathlib import Path

base = Path(__file__).parent
out = base / "results"
for repo in ["langchain", "django", "spring-boot", "kafka", "jdk21u"]:
    with (out / f"{repo}-evaluation.log").open("w") as log:
        result = subprocess.run(
            ["/usr/bin/time", "-v", sys.executable, str(base / "evaluate.py"), repo],
            stdout=log,
            stderr=subprocess.STDOUT,
            env={
                **os.environ,
                "HF_HUB_OFFLINE": "1",
                "OPENBLAS_NUM_THREADS": "1",
                "OMP_NUM_THREADS": "1",
                "TOKENIZERS_PARALLELISM": "false",
            },
        )
    print(repo, result.returncode, flush=True)
    if result.returncode:
        print((out / f"{repo}-evaluation.log").read_text()[-6000:], flush=True)
