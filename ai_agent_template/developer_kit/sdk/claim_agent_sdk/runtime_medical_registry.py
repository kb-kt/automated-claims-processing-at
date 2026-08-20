from __future__ import annotations

import copy
from typing import Any, Protocol


class RuntimeMedicalRegistry(Protocol):
    def get_medical_code(self, code: str, *, code_system: str = "KCD") -> dict[str, Any] | None:
        ...

    def get_procedure_code(self, code: str, *, code_system: str = "EDI") -> dict[str, Any] | None:
        ...

    def find_diagnosis_treatment_rule(self, kcd_code: str, edi_code: str) -> dict[str, Any] | None:
        ...

    def find_medical_routing_rule(
        self,
        *,
        reason_code: str,
        routing: str | None = None,
    ) -> dict[str, Any] | None:
        ...


class RuntimeMedicalRegistryService:
    """Build runtime medical evidence from the configured KCD/EDI repository."""

    def __init__(self, registry: RuntimeMedicalRegistry):
        self.registry = registry

    def enrich_claim_payload(self, claim_payload: dict[str, Any]) -> dict[str, Any]:
        enriched = copy.deepcopy(claim_payload)
        claim = enriched.get("claim", {})
        if not isinstance(claim, dict):
            return enriched

        diagnosis_code = str(claim.get("diagnosis_code") or "").strip()
        treatment_code = str(claim.get("treatment_code") or "").strip()
        kcd_row = self.registry.get_medical_code(diagnosis_code) if diagnosis_code else None
        edi_row = self.registry.get_procedure_code(treatment_code) if treatment_code else None
        if not kcd_row and not edi_row:
            return enriched

        evidence = _default_medical_evidence(enriched.get("medical_evidence"))
        mapping = evidence["code_mapping_candidates"]
        if kcd_row:
            _prepend_unique_candidate(
                mapping["kcd"],
                _code_candidate(kcd_row, submitted_code=diagnosis_code, source="runtime_registry:medical_code_registry"),
            )
        if edi_row:
            _prepend_unique_candidate(
                mapping["edi"],
                _code_candidate(edi_row, submitted_code=treatment_code, source="runtime_registry:procedure_code_registry"),
            )

        relationship_rule = None
        if kcd_row and edi_row:
            relationship_rule = self.registry.find_diagnosis_treatment_rule(
                str(kcd_row.get("code")),
                str(edi_row.get("code")),
            )
        if relationship_rule:
            matched_rule = self._routing_rule_from_relationship(relationship_rule)
            if matched_rule:
                _prepend_unique_rule(evidence["insurer_medical_routing_rules"], matched_rule)
            _merge_prior_document_requirements(evidence, relationship_rule)

        mapping["ambiguous"] = bool(mapping.get("ambiguous")) or _candidate_mapping_is_ambiguous(mapping)
        if mapping["ambiguous"] and not mapping.get("ambiguity_reason"):
            mapping["ambiguity_reason"] = "runtime_registry_candidate_margin"

        enriched["medical_evidence"] = evidence
        return enriched

    def _routing_rule_from_relationship(self, relationship_rule: dict[str, Any]) -> dict[str, Any] | None:
        reason_code = str(relationship_rule.get("reason_code") or "")
        routing = str(relationship_rule.get("review_policy") or "continue_claim_review")
        approved_rule = self.registry.find_medical_routing_rule(reason_code=reason_code, routing=routing)
        if approved_rule:
            return _matched_rule(approved_rule, matched=True)
        return {
            "rule_id": f"REGISTRY-{reason_code or 'DIAGNOSIS-TREATMENT'}",
            "rule_version": str(relationship_rule.get("version") or "runtime-registry"),
            "matched": True,
            "routing": routing if routing in _ROUTING_VALUES else "human_review",
            "reason_code": reason_code or "DIAGNOSIS_TREATMENT_REVIEW",
            "confidence": _relationship_confidence(relationship_rule),
            "approval_status": "draft",
            "source": "runtime_registry:diagnosis_treatment_rules",
            "evidence_refs": [],
        }


