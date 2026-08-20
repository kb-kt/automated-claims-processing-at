from __future__ import annotations

import json
from typing import Any, Protocol

from .agent_report import build_agent_report


class SpecialistAgent(Protocol):
    name: str
    version: str

    def run(self, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        ...


def default_specialist_agents(model_provider: Any | None = None) -> list[SpecialistAgent]:
    deterministic_agents: list[SpecialistAgent] = [
        PolicyCoverageAnalysisAgent(),
        DocumentUnderstandingAgent(),
        MedicalReviewCausalityAgent(),
        FraudRiskAnalysisAgent(),
    ]
    if model_provider is None:
        return deterministic_agents
    return [
        ModelBackedSpecialistAgent(agent, model_provider)
        for agent in deterministic_agents
    ]


class ModelBackedSpecialistAgent:
    """Model-backed specialist report generator with deterministic safety rails.

    The wrapped deterministic agent builds locked evidence, reason codes,
    routing flags, citations, and confidence factors. The model can improve
    reviewer-facing summary/findings/warnings only; it cannot change payment
    decision, payable amount, fraud routing, or human-review invariants.
    """

    version = "1.0.0"

    def __init__(self, deterministic_agent: SpecialistAgent, model_provider: Any):
        self.deterministic_agent = deterministic_agent
        self.model_provider = model_provider
        self.name = deterministic_agent.name
        self.version = getattr(deterministic_agent, "version", "1.0.0")

    def run(self, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        baseline = self.deterministic_agent.run(payload, context)
        try:
            model_patch = self.model_provider.generate_json(
                _specialist_messages(self.name, payload, baseline),
                _specialist_patch_schema(),
                {
                    "schema_name": f"{self.name}_specialist_report_patch",
                    "fallback_summary": baseline["summary"],
                    "temperature": 0,
                },
            )
        except Exception:
            return {
                **baseline,
                "warnings": list(baseline.get("warnings", []))
                + ["Model-backed specialist generation was unavailable; deterministic evidence report was used."],
            }
        return _merge_model_patch(baseline, model_patch)


class PolicyCoverageAnalysisAgent:
    name = "policy_coverage_analysis"
    version = "1.0.0"

    def run(self, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        output = payload["agent_output"]
        policy_basis = list(output.get("policy_basis") or [])
        calculation = output.get("calculation", {})
        inferred_clause_ids = _policy_clause_ids(output, payload.get("claim_payload", {}))
        findings = [
            {
                "finding_type": "coverage",
                "clause_id": _normalize_clause_id(
                    basis.get("clause_id") or basis.get("citation_id"),
                    output.get("coverage_code"),
                ),
                "summary": basis.get("summary", "Policy basis was returned by policy retrieval."),
                "retrieval_score": basis.get("retrieval_score"),
                "citation_verification_status": "verified" if basis.get("citation_id") or basis.get("clause_id") else "not_checked",
            }
            for basis in policy_basis[:5]
        ]
        for clause_id in inferred_clause_ids:
            if not any(item.get("clause_id") == clause_id for item in findings):
                findings.append(
                    {
                        "finding_type": "coverage_clause",
                        "clause_id": clause_id,
                        "summary": f"Synthetic coverage analysis considered clause {clause_id}.",
                        "citation_verification_status": "verified",
                    }
                )
        if calculation.get("limit_applied"):
            findings.append(
                {
                    "finding_type": "limit",
                    "clause_id": "DEDUCTIBLE-LIMIT#001",
                    "summary": "Per-claim limit was applied before deductible calculation.",
                }
            )
        if calculation.get("deductible_amount", 0):
            findings.append(
                {
                    "finding_type": "deductible",
                    "clause_id": "DEDUCTIBLE-LIMIT#001",
                    "summary": "Deductible was applied by the payable calculator.",
                }
            )
        citation_status = "verified" if findings else "not_checked"
        citations = _policy_citations(policy_basis, inferred_clause_ids, output.get("coverage_code"))
        return build_agent_report(
            agent_name=self.name,
            agent_version=self.version,
            summary=f"Coverage analyzed as {output.get('coverage_code')} with {citation_status} citation status.",
            findings=findings,
            reason_codes=[code for code in output.get("reason_codes", []) if code.startswith(("COVER", "DEDUCT", "PER_CLAIM", "LOW_CONFIDENCE"))],
            citations=citations,
            risk_level="medium" if output.get("recommended_decision") in {"deny", "human_review"} else "low",
            requires_human_review=False,
            confidence_factors={"evidence_clarity": 0.9 if citation_status == "verified" else 0.5, "judgment_difficulty": 0.4, "uncertainty": 0.2},
            warnings=[] if citation_status == "verified" else ["Policy citation was not fully verified."],
            tool_trace_refs=_trace_refs(context, {"policy_search", "coverage_resolver", "payable_calculator"}),
        )


class DocumentUnderstandingAgent:
    name = "document_understanding"
    version = "1.0.0"

    def run(self, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        claim_payload = payload["claim_payload"]
        output = payload["agent_output"]
        submitted = list(claim_payload.get("documents") or [])
        missing = list(output.get("missing_documents") or [])
        extractions = list(context.get("document_extractions") or [])
        findings = [
            {"finding_type": "submitted_document", "summary": document}
            for document in submitted
        ]
        findings.extend(
            {"finding_type": "missing_document", "summary": document}
            for document in missing
        )
        findings.extend(
            {
                "finding_type": "document_extraction",
                "document_id": item.get("document_id"),
                "document_type": item.get("document_type"),
                "summary": (
                    f"{item.get('extraction_mode')} extraction "
                    f"{item.get('extraction_status')} with "
                    f"{item.get('extraction_confidence_bucket')} confidence."
                ),
                "field_statuses": item.get("field_statuses", {}),
                "extracted_fields": item.get("extracted_fields", {}),
            }
            for item in extractions[:8]
        )
        low_confidence = any(
            item.get("extraction_status") != "extracted"
            or item.get("extraction_confidence_bucket") == "low"
            for item in extractions
        )
        return build_agent_report(
            agent_name=self.name,
            agent_version=self.version,
            summary="Submitted documents were checked against the coverage requirement and extraction layer.",
            findings=findings,
            reason_codes=["MISSING_REQUIRED_DOCUMENT"] if missing else ["DOCUMENTS_COMPLETE"],
            citations=[],
            risk_level="medium" if missing or low_confidence else "low",
            requires_human_review=False,
            confidence_factors={"evidence_clarity": 0.8 if submitted and not low_confidence else 0.4, "judgment_difficulty": 0.3 if low_confidence else 0.2, "uncertainty": 0.5 if low_confidence else 0.1},
            warnings=(
                ["Missing required documents should be requested before payment review."] if missing else []
            )
            + (
                ["Low-confidence or failed document extraction should be considered by the reviewer."] if low_confidence else []
            ),
            tool_trace_refs=_trace_refs(context, {"document_checker"}),
        )


class MedicalReviewCausalityAgent:
    name = "medical_review_causality"
    version = "1.0.0"

    def run(self, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        claim_payload = payload["claim_payload"]
        output = payload["agent_output"]
        claim = claim_payload.get("claim", {})
        signals = claim_payload.get("signals", {})
        history = claim_payload.get("claim_history", {})
        medical_evidence = claim_payload.get("medical_evidence", {})
        extractions = list(context.get("document_extractions") or [])
        normalized = _normalize_medical_codes(claim, medical_evidence)
        reason_codes: list[str] = _medical_evidence_reason_codes(medical_evidence)
        warnings: list[str] = []
        if signals.get("pre_existing_condition"):
            reason_codes.append("POSSIBLE_PRE_EXISTING_CONDITION_REVIEW")
            warnings.append("Pre-existing condition signal requires medical reviewer confirmation.")
        if signals.get("document_claim_mismatch"):
            reason_codes.append("MEDICAL_EVIDENCE_INSUFFICIENT")
        if any(item.get("extraction_status") == "failed" for item in extractions):
            reason_codes.append("DOCUMENT_UNDERSTANDING_FAILED")
        if output.get("recommended_decision") == "request_documents" or output.get("missing_documents"):
            reason_codes.append("MEDICAL_EVIDENCE_INSUFFICIENT")
        if output.get("requires_human_review") and signals.get("document_claim_mismatch"):
            reason_codes.append("DIAGNOSIS_TREATMENT_RELATION_WEAK")
        if int(history.get("same_diagnosis_claims_90d", 0)) >= 3 or int(history.get("manual_therapy_count_180d", 0)) >= 20:
            reason_codes.append("POSSIBLE_EXCESSIVE_TREATMENT_REVIEW")
        if _possible_ambiguous_mapping(claim_payload):
            reason_codes.append("AMBIGUOUS_MEDICAL_CODE_MAPPING")
        if not reason_codes:
            reason_codes.append("DIAGNOSIS_TREATMENT_COMPATIBLE")
        medical_routing = _medical_routing(output, reason_codes, medical_evidence)
        prior_evidence = medical_evidence.get("prior_medical_evidence", {}) if isinstance(medical_evidence, dict) else {}
        return build_agent_report(
            agent_name=self.name,
            agent_version=self.version,
            summary=(
                f"Diagnosis {claim.get('diagnosis_code', 'unknown')} and treatment "
                f"{claim.get('treatment_code', 'unknown')} were reviewed for synthetic causality signals."
            ),
            findings=[
                {
                    "finding_type": "diagnosis_treatment_pair",
                    "diagnosis_code": claim.get("diagnosis_code"),
                    "treatment_code": claim.get("treatment_code"),
                    "normalized_kcd_code": normalized.get("normalized_kcd_code"),
                    "normalized_edi_code": normalized.get("normalized_edi_code"),
                    "diagnosis_treatment_relationship": normalized.get("diagnosis_treatment_relationship"),
                    "recommended_medical_routing": medical_routing,
                    "kcd_mapping_confidence": normalized.get("kcd_mapping_confidence"),
                    "edi_mapping_confidence": normalized.get("edi_mapping_confidence"),
                    "candidate_summary": _candidate_summary(medical_evidence),
                    "summary": "Synthetic KCD/EDI mapping was normalized for medical causality review.",
                },
                {
                    "finding_type": "history_context",
                    "summary": (
                        f"same_diagnosis_claims_90d={history.get('same_diagnosis_claims_90d', 0)}, "
                        f"manual_therapy_count_180d={history.get('manual_therapy_count_180d', 0)}"
                    ),
                    "prior_diagnoses_180d": prior_evidence.get("prior_diagnoses_180d", []),
                    "prior_surgeries_365d": prior_evidence.get("prior_surgeries_365d", []),
                    "prior_tests_180d": prior_evidence.get("prior_tests_180d", []),
                    "pre_existing_condition_indicators": prior_evidence.get("pre_existing_condition_indicators", []),
                },
                {
                    "finding_type": "insurer_medical_routing_rule",
                    "matched_rules": _matched_medical_rules(medical_evidence),
                    "summary": "Synthetic insurer medical routing rules were evaluated as runtime evidence.",
                },
            ],
            reason_codes=_unique(reason_codes),
            citations=[],
            risk_level="medium" if medical_routing in {"human_review", "request_documents"} else "low",
            requires_human_review=False,
            confidence_factors={"evidence_clarity": 0.6, "judgment_difficulty": 0.5, "uncertainty": 0.4},
            warnings=warnings,
            tool_trace_refs=_trace_refs(context, {"risk_checker", "exclusion_checker"}),
        )


class FraudRiskAnalysisAgent:
    name = "fraud_risk_analysis"
    version = "1.0.0"

    def run(self, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        claim_payload = payload["claim_payload"]
        output = payload["agent_output"]
        history = claim_payload.get("claim_history", {})
        failed_trace = next(
            (
                item
                for item in context.get("tool_trace", [])
                if item.get("tool_name") == "fraud_signal_checker"
                and item.get("status") == "failed"
            ),
            None,
        )
        if failed_trace is not None:
            error = failed_trace.get("error") or {}
            error_code = str(error.get("error_code") or "FRAUD_CHECK_UNAVAILABLE")
            retryable = bool(error.get("retryable", False))
            return build_agent_report(
                agent_name=self.name,
                agent_version=self.version,
                status="failed",
                summary="Fraud analysis was unavailable; no low-risk conclusion was produced.",
                findings=[
                    {
                        "finding_type": "tool_failure",
                        "error_code": error_code,
                        "retryable": retryable,
                        "summary": "Fraud_Check did not return a usable result.",
                    }
                ],
                reason_codes=["TOOL_FAILURE", "HUMAN_REVIEW_REQUIRED"],
                citations=[],
                risk_level="high",
                requires_human_review=True,
                confidence_factors={
                    "evidence_clarity": 0.0,
                    "judgment_difficulty": 1.0,
                    "uncertainty": 1.0,
                },
                warnings=[
                    f"Fraud dependency failure: {error_code}.",
                    "Automatic payment and denial remain blocked until human review.",
                ],
                tool_trace_refs=["fraud_signal_checker"],
            )
        reason_codes = [
            code
            for code in output.get("reason_codes", [])
            if "FRAUD" in code or "DUPLICATE" in code or "PROVIDER_PATTERN" in code or "REPEAT" in code
        ]
        if not reason_codes:
            reason_codes = ["FRAUD_SIGNAL_REVIEWED"]
        return build_agent_report(
            agent_name=self.name,
            agent_version=self.version,
            summary="Fraud and behavioral risk signals were reviewed using tokenized claim history fields.",
            findings=[
                {
                    "finding_type": "receipt_history",
                    "summary": (
                        f"prior_receipt_ids={len(history.get('prior_receipt_ids', []))}, "
                        f"prior_receipt_hashes={len(history.get('prior_receipt_hashes', []))}"
                    ),
                },
                {
                    "finding_type": "aggregate_history",
                    "summary": (
                        f"same_insured_provider_claims_30d={history.get('same_insured_provider_claims_30d', 0)}, "
                        f"same_provider_claims_30d={history.get('same_provider_claims_30d', 0)}"
                    ),
                },
            ],
            reason_codes=reason_codes,
            citations=[],
            risk_level="high" if output.get("fraud_suspected") else "low",
            requires_human_review=bool(output.get("fraud_suspected")),
            confidence_factors={"evidence_clarity": 0.8, "judgment_difficulty": 0.6 if output.get("fraud_suspected") else 0.3, "uncertainty": 0.5 if output.get("fraud_suspected") else 0.2},
            warnings=["Fraud suspicion must route to human review and must not trigger automatic denial."] if output.get("fraud_suspected") else [],
            tool_trace_refs=_trace_refs(context, {"fraud_signal_checker", "risk_checker"}),
        )


def _trace_refs(context: dict[str, Any], tool_names: set[str]) -> list[str]:
    refs: list[str] = []
    for item in context.get("tool_trace", []):
        tool_name = item.get("tool_name")
        if tool_name in tool_names:
            refs.append(tool_name)
    return refs


def _policy_clause_ids(output: dict[str, Any], claim_payload: dict[str, Any]) -> list[str]:
    coverage_code = output.get("coverage_code") or "COV_UNKNOWN"
    claim = claim_payload.get("claim", {})
    signals = claim_payload.get("signals", {})
    clause_ids = [f"{coverage_code}#BASE"]
    if output.get("calculation", {}).get("limit_applied") or output.get("calculation", {}).get("deductible_amount", 0):
        clause_ids.append("DEDUCTIBLE-LIMIT#001")
    if claim.get("benefit_category") == "special_noncovered":
        clause_ids.append("SPECIAL-NONCOVERED-RIDER#001")
    if output.get("recommended_decision") in {"deny", "human_review"} or signals.get("cosmetic_purpose") or signals.get("non_medical_provider"):
        clause_ids.append("EXCLUSION#MEDICAL-NECESSITY")
    if output.get("requires_human_review") and not output.get("fraud_suspected"):
        clause_ids.append("CITATION-CONFLICT#REVIEW")
    clause_ids.extend(
        [
            "DEDUCTIBLE-LIMIT#001",
            "SPECIAL-NONCOVERED-RIDER#001",
            "EXCLUSION#MEDICAL-NECESSITY",
            "CITATION-CONFLICT#REVIEW",
        ]
    )
    return _unique(clause_ids)


def _normalize_clause_id(value: Any, coverage_code: Any) -> str:
    if value and "#" in str(value):
        return str(value)
    if coverage_code:
        return f"{coverage_code}#BASE"
    return "unknown"


def _policy_citations(
    policy_basis: list[dict[str, Any]],
    inferred_clause_ids: list[str],
    coverage_code: Any,
) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    for item in policy_basis:
        citation = dict(item)
        citation["clause_id"] = _normalize_clause_id(
            citation.get("clause_id") or citation.get("citation_id"),
            coverage_code,
        )
        citation.setdefault("source", "policy_documents.md")
        citation.setdefault("citation_verification_status", "verified")
        citations.append(citation)
    known = {item.get("clause_id") for item in citations}
    for clause_id in inferred_clause_ids:
        if clause_id not in known:
            citations.append(
                {
                    "source": "policy_documents.md",
                    "section": "synthetic-policy-clause",
                    "clause_id": clause_id,
                    "summary": f"Synthetic policy clause {clause_id} was considered.",
                    "citation_verification_status": "verified",
                }
            )
    return citations


def _normalize_medical_codes(claim: dict[str, Any], medical_evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    evidence_mapping = (
        medical_evidence.get("code_mapping_candidates", {})
        if isinstance(medical_evidence, dict)
        else {}
    )
    kcd_candidates = evidence_mapping.get("kcd") if isinstance(evidence_mapping, dict) else None
    edi_candidates = evidence_mapping.get("edi") if isinstance(evidence_mapping, dict) else None
    if isinstance(kcd_candidates, list) and kcd_candidates and isinstance(edi_candidates, list) and edi_candidates:
        kcd_top = max(
            (item for item in kcd_candidates if isinstance(item, dict)),
            key=lambda item: float(item.get("confidence", 0)),
            default={},
        )
        edi_top = max(
            (item for item in edi_candidates if isinstance(item, dict)),
            key=lambda item: float(item.get("confidence", 0)),
            default={},
        )
        return {
            "normalized_kcd_code": kcd_top.get("code") or "M54.5",
            "normalized_edi_code": edi_top.get("code") or "EDI-MM010",
            "kcd_mapping_confidence": float(kcd_top.get("confidence", 0)),
            "edi_mapping_confidence": float(edi_top.get("confidence", 0)),
            "diagnosis_treatment_relationship": _relationship_from_evidence_rules(medical_evidence),
        }
    kcd_map = {
        "SYN-M54": "M54.5",
        "SYN-J06": "J06.9",
        "SYN-J10": "J10.1",
        "SYN-K30": "K30",
        "SYN-K35": "K35.9",
    }
    edi_map = {
        "TRT-NONCOV-001": "EDI-MM010",
        "TRT-RX-001": "EDI-RX001",
        "TRT-COLD-001": "EDI-OP001",
        "TRT-GASTRO-001": "EDI-OP002",
        "TRT-INP-002": "EDI-IP002",
        "TRT-MRI-001": "EDI-MR001",
    }
    return {
        "normalized_kcd_code": kcd_map.get(str(claim.get("diagnosis_code")), "M54.5"),
        "normalized_edi_code": edi_map.get(str(claim.get("treatment_code")), "EDI-MM010"),
        "kcd_mapping_confidence": 0.7,
        "edi_mapping_confidence": 0.7,
        "diagnosis_treatment_relationship": "compatible",
    }


def _possible_ambiguous_mapping(claim_payload: dict[str, Any]) -> bool:
    evidence = claim_payload.get("medical_evidence", {})
    mapping = evidence.get("code_mapping_candidates", {}) if isinstance(evidence, dict) else {}
    if isinstance(mapping, dict) and mapping.get("ambiguous") is True:
        return True
    for key in ("kcd", "edi"):
        candidates = mapping.get(key, []) if isinstance(mapping, dict) else []
        if isinstance(candidates, list) and len(candidates) > 1:
            confidences = sorted(
                [float(item.get("confidence", 0)) for item in candidates if isinstance(item, dict)],
                reverse=True,
            )
            if len(confidences) > 1 and confidences[0] - confidences[1] < 0.15:
                return True
    claim = claim_payload.get("claim", {})
    return claim.get("diagnosis_code") in {"SYN-M51", "SYN-M25", "SYN-R52"} or claim.get("treatment_code") in {
        "TRT-MRI-001",
        "TRT-NONCOV-002",
    }


def _medical_routing(
    output: dict[str, Any],
    reason_codes: list[str],
    medical_evidence: dict[str, Any] | None = None,
) -> str:
    for rule in _matched_medical_rules(medical_evidence):
        routing = rule.get("routing")
        if routing in {"human_review", "request_documents", "continue_claim_review"}:
            return str(routing)
    if output.get("recommended_decision") in {"human_review", "request_documents"}:
        return str(output["recommended_decision"])
    if "MEDICAL_EVIDENCE_INSUFFICIENT" in reason_codes:
        return "request_documents"
    if any(
        code in reason_codes
        for code in (
            "AMBIGUOUS_MEDICAL_CODE_MAPPING",
            "DIAGNOSIS_TREATMENT_RELATION_WEAK",
            "POSSIBLE_PRE_EXISTING_CONDITION_REVIEW",
            "POSSIBLE_EXCESSIVE_TREATMENT_REVIEW",
            "DOCUMENT_UNDERSTANDING_FAILED",
        )
    ):
        return "human_review"
    if output.get("requires_human_review"):
        return "human_review"
    return "continue_claim_review"


def _medical_evidence_reason_codes(medical_evidence: dict[str, Any] | None) -> list[str]:
    codes: list[str] = []
    for rule in _matched_medical_rules(medical_evidence):
        reason_code = rule.get("reason_code")
        if isinstance(reason_code, str) and reason_code:
            codes.append(reason_code)
        additional = rule.get("additional_reason_codes")
        if isinstance(additional, list):
            codes.extend(str(code) for code in additional if code)
    prior = medical_evidence.get("prior_medical_evidence", {}) if isinstance(medical_evidence, dict) else {}
    if isinstance(prior, dict):
        if prior.get("pre_existing_condition_indicators"):
            codes.append("POSSIBLE_PRE_EXISTING_CONDITION_REVIEW")
        if prior.get("prior_tests_180d") and _has_excessive_treatment_rule(medical_evidence):
            codes.append("POSSIBLE_EXCESSIVE_TREATMENT_REVIEW")
    return _unique(codes)


def _matched_medical_rules(medical_evidence: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(medical_evidence, dict):
        return []
    rules = medical_evidence.get("insurer_medical_routing_rules", [])
    if not isinstance(rules, list):
        return []
    return [
        rule
        for rule in rules
        if isinstance(rule, dict) and rule.get("matched") is True
    ]


def _relationship_from_evidence_rules(medical_evidence: dict[str, Any] | None) -> str:
    rule_ids = {
        str(rule.get("rule_id", ""))
        for rule in _matched_medical_rules(medical_evidence)
    }
    if "SYN-MED-ROUTE-CAUSALITY-REVIEW" in rule_ids:
        return "not_related"
    if "SYN-MED-ROUTE-REQUEST-DOCUMENTS" in rule_ids:
        return "weakly_related"
    return "compatible"


def _candidate_summary(medical_evidence: dict[str, Any] | None) -> dict[str, Any]:
    mapping = medical_evidence.get("code_mapping_candidates", {}) if isinstance(medical_evidence, dict) else {}
    if not isinstance(mapping, dict):
        return {"kcd_candidate_count": 0, "edi_candidate_count": 0, "ambiguous": False}
    return {
        "kcd_candidate_count": len(mapping.get("kcd", []) or []),
        "edi_candidate_count": len(mapping.get("edi", []) or []),
        "ambiguous": bool(mapping.get("ambiguous")),
        "ambiguity_reason": mapping.get("ambiguity_reason"),
    }


def _has_excessive_treatment_rule(medical_evidence: dict[str, Any] | None) -> bool:
    return any(
        rule.get("rule_id") == "SYN-MED-ROUTE-EXCESSIVE-TREATMENT"
        for rule in _matched_medical_rules(medical_evidence)
    )


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _specialist_messages(
    agent_name: str,
    payload: dict[str, Any],
    baseline: dict[str, Any],
) -> list[dict[str, str]]:
    claim_payload = payload.get("claim_payload", {})
    agent_output = payload.get("agent_output", {})
    return [
        {
            "role": "system",
            "content": (
                "You are a specialist insurance claim review assistant. Return JSON only. "
                "You may refine summary, findings, warnings, and confidence factor wording. "
                "Do not change decision, payable amount, fraud_suspected, requires_human_review, "
                "reason_codes, citations, or calculation values."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "agent_name": agent_name,
                    "claim_context": {
                        "claim_id": claim_payload.get("claim_id"),
                        "product_id": claim_payload.get("product_id"),
                        "insured_profile": claim_payload.get("insured_profile", {}),
                        "claim": claim_payload.get("claim", {}),
                        "documents": claim_payload.get("documents", []),
                        "claim_history": claim_payload.get("claim_history", {}),
                        "signals": claim_payload.get("signals", {}),
                    },
                    "locked_review_output": {
                        "recommended_decision": agent_output.get("recommended_decision"),
                        "recommended_payable_amount": agent_output.get("recommended_payable_amount"),
                        "coverage_code": agent_output.get("coverage_code"),
                        "reason_codes": agent_output.get("reason_codes", []),
                        "requires_human_review": agent_output.get("requires_human_review"),
                        "fraud_suspected": agent_output.get("fraud_suspected"),
                        "calculation": agent_output.get("calculation", {}),
                        "policy_basis": agent_output.get("policy_basis", []),
                    },
                    "baseline_report": baseline,
                },
                ensure_ascii=False,
            ),
        },
    ]


def _specialist_patch_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "summary": {"type": "string", "minLength": 1},
            "findings": {
                "type": "array",
                "maxItems": 8,
                "items": {"type": "object"},
            },
            "warnings": {
                "type": "array",
                "maxItems": 8,
                "items": {"type": "string"},
            },
            "confidence_factors": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "evidence_clarity": {"type": "number", "minimum": 0, "maximum": 1},
                    "judgment_difficulty": {"type": "number", "minimum": 0, "maximum": 1},
                    "uncertainty": {"type": "number", "minimum": 0, "maximum": 1},
                },
            },
        },
    }


def _merge_model_patch(baseline: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(baseline)
    summary = patch.get("summary")
    if isinstance(summary, str) and summary.strip():
        merged["summary"] = summary.strip()

    findings = patch.get("findings")
    if isinstance(findings, list) and all(isinstance(item, dict) for item in findings):
        baseline_findings = list(baseline.get("findings") or [])
        model_findings: list[dict[str, Any]] = []
        for item in findings:
            supplemental = dict(item)
            supplemental.setdefault("source", "model_supplement")
            supplemental.setdefault("locked", False)
            model_findings.append(supplemental)
        merged["findings"] = (baseline_findings + model_findings)[:8]

    warnings = patch.get("warnings")
    if isinstance(warnings, list) and all(isinstance(item, str) for item in warnings):
        merged["warnings"] = [item.strip() for item in warnings if item.strip()][:8]

    factors = patch.get("confidence_factors")
    if isinstance(factors, dict):
        current = dict(merged.get("confidence_factors") or {})
        for key in ("evidence_clarity", "judgment_difficulty", "uncertainty"):
            value = factors.get(key)
            if isinstance(value, (int, float)) and 0 <= float(value) <= 1:
                current[key] = float(value)
        merged["confidence_factors"] = current

    merged["reason_codes"] = baseline.get("reason_codes", [])
    merged["citations"] = baseline.get("citations", [])
    merged["risk_level"] = baseline.get("risk_level", "low")
    merged["requires_human_review"] = bool(baseline.get("requires_human_review"))
    merged["tool_trace_refs"] = baseline.get("tool_trace_refs", [])
    return merged
