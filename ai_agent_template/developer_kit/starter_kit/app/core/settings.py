from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    template_root: Path
    sqlite_path: Path
    reports_dir: Path
    plugin_config_path: Path | None = None
    model_config_path: Path | None = None
    retrieval_enabled: bool = True
    retrieval_mode: str = "keyword"
    retrieval_top_k: int = 3

    @classmethod
    def load(cls) -> "Settings":
        starter_root = Path(__file__).resolve().parents[2]
        template_root = Path(os.environ.get("CLAIM_AGENT_TEMPLATE_ROOT", starter_root.parents[1])).resolve()
        sqlite_path = Path(
            os.environ.get("CLAIM_AGENT_SQLITE_PATH", starter_root / "runtime" / "starter_kit.sqlite3")
        ).resolve()
        reports_dir = Path(
            os.environ.get("CLAIM_AGENT_REPORTS_DIR", starter_root / "runtime" / "eval_runs")
        ).resolve()
        plugin_config_path = Path(
            os.environ.get("CLAIM_AGENT_PLUGIN_CONFIG", starter_root / "config" / "plugins.yaml")
        ).resolve()
        model_config_path = Path(
            os.environ.get("CLAIM_AGENT_MODEL_CONFIG", starter_root / "config" / "model_config.yaml")
        ).resolve()
        retrieval_enabled = os.environ.get("CLAIM_AGENT_RETRIEVAL_ENABLED", "true").lower() not in {
            "0",
            "false",
            "no",
        }
        retrieval_mode = os.environ.get("CLAIM_AGENT_RETRIEVAL_MODE", "keyword")
        retrieval_top_k = int(os.environ.get("CLAIM_AGENT_RETRIEVAL_TOP_K", "3"))
        return cls(
            template_root=template_root,
            sqlite_path=sqlite_path,
            reports_dir=reports_dir,
            plugin_config_path=plugin_config_path,
            model_config_path=model_config_path,
            retrieval_enabled=retrieval_enabled,
            retrieval_mode=retrieval_mode,
            retrieval_top_k=retrieval_top_k,
        )
