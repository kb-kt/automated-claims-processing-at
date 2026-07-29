from __future__ import annotations

from typing import Any


def verify_policy_basis(agent_output: dict[str, Any]) -> dict[str, Any]:
    """Check whether reviewer-visible policy basis entries are citation-ready."""

    basis = agent_output.get("policy_basis") or []
    missing_citations: list[dict[str, Any]] = []
    citation_count = 0
    for index, item in enumerate(basis):
        if not isinstance(item, dict):
            missing_citations.append(
                {
                    "index": index,
                    "reason": "policy_basis entry is not an object",
                }
            )
            continue
        has_citation = bool(item.get("citation_id") or item.get("clause_id"))
        if has_citation:
            citation_count += 1
            continue
        missing_citations.append(
            {
                "index": index,
                "source": item.get("source"),
                "section": item.get("section"),
                "reason": "missing citation_id or clause_id",
            }
        )

    return {
        "verified": bool(basis) and not missing_citations,
        "basis_count": len(basis),
        "citation_count": citation_count,
        "missing_citations": missing_citations,
    }
