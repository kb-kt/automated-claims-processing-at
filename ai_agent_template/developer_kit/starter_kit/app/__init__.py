"""Starter Kit application package.

The starter can be launched from its own directory with
`uvicorn app.main:app`. In that mode the repository root is not naturally on
`sys.path`, so add it before submodules import `ai_agent_template.*`.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_workspace_on_path() -> None:
    workspace_root = Path(__file__).resolve().parents[4]
    workspace = str(workspace_root)
    if workspace not in sys.path:
        sys.path.insert(0, workspace)


_ensure_workspace_on_path()
