from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .schemas import GenerationConfig, Product


MEDICAL_REVIEW_SCENARIOS = [
    "clear_kcd_mapping",
    "ambiguous_kcd_mapping_human_review",
    "clear_edi_mapping",
    "ambiguous_edi_mapping_human_review",
    "diagnosis_treatment_compatible",
    "diagnosis_treatment_weakly_related",
    "diagnosis_treatment_unrelated",
    "possible_pre_existing_condition",
    "possible_excessive_treatment",
    "high_cost_sufficient_evidence",
    "high_cost_insufficient_evidence",
    "document_understanding_failure",
]

POLICY_COVERAGE_SCENARIOS = [
    "standard_covered_clause_match",
    "special_noncovered_rider_match",
    "exclusion_clause_review",
    "deductible_and_limit_clause_match",
    "unclear_policy_citation_human_review",
]


@dataclass
class MedicalArtifactBundle:
    medical_code_registry: list[dict[str, Any]]
    edi_code_registry: list[dict[str, Any]]
    diagnosis_treatment_rules: list[dict[str, Any]]
    insurer_medical_routing_rules: list[dict[str, Any]]
    medical_labels_dev: list[dict[str, Any]]
    medical_labels_eval: list[dict[str, Any]]
    code_mapping_labels_dev: list[dict[str, Any]]
    code_mapping_labels_eval: list[dict[str, Any]]
    policy_coverage_labels_dev: list[dict[str, Any]]
    policy_coverage_labels_eval: list[dict[str, Any]]
    medical_document_metadata_dev: list[dict[str, Any]] = field(default_factory=list)
    medical_document_metadata_eval: list[dict[str, Any]] = field(default_factory=list)
    medical_context_seed_dev: list[dict[str, Any]] = field(default_factory=list)
    medical_context_seed_eval: list[dict[str, Any]] = field(default_factory=list)
    report: dict[str, Any] = field(default_factory=dict)


def build_medical_artifacts(
    *,
    config: GenerationConfig,
    product: Product,
    dev_claims: list[dict],
    eval_claims: list[dict],
    document_metadata_dev: list[dict],
    document_metadata_eval: list[dict],
) -> MedicalArtifactBundle:
    if not config.medical_generation.get("enabled", True):
        return MedicalArtifactBundle(
            medical_code_registry=[],
            edi_code_registry=[],
            diagnosis_treatment_rules=[],
            insurer_medical_routing_rules=[],
            medical_labels_dev=[],
            medical_labels_eval=[],
            code_mapping_labels_dev=[],
            code_mapping_labels_eval=[],
            policy_coverage_labels_dev=[],
            policy_coverage_labels_eval=[],
        )

    registries = _registries()
    rules = _diagnosis_treatment_rules()
    insurer_rules = _insurer_medical_routing_rules()
    dev = _split_artifacts(
        split="dev",
        product=product,
        claims=dev_claims,
        document_metadata=document_metadata_dev,
        rules=rules,
        insurer_rules=insurer_rules,
    )
    eval_ = _split_artifacts(
        split="eval",
        product=product,
        claims=eval_claims,
        document_metadata=document_metadata_eval,
        rules=rules,
        insurer_rules=insurer_rules,
    )
    bundle = MedicalArtifactBundle(
        medical_code_registry=registries["medical_code_registry"],
        edi_code_registry=registries["edi_code_registry"],
        diagnosis_treatment_rules=rules,
        insurer_medical_routing_rules=insurer_rules,
        medical_labels_dev=dev["medical_labels"],
        medical_labels_eval=eval_["medical_labels"],
        code_mapping_labels_dev=dev["code_mapping_labels"],
        code_mapping_labels_eval=eval_["code_mapping_labels"],
        policy_coverage_labels_dev=dev["policy_coverage_labels"],
        policy_coverage_labels_eval=eval_["policy_coverage_labels"],
        medical_document_metadata_dev=dev["medical_document_metadata"],
        medical_document_metadata_eval=eval_["medical_document_metadata"],
        medical_context_seed_dev=dev["medical_context_seed"],
        medical_context_seed_eval=eval_["medical_context_seed"],
    )
    bundle.report = _medical_report(bundle)
    return bundle


def _registries() -> dict[str, list[dict[str, Any]]]:
    return {
        "medical_code_registry": [
            _kcd("SYN-M54", "M54.5", "Low back pain", "musculoskeletal", ["back pain", "lumbago", "low back pain"]),
            _kcd("SYN-J06", "J06.9", "Acute upper respiratory infection", "respiratory", ["cold", "URI"]),
            _kcd("SYN-J10", "J10.1", "Influenza with respiratory manifestations", "respiratory", ["flu", "influenza"]),
            _kcd("SYN-K30", "K30", "Functional dyspepsia", "digestive", ["dyspepsia", "indigestion"]),
            _kcd("SYN-K35", "K35.9", "Acute appendicitis", "digestive", ["appendicitis"]),
            _kcd("SYN-S83", "S83.5", "Sprain and strain involving knee ligament", "injury", ["knee sprain"]),
        ],
        "edi_code_registry": [
            _edi("TRT-NONCOV-001", "EDI-MM010", "Manual therapy session", "manual_therapy", "special_noncovered"),
            _edi("TRT-COLD-001", "EDI-OP001", "Outpatient consultation", "consultation", "covered"),
            _edi("TRT-GASTRO-001", "EDI-OP002", "Outpatient digestive treatment", "consultation", "covered"),
            _edi("TRT-INP-002", "EDI-IP002", "Inpatient surgical treatment", "inpatient_procedure", "covered"),
            _edi("TRT-RX-001", "EDI-RX001", "Prescription dispensing", "pharmacy", "covered"),
            _edi("TRT-MRI-001", "EDI-MR001", "MRI scan", "imaging", "special_noncovered"),
        ],
    }


