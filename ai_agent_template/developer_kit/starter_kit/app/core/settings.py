from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    template_root: Path
    sqlite_path: Path
    reports_dir: Path
    fraud_generated_dir: Path = Path("data_generator/generated")
    uploaded_documents_dir: Path = Path("runtime/documents")
    max_document_bytes: int = 10_000_000
    plugin_config_path: Path | None = None
    specialist_config_path: Path | None = None
    model_config_path: Path | None = None
    retrieval_enabled: bool = True
    retrieval_mode: str = "keyword"
    retrieval_top_k: int = 3
    auth_enabled: bool = False
    customer_api_key: str = ""
    reviewer_api_key: str = ""
    admin_api_key: str = ""

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
        fraud_generated_dir = Path(
            os.environ.get(
                "CLAIM_AGENT_FRAUD_GENERATED_DIR",
                template_root.parent / "data_generator" / "generated",
            )
        ).resolve()
        uploaded_documents_dir = Path(
            os.environ.get(
                "CLAIM_AGENT_DOCUMENT_STORAGE_DIR",
                starter_root / "runtime" / "documents",
            )
        ).resolve()
        max_document_bytes = int(os.environ.get("CLAIMS_INTERNAL_MAX_DOCUMENT_BYTES", "10000000"))
        plugin_config_path = Path(
            os.environ.get("CLAIM_AGENT_PLUGIN_CONFIG", starter_root / "config" / "plugins.yaml")
        ).resolve()
        specialist_config_path = Path(
            os.environ.get(
                "CLAIM_AGENT_SPECIALIST_PLUGIN_CONFIG",
                starter_root / "config" / "specialist_plugins.synthetic_insurer.yaml",
            )
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
        auth_enabled = os.environ.get("CLAIM_AGENT_AUTH_ENABLED", "false").lower() in {
            "1", "true", "yes", "on"
        }
        return cls(
            template_root=template_root,
            sqlite_path=sqlite_path,
            reports_dir=reports_dir,
            fraud_generated_dir=fraud_generated_dir,
            uploaded_documents_dir=uploaded_documents_dir,
            max_document_bytes=max_document_bytes,
            plugin_config_path=plugin_config_path,
            specialist_config_path=specialist_config_path,
            model_config_path=model_config_path,
            retrieval_enabled=retrieval_enabled,
            retrieval_mode=retrieval_mode,
            retrieval_top_k=retrieval_top_k,
            auth_enabled=auth_enabled,
            customer_api_key=os.environ.get("CLAIM_AGENT_CUSTOMER_API_KEY", ""),
            reviewer_api_key=os.environ.get("CLAIM_AGENT_REVIEWER_API_KEY", ""),
            admin_api_key=os.environ.get("CLAIM_AGENT_ADMIN_API_KEY", ""),
        )
