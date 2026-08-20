from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .template_loader import TemplateBundle
from .workflow_loader import WorkflowLoader


def build_decision_provenance(
    template: TemplateBundle,
    *,
    model_provider: Any,
    tool_registry: Any,
    specialist_agents: list[Any],
    policy_sources: list[str | Path] | None = None,
    medical_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic, secret-free fingerprint of decision dependencies."""

    workflow = WorkflowLoader(template).load()
    prompt_path = template.require("prompts/claim_review_prompt.md")
    policy_fingerprints = []
    for source in policy_sources or []:
        path = Path(source)
        if path.exists() and path.is_file():
            policy_fingerprints.append({"name": path.name, "sha256": _hash_bytes(path.read_bytes())})
    plugins = [
        {
            "name": name,
            "class": f"{plugin.__class__.__module__}.{plugin.__class__.__name__}",
            "version": str(getattr(plugin, "contract_version", "unknown")),
        }
        for name, plugin in sorted(getattr(tool_registry, "_plugins", {}).items())
    ]
    return {
        "provenance_version": "1.0.0",
        "input_schema_version": str(template.input_schema.get("version", "unknown")),
        "output_schema_version": str(template.output_schema.get("version", "unknown")),
        "workflow_id": str(workflow.get("workflow_id", "unknown")),
        "workflow_version": str(workflow.get("version", "unknown")),
        "workflow_sha256": _hash_bytes(template.require("workflows/claim_review_workflow.yaml").read_bytes()),
        "prompt_version": _prompt_version(prompt_path.read_text(encoding="utf-8")),
        "prompt_sha256": _hash_bytes(prompt_path.read_bytes()),
        "model": {
            "provider": str(getattr(model_provider, "provider_name", "unknown")),
            "model_id": str(getattr(model_provider, "model_id", "unknown")),
            "provider_version": str(getattr(model_provider, "version", "unknown")),
        },
        "tool_plugins": plugins,
        "specialist_agents": [
            {
                "name": str(getattr(agent, "name", "unknown")),
                "version": str(getattr(agent, "version", "unknown")),
                "class": f"{agent.__class__.__module__}.{agent.__class__.__name__}",
            }
            for agent in specialist_agents
        ],
        "policy_sources": policy_fingerprints,
        "medical_registry": extract_medical_evidence_provenance(medical_evidence or {}),
        "bundle_sha256": _hash_json(
            {"schemas": {"input": template.input_schema, "output": template.output_schema}, "contracts": template.tool_contracts()}
        ),
    }


def extract_medical_evidence_provenance(evidence: dict[str, Any]) -> dict[str, Any]:
    mappings = evidence.get("code_mapping_candidates") or {}
    return {
        "kcd_versions": _unique_versions(mappings.get("kcd") or [], "registry_version"),
        "edi_versions": _unique_versions(mappings.get("edi") or [], "registry_version"),
        "routing_rule_versions": _unique_versions(
            evidence.get("insurer_medical_routing_rules") or [],
            "rule_version",
        ),
    }


def _unique_versions(rows: list[Any], key: str) -> list[str]:
    return sorted(
        {
            str(row[key])
            for row in rows
            if isinstance(row, dict) and row.get(key)
        }
    )


def _prompt_version(text: str) -> str:
    for line in text.splitlines():
        if line.lower().startswith("version:"):
            return line.split(":", 1)[1].strip()
    return "unknown"


def _hash_json(value: Any) -> str:
    return _hash_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
