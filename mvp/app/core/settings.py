from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Settings:
    mvp_root: Path
    app_name: str
    environment: str
    debug: bool
    version: str
    template_root: Path
    policy_documents_path: Path
    products_json_path: Path
    claims_dev_path: Path
    labels_dev_path: Path
    claims_eval_path: Path
    labels_eval_path: Path
    sqlite_path: Path
    reports_dir: Path
    plugin_config_path: Path
    model_config_path: Path
    demo_scenarios_path: Path
    retrieval_enabled: bool
    retrieval_mode: str
    retrieval_top_k: int
    fail_closed: bool
    low_confidence_threshold: float

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> "Settings":
        mvp_root = Path(__file__).resolve().parents[2]
        config_file = Path(
            config_path
            or os.environ.get("CLAIM_MVP_CONFIG_PATH")
            or mvp_root / "config" / "app_config.yaml"
        ).resolve()
        config = _parse_simple_yaml(config_file)

        app_config = config.get("app", {})
        paths = config.get("paths", {})
        workflow = config.get("workflow", {})
        retrieval = config.get("retrieval", {})

        template_root = _path(
            os.environ.get("CLAIM_MVP_TEMPLATE_ROOT") or paths.get("template_root", "../ai_agent_template"),
            mvp_root,
        )
        sqlite_path = _path(
            os.environ.get("CLAIM_MVP_SQLITE_PATH") or paths.get("sqlite_path", "runtime/mvp.sqlite3"),
            mvp_root,
        )
        reports_dir = _path(
            os.environ.get("CLAIM_MVP_REPORTS_DIR") or paths.get("reports_dir", "runtime/reports"),
            mvp_root,
        )
        plugin_config_path = _path(
            os.environ.get("CLAIM_MVP_PLUGIN_CONFIG") or mvp_root / "config" / "plugins.yaml",
            mvp_root,
        )
        model_config_path = _path(
            os.environ.get("CLAIM_MVP_MODEL_CONFIG") or mvp_root / "config" / "model_config.yaml",
            mvp_root,
        )
        demo_scenarios_path = _path(
            os.environ.get("CLAIM_MVP_DEMO_SCENARIOS")
            or paths.get("demo_scenarios", "config/demo_scenarios.json"),
            mvp_root,
        )

        retrieval_enabled = _bool(
            os.environ.get("CLAIM_MVP_RETRIEVAL_ENABLED"),
            default=_bool(retrieval.get("enabled"), default=True),
        )
        retrieval_mode = str(os.environ.get("CLAIM_MVP_RETRIEVAL_MODE") or retrieval.get("mode", "keyword"))
        retrieval_top_k = int(os.environ.get("CLAIM_MVP_RETRIEVAL_TOP_K") or retrieval.get("top_k", 3))

        return cls(
            mvp_root=mvp_root,
            app_name=str(app_config.get("name", "insurance-claims-review-mvp")),
            environment=str(app_config.get("environment", "local")),
            debug=_bool(app_config.get("debug"), default=False),
            version=str(app_config.get("version", "0.1.0")),
            template_root=template_root,
            policy_documents_path=_path(paths.get("policy_documents", "../data_generator/generated/policy_documents.md"), mvp_root),
            products_json_path=_path(paths.get("products_json", "../data_generator/generated/products.json"), mvp_root),
            claims_dev_path=_path(paths.get("claims_dev", "../data_generator/generated/claims_dev.jsonl"), mvp_root),
            labels_dev_path=_path(paths.get("labels_dev", "../data_generator/generated/labels_dev.jsonl"), mvp_root),
            claims_eval_path=_path(paths.get("claims_eval", "../data_generator/generated/claims_eval.jsonl"), mvp_root),
            labels_eval_path=_path(paths.get("labels_eval", "../data_generator/generated/labels_eval.jsonl"), mvp_root),
            sqlite_path=sqlite_path,
            reports_dir=reports_dir,
            plugin_config_path=plugin_config_path,
            model_config_path=model_config_path,
            demo_scenarios_path=demo_scenarios_path,
            retrieval_enabled=retrieval_enabled,
            retrieval_mode=retrieval_mode,
            retrieval_top_k=retrieval_top_k,
            fail_closed=_bool(workflow.get("fail_closed"), default=True),
            low_confidence_threshold=float(workflow.get("low_confidence_threshold", 0.75)),
        )


def _path(value: str | Path, base: Path) -> Path:
    raw = Path(_resolve_env(str(value)))
    if raw.is_absolute():
        return raw.resolve()
    return (base / raw).resolve()


def _resolve_env(value: str) -> str:
    if value.startswith("${") and value.endswith("}"):
        return os.environ.get(value[2:-1], "")
    return value


def _bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {"0", "false", "no", "off"}


def _parse_simple_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"MVP config not found: {path}")
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        stripped = raw_line.strip()
        if ":" not in stripped:
            continue
        key, raw_value = stripped.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if raw_value == "":
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _coerce_yaml_value(raw_value)
    return root


def _coerce_yaml_value(value: str) -> Any:
    cleaned = _resolve_env(value.strip())
    if (cleaned.startswith('"') and cleaned.endswith('"')) or (
        cleaned.startswith("'") and cleaned.endswith("'")
    ):
        return cleaned[1:-1]
    lowered = cleaned.lower()
    if lowered in {"true", "false"}:
        return lowered == "true"
    try:
        return int(cleaned)
    except ValueError:
        pass
    try:
        return float(cleaned)
    except ValueError:
        return cleaned
