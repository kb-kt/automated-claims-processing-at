from __future__ import annotations

import subprocess
import sys
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[1]
SUITES = [
    ("data_generator", [sys.executable, "-m", "unittest", "discover", "-s", "data_generator/tests"]),
    ("ai_agent_template", [sys.executable, "-m", "unittest", "discover", "-s", "ai_agent_template"]),
    ("mvp", [sys.executable, "-m", "unittest", "discover", "-s", "mvp/tests"]),
    ("integration", [sys.executable, "-m", "unittest", "discover", "-s", "integration_tests"]),
]


def main() -> int:
    for name, command in SUITES:
        print(f"[quality-gate] running {name}", flush=True)
        completed = subprocess.run(command, cwd=WORKSPACE, check=False)
        if completed.returncode != 0:
            print(f"[quality-gate] failed: {name}", flush=True)
            return completed.returncode
    print("[quality-gate] all suites passed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