def _kcd(source_code: str, code: str, name: str, category: str, aliases: list[str]) -> dict[str, Any]:
    return {
        "code_system": "KCD",
        "source_synthetic_code": source_code,
        "code": code,
        "code_name": name,
        "parent_code": code.split(".")[0],
        "chapter": category,
        "category": category,
        "valid_from": "2026-01-01",
        "valid_to": None,
        "version": "synthetic-kcd-1.0.0",
        "aliases": aliases,
        "synthetic": True,
    }


def _edi(source_code: str, code: str, name: str, group: str, benefit_category: str) -> dict[str, Any]:
    return {
        "code_system": "EDI",
        "source_synthetic_code": source_code,
        "code": code,
        "code_name": name,
        "procedure_group": group,
        "benefit_category": benefit_category,
        "valid_from": "2026-01-01",
        "valid_to": None,
        "version": "synthetic-edi-1.0.0",
        "aliases": [name.lower()],
        "synthetic": True,
    }


def _diagnosis_treatment_rules() -> list[dict[str, Any]]:
    rows = [
        ("M54.5", "EDI-MM010", "compatible", "partially_supported", "continue_claim_review", "DIAGNOSIS_TREATMENT_COMPATIBLE"),
        ("J06.9", "EDI-RX001", "compatible", "supported", "continue_claim_review", "DIAGNOSIS_TREATMENT_COMPATIBLE"),
        ("J10.1", "EDI-OP001", "compatible", "supported", "continue_claim_review", "DIAGNOSIS_TREATMENT_COMPATIBLE"),
        ("K30", "EDI-OP002", "compatible", "supported", "continue_claim_review", "DIAGNOSIS_TREATMENT_COMPATIBLE"),
        ("K35.9", "EDI-IP002", "compatible", "supported", "continue_claim_review", "DIAGNOSIS_TREATMENT_COMPATIBLE"),
        ("M54.5", "EDI-MR001", "weakly_related", "insufficient_evidence", "request_documents", "MEDICAL_EVIDENCE_INSUFFICIENT"),
        ("J06.9", "EDI-MM010", "not_related", "unsupported", "human_review", "DIAGNOSIS_TREATMENT_RELATION_WEAK"),
    ]
    return [
        {
            "kcd_code": kcd,
            "edi_code": edi,
            "relationship": relationship,
            "medical_necessity_level": necessity,
            "required_documents": _required_medical_docs(relationship, necessity),
            "age_min": None,
            "age_max": None,
            "sex_constraint": "any",
            "review_policy": review_policy,
            "reason_code": reason_code,
            "version": "synthetic-medical-rule-1.0.0",
            "synthetic": True,
        }
        for kcd, edi, relationship, necessity, review_policy, reason_code in rows
    ]


def _insurer_medical_routing_rules() -> list[dict[str, Any]]:
    rows = [
        (
            "SYN-MED-ROUTE-CONTINUE",
            "Continue claim review when KCD/EDI mapping is confident and diagnosis-treatment relation is compatible.",
            "continue_claim_review",
            "DIAGNOSIS_TREATMENT_COMPATIBLE",
            0.82,
        ),
        (
            "SYN-MED-ROUTE-AMBIGUOUS-CODE",
            "Route to medical reviewer when candidate KCD/EDI confidence margin is below the configured threshold.",
            "human_review",
            "AMBIGUOUS_MEDICAL_CODE_MAPPING",
            0.88,
        ),
        (
            "SYN-MED-ROUTE-PREEXISTING",
            "Route to medical reviewer when prior diagnosis, test, or continuity evidence suggests possible pre-existing condition review.",
            "human_review",
            "POSSIBLE_PRE_EXISTING_CONDITION_REVIEW",
            0.88,
        ),
        (
            "SYN-MED-ROUTE-EXCESSIVE-TREATMENT",
            "Route to medical reviewer when repeated same-diagnosis or manual-therapy evidence exceeds synthetic insurer threshold.",
            "human_review",
            "POSSIBLE_EXCESSIVE_TREATMENT_REVIEW",
            0.88,
        ),
        (
            "SYN-MED-ROUTE-REQUEST-DOCUMENTS",
            "Request additional documents when medical necessity is insufficient or diagnosis-treatment relation needs supporting evidence.",
            "request_documents",
            "MEDICAL_EVIDENCE_INSUFFICIENT",
            0.84,
        ),
        (
            "SYN-MED-ROUTE-CAUSALITY-REVIEW",
            "Route to medical reviewer when diagnosis and treatment appear weakly related or unrelated.",
            "human_review",
            "DIAGNOSIS_TREATMENT_RELATION_WEAK",
            0.86,
        ),
    ]
    return [
        {
            "rule_id": rule_id,
            "rule_version": "synthetic-insurer-medical-routing-1.0.0",
            "rule_name": rule_id.replace("SYN-MED-ROUTE-", "").replace("-", " ").title(),
            "description": description,
            "routing": routing,
            "reason_code": reason_code,
            "default_confidence": confidence,
            "approval_status": "synthetic_insurer_approved",
            "owner": "Synthetic Insurer A",
            "effective_from": "2026-01-01",
            "effective_to": None,
            "synthetic": True,
        }
        for rule_id, description, routing, reason_code, confidence in rows
    ]