def _default_medical_evidence(existing: Any) -> dict[str, Any]:
    if isinstance(existing, dict):
        evidence = copy.deepcopy(existing)
    else:
        evidence = {}
    evidence.setdefault("schema_version", "1.0.0")
    mapping = evidence.setdefault("code_mapping_candidates", {})
    if not isinstance(mapping, dict):
        mapping = {}
        evidence["code_mapping_candidates"] = mapping
    mapping.setdefault("kcd", [])
    mapping.setdefault("edi", [])
    mapping.setdefault("ambiguous", False)
    evidence.setdefault(
        "prior_medical_evidence",
        {
            "prior_diagnoses_180d": [],
            "prior_surgeries_365d": [],
            "prior_tests_180d": [],
            "treatment_continuity_days": 0,
            "pre_existing_condition_indicators": [],
        },
    )
    evidence.setdefault("insurer_medical_routing_rules", [])
    evidence.setdefault("synthetic", False)
    return evidence


def _code_candidate(row: dict[str, Any], *, submitted_code: str, source: str) -> dict[str, Any]:
    canonical_code = str(row.get("code") or submitted_code)
    confidence = 0.98 if canonical_code == submitted_code else 0.95
    return {
        "code": canonical_code,
        "code_name": str(row.get("code_name") or canonical_code),
        "confidence": confidence,
        "source": source,
        "registry_version": str(row.get("version") or "unknown"),
        "evidence_document_ids": [],
    }


def _matched_rule(row: dict[str, Any], *, matched: bool) -> dict[str, Any]:
    return {
        "rule_id": str(row["rule_id"]),
        "rule_version": str(row.get("rule_version") or row.get("version") or "unknown"),
        "matched": matched,
        "routing": str(row["routing"]),
        "reason_code": str(row["reason_code"]),
        "confidence": float(row.get("default_confidence", row.get("confidence", 0.8))),
        "approval_status": str(row.get("approval_status", "draft")),
        "source": "runtime_registry:medical_routing_rules",
        "evidence_refs": [],
    }


def _prepend_unique_candidate(candidates: Any, candidate: dict[str, Any]) -> None:
    if not isinstance(candidates, list):
        return
    candidates[:] = [
        item
        for item in candidates
        if not (isinstance(item, dict) and item.get("code") == candidate["code"])
    ]
    candidates.insert(0, candidate)


def _prepend_unique_rule(rules: Any, rule: dict[str, Any]) -> None:
    if not isinstance(rules, list):
        return
    rules[:] = [
        item
        for item in rules
        if not (
            isinstance(item, dict)
            and item.get("rule_id") == rule["rule_id"]
            and item.get("rule_version") == rule["rule_version"]
        )
    ]
    rules.insert(0, rule)


def _candidate_mapping_is_ambiguous(mapping: dict[str, Any]) -> bool:
    return _candidate_list_is_ambiguous(mapping.get("kcd")) or _candidate_list_is_ambiguous(mapping.get("edi"))


def _candidate_list_is_ambiguous(candidates: Any) -> bool:
    if not isinstance(candidates, list):
        return False
    confidences = sorted(
        [float(item.get("confidence", 0)) for item in candidates if isinstance(item, dict)],
        reverse=True,
    )
    return len(confidences) > 1 and confidences[0] - confidences[1] < 0.15


def _relationship_confidence(rule: dict[str, Any]) -> float:
    if rule.get("relationship") == "compatible" and rule.get("medical_necessity_level") == "supported":
        return 0.86
    if rule.get("relationship") == "compatible":
        return 0.8
    return 0.72


def _merge_prior_document_requirements(evidence: dict[str, Any], relationship_rule: dict[str, Any]) -> None:
    required_documents = relationship_rule.get("required_documents")
    if not required_documents:
        return
    rules = evidence.get("insurer_medical_routing_rules")
    if not isinstance(rules, list):
        return
    # Document requirements are preserved in rule evidence refs only when the input schema permits it.


_ROUTING_VALUES = {"continue_claim_review", "request_documents", "human_review"}
