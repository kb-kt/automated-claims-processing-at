from __future__ import annotations

from typing import Any


def build_agent_report(
    *,
    agent_name: str,
    summary: str,
    findings: list[dict[str, Any]] | None = None,
    reason_codes: list[str] | None = None,
    citations: list[dict[str, Any]] | None = None,
    risk_level: str = "low",
    requires_human_review: bool = False,
    status: str = "success",
    agent_version: str = "1.0.0",
    confidence_factors: dict[str, float] | None = None,
    warnings: list[str] | None = None,
    tool_trace_refs: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "agent_name": agent_name,
        "agent_version": agent_version,
        "status": status,
        "summary": summary,
        "findings": findings or [],
        "reason_codes": list(dict.fromkeys(reason_codes or [])),
        "citations": citations or [],
        "risk_level": risk_level,
        "requires_human_review": bool(requires_human_review),
        "confidence_factors": {
            "evidence_clarity": float((confidence_factors or {}).get("evidence_clarity", 0.0)),
            "judgment_difficulty": float((confidence_factors or {}).get("judgment_difficulty", 0.0)),
            "uncertainty": float((confidence_factors or {}).get("uncertainty", 0.0)),
        },
        "warnings": warnings or [],
        "tool_trace_refs": tool_trace_refs or [],
    }