def _split_artifacts(
    *,
    split: str,
    product: Product,
    claims: list[dict],
    document_metadata: list[dict],
    rules: list[dict[str, Any]],
    insurer_rules: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    doc_by_claim = _docs_by_claim(document_metadata)
    medical_labels: list[dict[str, Any]] = []
    code_mapping_labels: list[dict[str, Any]] = []
    policy_coverage_labels: list[dict[str, Any]] = []
    medical_document_metadata: list[dict[str, Any]] = []
    medical_context_seed: list[dict[str, Any]] = []

    for index, claim in enumerate(claims, start=1):
        medical_scenario = MEDICAL_REVIEW_SCENARIOS[(index - 1) % len(MEDICAL_REVIEW_SCENARIOS)]
        policy_scenario = POLICY_COVERAGE_SCENARIOS[(index - 1) % len(POLICY_COVERAGE_SCENARIOS)]
        claim_docs = doc_by_claim.get(claim["claim_id"], [])
        doc_ids = [row["document_id"] for row in claim_docs[:2]]
        mapping = _mapping_for_claim(claim, medical_scenario)
        relationship = _relationship_for(claim, mapping, medical_scenario, rules)
        claim["medical_evidence"] = _runtime_medical_evidence(
            claim=claim,
            scenario=medical_scenario,
            mapping=mapping,
            relationship=relationship,
            document_ids=doc_ids,
            insurer_rules=insurer_rules,
        )
        medical_labels.append(_medical_label(claim, medical_scenario, mapping, relationship, doc_ids))
        code_mapping_labels.append(_code_mapping_label(claim, medical_scenario, mapping, doc_ids))
        policy_coverage_labels.append(_policy_label(product, claim, policy_scenario, mapping, doc_ids))
        for doc in claim_docs:
            medical_document_metadata.append(_medical_doc_metadata(claim, doc, medical_scenario, mapping))
        medical_context_seed.append(_medical_context_seed_row(split, claim, claim_docs, mapping))

    return {
        "medical_labels": medical_labels,
        "code_mapping_labels": code_mapping_labels,
        "policy_coverage_labels": policy_coverage_labels,
        "medical_document_metadata": medical_document_metadata,
        "medical_context_seed": medical_context_seed,
    }


def _docs_by_claim(document_metadata: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for row in document_metadata:
        grouped.setdefault(row["claim_id"], []).append(row)
    return {key: sorted(value, key=lambda row: row["document_id"]) for key, value in grouped.items()}


def _mapping_for_claim(claim: dict, scenario: str) -> dict[str, Any]:
    claim_body = claim["claim"]
    diagnosis_code = claim_body["diagnosis_code"]
    treatment_code = claim_body["treatment_code"]
    kcd_code = _KCD_BY_SOURCE.get(diagnosis_code, "M54.5")
    edi_code = _EDI_BY_SOURCE.get(treatment_code, "EDI-MM010")
    if scenario == "ambiguous_kcd_mapping_human_review":
        return _mapping(diagnosis_code, treatment_code, ["M54.5", "S83.5"], [edi_code], True)
    if scenario == "ambiguous_edi_mapping_human_review":
        return _mapping(diagnosis_code, treatment_code, [kcd_code], ["EDI-MM010", "EDI-MR001"], True)
    if scenario == "diagnosis_treatment_weakly_related":
        return _mapping(diagnosis_code, treatment_code, ["M54.5"], ["EDI-MR001"], False)
    if scenario == "diagnosis_treatment_unrelated":
        return _mapping(diagnosis_code, treatment_code, ["J06.9"], ["EDI-MM010"], False)
    return _mapping(diagnosis_code, treatment_code, [kcd_code], [edi_code], False)


def _mapping(
    submitted_diagnosis_code: str,
    submitted_treatment_code: str,
    kcd_candidates: list[str],
    edi_candidates: list[str],
    ambiguous: bool,
) -> dict[str, Any]:
    return {
        "submitted_diagnosis_code": submitted_diagnosis_code,
        "submitted_treatment_code": submitted_treatment_code,
        "expected_kcd_code": kcd_candidates[0],
        "expected_edi_code": edi_candidates[0],
        "kcd_candidates": [
            {"code": code, "confidence": round(0.54 if ambiguous else 0.93, 2)}
            for code in kcd_candidates
        ],
        "edi_candidates": [
            {"code": code, "confidence": round(0.56 if ambiguous else 0.92, 2)}
            for code in edi_candidates
        ],
        "ambiguous": ambiguous,
    }


def _relationship_for(
    claim: dict,
    mapping: dict[str, Any],
    scenario: str,
    rules: list[dict[str, Any]],
) -> dict[str, Any]:
    if scenario == "possible_pre_existing_condition":
        return {
            "relationship": "compatible",
            "medical_necessity_level": "partially_supported",
            "review_policy": "human_review",
            "reason_code": "POSSIBLE_PRE_EXISTING_CONDITION_REVIEW",
        }
    if scenario == "possible_excessive_treatment":
        return {
            "relationship": "compatible",
            "medical_necessity_level": "insufficient_evidence",
            "review_policy": "human_review",
            "reason_code": "POSSIBLE_EXCESSIVE_TREATMENT_REVIEW",
        }
    if scenario == "high_cost_insufficient_evidence":
        return {
            "relationship": "compatible",
            "medical_necessity_level": "insufficient_evidence",
            "review_policy": "request_documents",
            "reason_code": "MEDICAL_EVIDENCE_INSUFFICIENT",
        }
    if scenario == "document_understanding_failure":
        return {
            "relationship": "unknown",
            "medical_necessity_level": "insufficient_evidence",
            "review_policy": "human_review",
            "reason_code": "DOCUMENT_UNDERSTANDING_FAILED",
        }
    for rule in rules:
        if rule["kcd_code"] == mapping["expected_kcd_code"] and rule["edi_code"] == mapping["expected_edi_code"]:
            return {
                "relationship": rule["relationship"],
                "medical_necessity_level": rule["medical_necessity_level"],
                "review_policy": rule["review_policy"],
                "reason_code": rule["reason_code"],
            }
    return {
        "relationship": "unknown",
        "medical_necessity_level": "insufficient_evidence",
        "review_policy": "human_review",
        "reason_code": "NO_DIAGNOSIS_TREATMENT_RULE",
    }


def _medical_label(
    claim: dict,
    scenario: str,
    mapping: dict[str, Any],
    relationship: dict[str, Any],
    doc_ids: list[str],
) -> dict[str, Any]:
    requires_human_review = relationship["review_policy"] == "human_review" or mapping["ambiguous"]
    return {
        "claim_id": claim["claim_id"],
        "medical_scenario": scenario,
        "normalized_kcd_code": mapping["expected_kcd_code"],
        "normalized_edi_code": mapping["expected_edi_code"],
        "diagnosis_treatment_relationship": relationship["relationship"],
        "medical_necessity": relationship["medical_necessity_level"],
        "pre_existing_condition_review": scenario == "possible_pre_existing_condition",
        "excessive_treatment_review": scenario == "possible_excessive_treatment",
        "recommended_medical_routing": "human_review" if requires_human_review else relationship["review_policy"],
        "requires_human_review": requires_human_review,
        "reason_codes": _medical_reason_codes(scenario, mapping, relationship),
        "evidence_document_ids": doc_ids,
    }


def _code_mapping_label(
    claim: dict,
    scenario: str,
    mapping: dict[str, Any],
    doc_ids: list[str],
) -> dict[str, Any]:
    return {
        "claim_id": claim["claim_id"],
        "mapping_scenario": scenario,
        "submitted_diagnosis_code": mapping["submitted_diagnosis_code"],
        "submitted_treatment_code": mapping["submitted_treatment_code"],
        "expected_kcd_code": mapping["expected_kcd_code"],
        "expected_edi_code": mapping["expected_edi_code"],
        "kcd_candidates": mapping["kcd_candidates"],
        "edi_candidates": mapping["edi_candidates"],
        "requires_human_review": mapping["ambiguous"],
        "reason_codes": ["AMBIGUOUS_MEDICAL_CODE_MAPPING"] if mapping["ambiguous"] else ["MEDICAL_CODE_MAPPING_CONFIDENT"],
        "evidence_document_ids": doc_ids,
    }


def _policy_label(
    product: Product,
    claim: dict,
    scenario: str,
    mapping: dict[str, Any],
    doc_ids: list[str],
) -> dict[str, Any]:
    coverage_code = _coverage_code_for_claim(claim)
    requires_human_review = scenario in {"exclusion_clause_review", "unclear_policy_citation_human_review"}
    return {
        "claim_id": claim["claim_id"],
        "policy_coverage_scenario": scenario,
        "product_id": product.product_id,
        "expected_coverage_code": coverage_code,
        "expected_policy_outcome": "human_review" if requires_human_review else "coverage_analysis_supported",
        "normalized_kcd_code": mapping["expected_kcd_code"],
        "normalized_edi_code": mapping["expected_edi_code"],
        "expected_clause_ids": _clause_ids(coverage_code, scenario),
        "expected_citation_requirements": {
            "must_include_clause_id": True,
            "must_include_source_document": True,
            "must_verify_citation": scenario != "unclear_policy_citation_human_review",
        },
        "requires_human_review": requires_human_review,
        "reason_codes": _policy_reason_codes(scenario),
        "evidence_document_ids": doc_ids,
    }


def _medical_doc_metadata(
    claim: dict,
    doc: dict,
    scenario: str,
    mapping: dict[str, Any],
) -> dict[str, Any]:
    extraction_mode = "text_pdf"
    confidence = "high"
    if doc.get("document_status") == "low_ocr":
        extraction_mode = "ocr_text"
        confidence = "low"
    if scenario == "document_understanding_failure":
        extraction_mode = "vlm_required"
        confidence = "low"
    status = "failed" if scenario == "document_understanding_failure" else "extracted"
    return {
        "claim_id": claim["claim_id"],
        "document_id": doc["document_id"],
        "document_type": doc["document_type"],
        "source_file_path": doc.get("file_path"),
        "content_hash": doc.get("content_hash"),
        "text_fingerprint": doc.get("text_fingerprint"),
        "extraction_mode": extraction_mode,
        "extraction_status": status,
        "extraction_confidence_bucket": confidence,
        "field_statuses": {
            "diagnosis_code": "extracted" if status == "extracted" else "unreadable",
            "treatment_code": "extracted" if status == "extracted" else "unreadable",
            "claimed_amount": "extracted" if status == "extracted" else "unreadable",
        },
        "extracted_fields": {
            "submitted_diagnosis_code": mapping["submitted_diagnosis_code"],
            "submitted_treatment_code": mapping["submitted_treatment_code"],
            "normalized_kcd_candidate": mapping["expected_kcd_code"] if status == "extracted" else None,
            "normalized_edi_candidate": mapping["expected_edi_code"] if status == "extracted" else None,
        },
        "synthetic": True,
    }


def _medical_context_seed_row(
    split: str,
    claim: dict,
    claim_docs: list[dict],
    mapping: dict[str, Any],
) -> dict[str, Any]:
    return {
        "seed_type": "medical_context",
        "split": split,
        "claim_id": claim["claim_id"],
        "submitted_diagnosis_code": mapping["submitted_diagnosis_code"],
        "submitted_treatment_code": mapping["submitted_treatment_code"],
        "document_refs": [
            {
                "document_id": doc["document_id"],
                "document_type": doc["document_type"],
                "content_hash": doc.get("content_hash"),
            }
            for doc in claim_docs
        ],
        "prior_history_summary": {
            "same_diagnosis_claims_90d": claim["claim_history"].get("same_diagnosis_claims_90d", 0),
            "manual_therapy_count_180d": claim["claim_history"].get("manual_therapy_count_180d", 0),
        },
        "medical_evidence": claim.get("medical_evidence", {}),
        "synthetic": True,
    }


def _runtime_medical_evidence(
    *,
    claim: dict,
    scenario: str,
    mapping: dict[str, Any],
    relationship: dict[str, Any],
    document_ids: list[str],
    insurer_rules: list[dict[str, Any]],
) -> dict[str, Any]:
    history = claim.get("claim_history", {})
    claim_body = claim.get("claim", {})
    kcd_candidates = [
        {
            **candidate,
            "source": "synthetic_code_mapper",
            "evidence_document_ids": document_ids,
        }
        for candidate in mapping["kcd_candidates"]
    ]
    edi_candidates = [
        {
            **candidate,
            "source": "synthetic_code_mapper",
            "evidence_document_ids": document_ids,
        }
        for candidate in mapping["edi_candidates"]
    ]
    prior_diagnoses = []
    same_diagnosis_count = int(history.get("same_diagnosis_claims_90d", 0))
    if same_diagnosis_count:
        prior_diagnoses.append(
            {
                "kcd_code": mapping["expected_kcd_code"],
                "encounter_count": same_diagnosis_count,
                "last_service_date": _date_minus_days(claim_body.get("treatment_start_date"), 21),
                "source": "synthetic_claim_history",
            }
        )
    prior_surgeries = []
    prior_tests = []
    pre_existing_indicators: list[str] = []
    continuity_days = 0
    if scenario == "possible_pre_existing_condition":
        pre_existing_indicators.append("same_body_region_prior_care")
        prior_diagnoses.append(
            {
                "kcd_code": mapping["expected_kcd_code"],
                "encounter_count": max(1, same_diagnosis_count),
                "last_service_date": _date_minus_days(claim_body.get("treatment_start_date"), 75),
                "source": "synthetic_prior_medical_record",
            }
        )
        prior_tests.append(
            {
                "test_code": "SYN-TEST-MRI-PRIOR",
                "test_date": _date_minus_days(claim_body.get("treatment_start_date"), 80),
                "result_summary": "Prior imaging finding exists for the same synthetic diagnosis group.",
                "related_kcd_code": mapping["expected_kcd_code"],
                "source": "synthetic_prior_test_result",
            }
        )
        continuity_days = 75
    if scenario == "possible_excessive_treatment":
        prior_tests.append(
            {
                "test_code": "SYN-TEST-FOLLOWUP",
                "test_date": _date_minus_days(claim_body.get("treatment_start_date"), 14),
                "result_summary": "Repeated treatment without clear documented improvement signal.",
                "related_kcd_code": mapping["expected_kcd_code"],
                "source": "synthetic_prior_test_result",
            }
        )
    if claim_body.get("care_setting") == "inpatient":
        prior_surgeries.append(
            {
                "procedure_code": mapping["expected_edi_code"],
                "surgery_date": _date_minus_days(claim_body.get("treatment_start_date"), 120),
                "related_kcd_code": mapping["expected_kcd_code"],
                "source": "synthetic_prior_surgery_record",
            }
        )
    routing = "human_review" if mapping["ambiguous"] else relationship["review_policy"]
    if scenario == "possible_pre_existing_condition":
        routing = "human_review"
    if scenario == "possible_excessive_treatment":
        routing = "human_review"
    reason_code = "AMBIGUOUS_MEDICAL_CODE_MAPPING" if mapping["ambiguous"] else relationship["reason_code"]
    selected_rule = _find_insurer_rule(insurer_rules, _medical_rule_id(scenario, mapping, relationship))
    if selected_rule is None:
        selected_rule = _find_insurer_rule(insurer_rules, "SYN-MED-ROUTE-CONTINUE") or {}
    return {
        "schema_version": "1.0.0",
        "code_mapping_candidates": {
            "kcd": kcd_candidates,
            "edi": edi_candidates,
            "ambiguous": bool(mapping["ambiguous"]),
            "ambiguity_reason": (
                "top candidate confidence margin below synthetic insurer threshold"
                if mapping["ambiguous"]
                else "single high-confidence synthetic mapping"
            ),
        },
        "prior_medical_evidence": {
            "prior_diagnoses_180d": prior_diagnoses,
            "prior_surgeries_365d": prior_surgeries,
            "prior_tests_180d": prior_tests,
            "treatment_continuity_days": continuity_days,
            "pre_existing_condition_indicators": pre_existing_indicators,
        },
        "insurer_medical_routing_rules": [
            {
                "rule_id": selected_rule.get("rule_id", _medical_rule_id(scenario, mapping, relationship)),
                "rule_version": selected_rule.get("rule_version", "synthetic-insurer-medical-routing-1.0.0"),
                "matched": True,
                "routing": selected_rule.get("routing", "human_review" if routing == "human_review" else routing),
                "reason_code": selected_rule.get("reason_code", reason_code),
                "additional_reason_codes": _additional_medical_reason_codes(
                    selected_rule.get("reason_code", reason_code),
                    reason_code,
                    scenario,
                ),
                "confidence": float(selected_rule.get("default_confidence", 0.88 if routing == "human_review" else 0.82)),
                "approval_status": selected_rule.get("approval_status", "synthetic_insurer_approved"),
                "source": "insurer_medical_routing_rules.json",
                "evidence_refs": document_ids,
            }
        ],
        "synthetic": True,
    }


def _find_insurer_rule(rows: list[dict[str, Any]], rule_id: str) -> dict[str, Any] | None:
    for row in rows:
        if row.get("rule_id") == rule_id:
            return row
    return None


def _additional_medical_reason_codes(primary: Any, relationship_reason: str, scenario: str) -> list[str]:
    codes = []
    if relationship_reason and relationship_reason != primary:
        codes.append(relationship_reason)
    if scenario == "document_understanding_failure":
        codes.append("DOCUMENT_UNDERSTANDING_FAILED")
    return list(dict.fromkeys(codes))


def _medical_rule_id(scenario: str, mapping: dict[str, Any], relationship: dict[str, Any]) -> str:
    if mapping["ambiguous"]:
        return "SYN-MED-ROUTE-AMBIGUOUS-CODE"
    if scenario == "possible_pre_existing_condition":
        return "SYN-MED-ROUTE-PREEXISTING"
    if scenario == "possible_excessive_treatment":
        return "SYN-MED-ROUTE-EXCESSIVE-TREATMENT"
    if relationship["review_policy"] == "request_documents":
        return "SYN-MED-ROUTE-REQUEST-DOCUMENTS"
    if relationship["review_policy"] == "human_review":
        return "SYN-MED-ROUTE-CAUSALITY-REVIEW"
    return "SYN-MED-ROUTE-CONTINUE"


def _date_minus_days(value: Any, days: int) -> str:
    from datetime import date, timedelta

    try:
        parsed = date.fromisoformat(str(value))
    except ValueError:
        parsed = date(2026, 1, 1)
    return (parsed - timedelta(days=days)).isoformat()


def _coverage_code_for_claim(claim: dict) -> str:
    claim_body = claim["claim"]
    care_setting = claim_body["care_setting"]
    benefit_category = claim_body["benefit_category"]
    treatment_code = claim_body["treatment_code"]
    if benefit_category == "special_noncovered":
        if treatment_code.startswith("TRT-MRI"):
            return "COV_SPECIAL_MRI_MRA"
        if treatment_code.startswith("TRT-INJECTION"):
            return "COV_SPECIAL_INJECTION"
        return "COV_SPECIAL_MANUAL_THERAPY"
    if care_setting == "pharmacy":
        return "COV_PRESCRIPTION"
    if care_setting == "outpatient" and benefit_category == "covered":
        return "COV_OUTPATIENT_COVERED"
    if care_setting == "outpatient":
        return "COV_OUTPATIENT_NONCOVERED"
    if care_setting == "inpatient" and benefit_category == "covered":
        return "COV_INPATIENT_COVERED"
    return "COV_INPATIENT_NONCOVERED"


def _clause_ids(coverage_code: str, scenario: str) -> list[str]:
    ids = [f"{coverage_code}#BASE"]
    if scenario == "special_noncovered_rider_match":
        ids.append("SPECIAL-NONCOVERED-RIDER#001")
    if scenario == "exclusion_clause_review":
        ids.append("EXCLUSION#MEDICAL-NECESSITY")
    if scenario == "deductible_and_limit_clause_match":
        ids.append("DEDUCTIBLE-LIMIT#001")
    if scenario == "unclear_policy_citation_human_review":
        ids.append("CITATION-CONFLICT#REVIEW")
    return ids


def _policy_reason_codes(scenario: str) -> list[str]:
    return {
        "standard_covered_clause_match": ["POLICY_CLAUSE_MATCHED"],
        "special_noncovered_rider_match": ["SPECIAL_RIDER_REVIEWED"],
        "exclusion_clause_review": ["EXCLUSION_CLAUSE_REVIEW_REQUIRED"],
        "deductible_and_limit_clause_match": ["DEDUCTIBLE_AND_LIMIT_BASIS_REQUIRED"],
        "unclear_policy_citation_human_review": ["POLICY_CITATION_UNCLEAR"],
    }[scenario]


def _medical_reason_codes(scenario: str, mapping: dict[str, Any], relationship: dict[str, Any]) -> list[str]:
    codes: list[str] = []
    if mapping["ambiguous"]:
        codes.append("AMBIGUOUS_MEDICAL_CODE_MAPPING")
    codes.append(relationship["reason_code"])
    if scenario == "possible_pre_existing_condition":
        codes.append("POSSIBLE_PRE_EXISTING_CONDITION_REVIEW")
    if scenario == "possible_excessive_treatment":
        codes.append("POSSIBLE_EXCESSIVE_TREATMENT_REVIEW")
    return list(dict.fromkeys(codes))


def _required_medical_docs(relationship: str, necessity: str) -> list[str]:
    if necessity == "insufficient_evidence":
        return ["diagnosis_note", "medical_statement", "test_result_summary"]
    if relationship == "not_related":
        return ["diagnosis_note", "physician_note"]
    return ["diagnosis_note", "medical_statement"]


def _medical_report(bundle: MedicalArtifactBundle) -> dict[str, Any]:
    medical_labels = bundle.medical_labels_dev + bundle.medical_labels_eval
    code_labels = bundle.code_mapping_labels_dev + bundle.code_mapping_labels_eval
    policy_labels = bundle.policy_coverage_labels_dev + bundle.policy_coverage_labels_eval
    return {
        "medical_scenario_distribution": _counter(label["medical_scenario"] for label in medical_labels),
        "policy_coverage_scenario_distribution": _counter(label["policy_coverage_scenario"] for label in policy_labels),
        "code_mapping_label_counts": {
            "dev": len(bundle.code_mapping_labels_dev),
            "eval": len(bundle.code_mapping_labels_eval),
            "ambiguous": sum(1 for label in code_labels if label["requires_human_review"]),
        },
        "medical_label_counts": {
            "dev": len(bundle.medical_labels_dev),
            "eval": len(bundle.medical_labels_eval),
            "human_review": sum(1 for label in medical_labels if label["requires_human_review"]),
        },
        "document_understanding_rows": len(bundle.medical_document_metadata_dev) + len(bundle.medical_document_metadata_eval),
        "registries": {
            "medical_code_registry": len(bundle.medical_code_registry),
            "edi_code_registry": len(bundle.edi_code_registry),
            "diagnosis_treatment_rules": len(bundle.diagnosis_treatment_rules),
            "insurer_medical_routing_rules": len(bundle.insurer_medical_routing_rules),
        },
    }


def validate_medical_artifacts(
    *,
    dev_claims: list[dict],
    eval_claims: list[dict],
    medical_code_registry: list[dict[str, Any]],
    edi_code_registry: list[dict[str, Any]],
    diagnosis_treatment_rules: list[dict[str, Any]],
    insurer_medical_routing_rules: list[dict[str, Any]] | None = None,
    medical_labels_dev: list[dict[str, Any]],
    medical_labels_eval: list[dict[str, Any]],
    code_mapping_labels_dev: list[dict[str, Any]],
    code_mapping_labels_eval: list[dict[str, Any]],
    policy_coverage_labels_dev: list[dict[str, Any]],
    policy_coverage_labels_eval: list[dict[str, Any]],
    medical_document_metadata_dev: list[dict[str, Any]],
    medical_document_metadata_eval: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    claims = dev_claims + eval_claims
    claim_ids = {claim["claim_id"] for claim in claims}
    kcd_codes = {row["code"] for row in medical_code_registry}
    edi_codes = {row["code"] for row in edi_code_registry}
    rule_pairs = {(row["kcd_code"], row["edi_code"]) for row in diagnosis_treatment_rules}
    insurer_rule_ids = {row.get("rule_id") for row in (insurer_medical_routing_rules or [])}
    _check_scenario_coverage(errors, "dev medical", medical_labels_dev, "medical_scenario", MEDICAL_REVIEW_SCENARIOS)
    _check_scenario_coverage(errors, "eval medical", medical_labels_eval, "medical_scenario", MEDICAL_REVIEW_SCENARIOS)
    _check_scenario_coverage(errors, "dev policy", policy_coverage_labels_dev, "policy_coverage_scenario", POLICY_COVERAGE_SCENARIOS)
    _check_scenario_coverage(errors, "eval policy", policy_coverage_labels_eval, "policy_coverage_scenario", POLICY_COVERAGE_SCENARIOS)

    for claim in claims:
        serialized = str(claim)
        for forbidden in [
            "expected_kcd_code",
            "expected_edi_code",
            "medical_scenario",
            "policy_coverage_scenario",
            "diagnosis_treatment_relationship",
        ]:
            if forbidden in serialized:
                errors.append(f"runtime claim leaked medical label key {forbidden}: {claim['claim_id']}")
        _validate_runtime_medical_evidence(errors, claim, kcd_codes, edi_codes, insurer_rule_ids)

    for label in code_mapping_labels_dev + code_mapping_labels_eval:
        _require_known_claim(errors, claim_ids, label, "code mapping label")
        if label.get("expected_kcd_code") not in kcd_codes:
            errors.append(f"unknown expected KCD code: {label.get('claim_id')} {label.get('expected_kcd_code')}")
        if label.get("expected_edi_code") not in edi_codes:
            errors.append(f"unknown expected EDI code: {label.get('claim_id')} {label.get('expected_edi_code')}")

    for label in medical_labels_dev + medical_labels_eval:
        _require_known_claim(errors, claim_ids, label, "medical label")
        pair = (label.get("normalized_kcd_code"), label.get("normalized_edi_code"))
        if pair not in rule_pairs and label.get("diagnosis_treatment_relationship") != "unknown":
            errors.append(f"medical label references missing rule pair: {label.get('claim_id')} {pair}")
        if label.get("medical_scenario", "").endswith("human_review") and not label.get("requires_human_review"):
            errors.append(f"medical human review scenario is not routed to human_review: {label.get('claim_id')}")

    for label in policy_coverage_labels_dev + policy_coverage_labels_eval:
        _require_known_claim(errors, claim_ids, label, "policy coverage label")
        if not label.get("expected_clause_ids"):
            errors.append(f"policy coverage label has no expected clauses: {label.get('claim_id')}")

    for row in medical_document_metadata_dev + medical_document_metadata_eval:
        if row.get("claim_id") not in claim_ids:
            errors.append(f"medical document metadata references unknown claim: {row.get('claim_id')}")
        if row.get("synthetic") is not True:
            errors.append(f"medical document metadata not synthetic: {row.get('document_id')}")
        if row.get("extraction_mode") == "vlm_required" and row.get("extraction_status") != "failed":
            errors.append(f"vlm_required row should be failed in synthetic fixture: {row.get('document_id')}")
    return errors


def _validate_runtime_medical_evidence(
    errors: list[str],
    claim: dict[str, Any],
    kcd_codes: set[str],
    edi_codes: set[str],
    insurer_rule_ids: set[Any],
) -> None:
    evidence = claim.get("medical_evidence")
    claim_id = claim.get("claim_id")
    if not isinstance(evidence, dict):
        errors.append(f"claim missing runtime medical_evidence: {claim_id}")
        return
    if evidence.get("schema_version") != "1.0.0":
        errors.append(f"medical_evidence schema_version invalid: {claim_id}")
    if evidence.get("synthetic") is not True:
        errors.append(f"medical_evidence not synthetic: {claim_id}")
    mapping = evidence.get("code_mapping_candidates", {})
    if not isinstance(mapping, dict):
        errors.append(f"medical_evidence code_mapping_candidates invalid: {claim_id}")
        return
    kcd_candidates = mapping.get("kcd", [])
    edi_candidates = mapping.get("edi", [])
    if not kcd_candidates:
        errors.append(f"medical_evidence missing KCD candidates: {claim_id}")
    if not edi_candidates:
        errors.append(f"medical_evidence missing EDI candidates: {claim_id}")
    for candidate in kcd_candidates:
        if candidate.get("code") not in kcd_codes:
            errors.append(f"medical_evidence unknown KCD candidate: {claim_id} {candidate.get('code')}")
        _validate_candidate(errors, claim_id, candidate, "KCD")
    for candidate in edi_candidates:
        if candidate.get("code") not in edi_codes:
            errors.append(f"medical_evidence unknown EDI candidate: {claim_id} {candidate.get('code')}")
        _validate_candidate(errors, claim_id, candidate, "EDI")
    prior = evidence.get("prior_medical_evidence", {})
    for key in [
        "prior_diagnoses_180d",
        "prior_surgeries_365d",
        "prior_tests_180d",
        "pre_existing_condition_indicators",
    ]:
        if not isinstance(prior.get(key), list):
            errors.append(f"medical_evidence prior {key} invalid: {claim_id}")
    if not isinstance(prior.get("treatment_continuity_days"), int):
        errors.append(f"medical_evidence treatment_continuity_days invalid: {claim_id}")
    rules = evidence.get("insurer_medical_routing_rules", [])
    if not isinstance(rules, list) or not rules:
        errors.append(f"medical_evidence missing routing rules: {claim_id}")
    for rule in rules:
        if rule.get("routing") not in {"continue_claim_review", "request_documents", "human_review"}:
            errors.append(f"medical_evidence invalid routing rule: {claim_id} {rule.get('routing')}")
        if insurer_rule_ids and rule.get("rule_id") not in insurer_rule_ids:
            errors.append(f"medical_evidence references unknown insurer medical rule: {claim_id} {rule.get('rule_id')}")
        if rule.get("approval_status") != "synthetic_insurer_approved":
            errors.append(f"medical_evidence routing rule is not approved synthetic rule: {claim_id}")
        if not rule.get("reason_code"):
            errors.append(f"medical_evidence routing rule missing reason_code: {claim_id}")
        confidence = rule.get("confidence")
        if not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
            errors.append(f"medical_evidence routing rule confidence invalid: {claim_id}")


def _validate_candidate(errors: list[str], claim_id: Any, candidate: dict[str, Any], label: str) -> None:
    confidence = candidate.get("confidence")
    if not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
        errors.append(f"medical_evidence {label} candidate confidence invalid: {claim_id}")
    if not candidate.get("source"):
        errors.append(f"medical_evidence {label} candidate missing source: {claim_id}")


def _check_scenario_coverage(
    errors: list[str],
    label: str,
    rows: list[dict[str, Any]],
    key: str,
    expected: list[str],
) -> None:
    actual = {row.get(key) for row in rows}
    missing = set(expected) - actual
    if missing:
        errors.append(f"{label} scenarios missing: {sorted(missing)}")


def _require_known_claim(errors: list[str], claim_ids: set[str], label: dict[str, Any], label_name: str) -> None:
    if label.get("claim_id") not in claim_ids:
        errors.append(f"{label_name} references unknown claim_id: {label.get('claim_id')}")


def _counter(values) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


_KCD_BY_SOURCE = {
    "SYN-M54": "M54.5",
    "SYN-J06": "J06.9",
    "SYN-J10": "J10.1",
    "SYN-K30": "K30",
    "SYN-K35": "K35.9",
    "SYN-S83": "S83.5",
}

_EDI_BY_SOURCE = {
    "TRT-NONCOV-001": "EDI-MM010",
    "TRT-COLD-001": "EDI-OP001",
    "TRT-GASTRO-001": "EDI-OP002",
    "TRT-INP-002": "EDI-IP002",
    "TRT-RX-001": "EDI-RX001",
    "TRT-MRI-001": "EDI-MR001",
}
