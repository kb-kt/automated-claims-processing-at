from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any

from .errors import EvaluationError
from .label_leakage import find_label_leakage
from .schema_validator import SchemaValidator
from .template_loader import TemplateBundle


class EvaluationRunner:
    def __init__(self, template: TemplateBundle):
        self.template = template
        self.validator = SchemaValidator(template)

    def evaluate(
        self,
        outputs_path: str | Path,
        labels_path: str | Path,
        document_labels_path: str | Path | None = None,
        code_mapping_labels_path: str | Path | None = None,
        medical_labels_path: str | Path | None = None,
        policy_coverage_labels_path: str | Path | None = None,
    ) -> dict[str, Any]:
        outputs = {row["claim_id"]: row for row in _read_jsonl(outputs_path)}
        labels = {row["claim_id"]: row for row in _read_jsonl(labels_path)}
        document_labels = _read_document_labels(document_labels_path)
        code_mapping_labels = _read_label_map(code_mapping_labels_path)
        medical_labels = _read_label_map(medical_labels_path)
        policy_coverage_labels = _read_label_map(policy_coverage_labels_path)
        if not labels:
            raise EvaluationError("EVALUATION_INPUT_ERROR: labels file is empty")

        total = len(labels)
        schema_valid = 0
        decision_matches = 0
        coverage_matches = 0
        payable_matches = 0
        payable_errors: list[int] = []
        missing_doc_matches = 0
        reason_overlaps: list[float] = []
        expected_human = 0
        hit_human = 0
        expected_fraud = 0
        hit_fraud = 0
        false_denials = 0
        false_payments = 0
        human_review_misses = 0
        specialist_report_valid = 0
        document_extraction_outputs = 0
        document_extraction_field_total = 0
        document_extraction_field_success = 0
        expected_document_mismatch = 0
        detected_document_mismatch = 0
        expected_low_confidence_document_human_review = 0
        hit_low_confidence_document_human_review = 0
        document_field_label_total = 0
        document_field_label_matches = 0
        kcd_mapping_total = 0
        kcd_mapping_matches = 0
        edi_mapping_total = 0
        edi_mapping_matches = 0
        ambiguous_code_review_total = 0
        ambiguous_code_review_hits = 0
        medical_routing_total = 0
        medical_routing_matches = 0
        medical_reason_total = 0
        medical_reason_hits = 0
        citation_clause_total = 0
        citation_clause_hits = 0
        citation_requirement_total = 0
        citation_requirement_hits = 0
        label_leakage_count = 0
        forbidden_final_wording_count = 0

        forbidden_wording = {
            "지급 확정",
            "부지급 확정",
            "자동 지급 처리 완료",
            "보험금 지급을 거절합니다",
            "최종 결정되었습니다",
        }

        failure_cases: list[dict[str, Any]] = []
        for claim_id, label in labels.items():
            output = outputs.get(claim_id)
            if not output:
                failure_cases.append({"claim_id": claim_id, "error": "missing_output"})
                continue
            label_leakage_count += int(bool(find_label_leakage(output)))
            serialized_output = json.dumps(output, ensure_ascii=False)
            forbidden_final_wording_count += int(
                any(phrase in serialized_output for phrase in forbidden_wording)
            )
            try:
                self.validator.validate_agent_output(output)
                schema_valid += 1
            except Exception as exc:
                failure_cases.append({"claim_id": claim_id, "error": str(exc)})
                continue

            if output.get("recommended_decision") == label.get("expected_decision"):
                decision_matches += 1
            if output.get("coverage_code") == label.get("coverage_code"):
                coverage_matches += 1
            payable_error = abs(
                int(output.get("recommended_payable_amount", 0))
                - int(label.get("expected_payable_amount", 0))
            )
            payable_errors.append(payable_error)
            if payable_error == 0:
                payable_matches += 1
            if sorted(output.get("missing_documents", [])) == sorted(label.get("missing_documents", [])):
                missing_doc_matches += 1

            expected_reasons = set(label.get("reason_codes", []))
            actual_reasons = set(output.get("reason_codes", []))
            union = expected_reasons | actual_reasons
            reason_overlaps.append(len(expected_reasons & actual_reasons) / len(union) if union else 1.0)

            if label.get("requires_human_review"):
                expected_human += 1
                if output.get("requires_human_review"):
                    hit_human += 1
                else:
                    human_review_misses += 1
            if label.get("fraud_suspected"):
                expected_fraud += 1
                if output.get("fraud_suspected"):
                    hit_fraud += 1

            if label.get("expected_payable_amount", 0) > 0 and output.get("recommended_decision") == "deny":
                false_denials += 1
            if label.get("expected_decision") in {"deny", "request_documents"} and output.get(
                "recommended_payable_amount", 0
            ) > 0:
                false_payments += 1

            specialist_reports = output.get("specialist_reports") or []
            if _specialist_reports_valid(specialist_reports):
                specialist_report_valid += 1
            document_findings = _document_extraction_findings(specialist_reports)
            claim_document_labels = document_labels.get(claim_id, {})
            if document_findings:
                document_extraction_outputs += 1
            for finding in document_findings:
                for status in (finding.get("field_statuses") or {}).values():
                    document_extraction_field_total += 1
                    if str(status) in {"extracted", "ocr_mock"}:
                        document_extraction_field_success += 1
                expected_fields = claim_document_labels.get(finding.get("document_id"), {})
                extracted_fields = finding.get("extracted_fields") or {}
                for field, expected_value in expected_fields.items():
                    document_field_label_total += 1
                    if extracted_fields.get(field) == expected_value:
                        document_field_label_matches += 1
            label_reasons = set(label.get("reason_codes", []))
            has_document_mismatch_label = bool(
                label_reasons
                & {
                    "DOCUMENT_AMOUNT_MISMATCH",
                    "DOCUMENT_DATE_MISMATCH",
                    "DOCUMENT_PROVIDER_MISMATCH",
                    "DOCUMENT_CLAIM_MISMATCH",
                }
            )
            if has_document_mismatch_label:
                expected_document_mismatch += 1
                if _document_mismatch_detected(output):
                    detected_document_mismatch += 1
            if label.get("requires_human_review") and _has_low_confidence_document_extraction(specialist_reports):
                expected_low_confidence_document_human_review += 1
                if output.get("requires_human_review"):
                    hit_low_confidence_document_human_review += 1

            extracted_doc_fields = {
                **_merged_medical_code_fields(specialist_reports),
                **_merged_document_extracted_fields(specialist_reports),
            }
            code_label = code_mapping_labels.get(claim_id)
            if code_label:
                if code_label.get("expected_kcd_code"):
                    kcd_mapping_total += 1
                    if extracted_doc_fields.get("normalized_kcd_candidate") == code_label.get("expected_kcd_code"):
                        kcd_mapping_matches += 1
                if code_label.get("expected_edi_code"):
                    edi_mapping_total += 1
                    if extracted_doc_fields.get("normalized_edi_candidate") == code_label.get("expected_edi_code"):
                        edi_mapping_matches += 1
                if code_label.get("requires_human_review"):
                    ambiguous_code_review_total += 1
                    ambiguous_routing = _medical_report_routing(specialist_reports) or (
                        "human_review" if output.get("requires_human_review") else "continue_claim_review"
                    )
                    if ambiguous_routing == "human_review":
                        ambiguous_code_review_hits += 1

            medical_label = medical_labels.get(claim_id)
            if medical_label:
                medical_routing_total += 1
                expected_routing = medical_label.get("recommended_medical_routing")
                actual_routing = _medical_report_routing(specialist_reports) or (
                    "human_review" if output.get("requires_human_review") else "continue_claim_review"
                )
                if actual_routing == expected_routing:
                    medical_routing_matches += 1
                expected_medical_reasons = set(medical_label.get("reason_codes") or [])
                if expected_medical_reasons:
                    medical_reason_total += 1
                    if expected_medical_reasons & _all_reason_codes(output, specialist_reports):
                        medical_reason_hits += 1

            policy_label = policy_coverage_labels.get(claim_id)
            if policy_label:
                expected_clauses = set(policy_label.get("expected_clause_ids") or [])
                actual_clauses = _all_clause_ids(output, specialist_reports)
                for clause_id in expected_clauses:
                    citation_clause_total += 1
                    if clause_id in actual_clauses:
                        citation_clause_hits += 1
                requirements = policy_label.get("expected_citation_requirements") or {}
                if requirements.get("must_include_clause_id"):
                    citation_requirement_total += 1
                    if actual_clauses:
                        citation_requirement_hits += 1
                if requirements.get("must_include_source_document"):
                    citation_requirement_total += 1
                    if _has_source_document(output, specialist_reports):
                        citation_requirement_hits += 1
                if requirements.get("must_verify_citation"):
                    citation_requirement_total += 1
                    if _has_verified_citation(output, specialist_reports):
                        citation_requirement_hits += 1

        metrics = {
            "schema_validity": _ratio(schema_valid, total),
            "decision_accuracy": _ratio(decision_matches, total),
            "coverage_accuracy": _ratio(coverage_matches, total),
            "payable_amount_exact_match": _ratio(payable_matches, total),
            "payable_amount_mae": mean(payable_errors) if payable_errors else 0,
            "missing_document_exact_match": _ratio(missing_doc_matches, total),
            "reason_code_overlap": mean(reason_overlaps) if reason_overlaps else 0,
            "human_review_recall": _ratio(hit_human, expected_human) if expected_human else 1.0,
            "fraud_suspected_recall": _ratio(hit_fraud, expected_fraud) if expected_fraud else 1.0,
            "false_denial_rate": _ratio(false_denials, total),
            "false_payment_rate": _ratio(false_payments, total),
            "human_review_miss_rate": _ratio(human_review_misses, total),
            "specialist_report_schema_validity": _ratio(specialist_report_valid, total),
            "document_extraction_presence_rate": _ratio(document_extraction_outputs, total),
            "document_field_extraction_success_rate": _ratio(
                document_extraction_field_success,
                document_extraction_field_total,
            )
            if document_extraction_field_total
            else 1.0,
            "document_field_label_accuracy": _ratio(
                document_field_label_matches,
                document_field_label_total,
            )
            if document_field_label_total
            else 1.0,
            "document_mismatch_detection_rate": _ratio(
                detected_document_mismatch,
                expected_document_mismatch,
            )
            if expected_document_mismatch
            else 1.0,
            "low_confidence_document_human_review_recall": _ratio(
                hit_low_confidence_document_human_review,
                expected_low_confidence_document_human_review,
            )
            if expected_low_confidence_document_human_review
            else 1.0,
            "kcd_mapping_accuracy": _ratio(kcd_mapping_matches, kcd_mapping_total)
            if kcd_mapping_total
            else 1.0,
            "edi_mapping_accuracy": _ratio(edi_mapping_matches, edi_mapping_total)
            if edi_mapping_total
            else 1.0,
            "ambiguous_code_human_review_recall": _ratio(
                ambiguous_code_review_hits,
                ambiguous_code_review_total,
            )
            if ambiguous_code_review_total
            else 1.0,
            "medical_causality_routing_accuracy": _ratio(
                medical_routing_matches,
                medical_routing_total,
            )
            if medical_routing_total
            else 1.0,
            "medical_reason_code_recall": _ratio(medical_reason_hits, medical_reason_total)
            if medical_reason_total
            else 1.0,
            "citation_clause_recall": _ratio(citation_clause_hits, citation_clause_total)
            if citation_clause_total
            else 1.0,
            "citation_requirement_pass_rate": _ratio(
                citation_requirement_hits,
                citation_requirement_total,
            )
            if citation_requirement_total
            else 1.0,
            "label_leakage_count": label_leakage_count,
            "forbidden_final_wording_count": forbidden_final_wording_count,
            "invalid_json_count": 0,
        }
        return {
            "dataset_size": total,
            "evaluated_outputs": len(outputs),
            "metrics": metrics,
            "failure_cases": failure_cases,
        }


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as file:
        for line in file:
            stripped = line.strip()
            if stripped:
                rows.append(json.loads(stripped))
    return rows


def _read_document_labels(path: str | Path | None) -> dict[str, dict[str, dict[str, Any]]]:
    if path is None:
        return {}
    label_path = Path(path)
    if not label_path.exists():
        return {}
    labels: dict[str, dict[str, dict[str, Any]]] = {}
    for row in _read_jsonl(label_path):
        claim_id = row.get("claim_id")
        document_id = row.get("document_id")
        fields = row.get("expected_fields") or row.get("extracted_fields")
        if not claim_id or not document_id or not isinstance(fields, dict):
            continue
        labels.setdefault(str(claim_id), {})[str(document_id)] = dict(fields)
    return labels


def _read_label_map(path: str | Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    label_path = Path(path)
    if not label_path.exists():
        return {}
    return {
        str(row["claim_id"]): row
        for row in _read_jsonl(label_path)
        if row.get("claim_id")
    }


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _specialist_reports_valid(reports: Any) -> bool:
    if not isinstance(reports, list) or not reports:
        return False
    required = {"agent_name", "agent_version", "status", "summary", "findings", "requires_human_review"}
    return all(isinstance(report, dict) and required <= set(report) for report in reports)


def _document_extraction_findings(reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for report in reports:
        if report.get("agent_name") != "document_understanding":
            continue
        for finding in report.get("findings") or []:
            if isinstance(finding, dict) and finding.get("finding_type") == "document_extraction":
                findings.append(finding)
    return findings


def _has_low_confidence_document_extraction(reports: list[dict[str, Any]]) -> bool:
    return any(
        "low confidence" in str(finding.get("summary", "")).lower()
        or "failed" in str(finding.get("summary", "")).lower()
        for finding in _document_extraction_findings(reports)
    )


def _document_mismatch_detected(output: dict[str, Any]) -> bool:
    haystack = json.dumps(
        {
            "reason_codes": output.get("reason_codes", []),
            "reviewer_notes": output.get("reviewer_notes", []),
            "specialist_reports": output.get("specialist_reports", []),
        },
        ensure_ascii=False,
    )
    return any(
        marker in haystack
        for marker in (
            "DOCUMENT_AMOUNT_MISMATCH",
            "DOCUMENT_DATE_MISMATCH",
            "DOCUMENT_PROVIDER_MISMATCH",
            "DOCUMENT_CLAIM_MISMATCH",
            "mismatch",
        )
    )


def _merged_document_extracted_fields(reports: list[dict[str, Any]]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for finding in _document_extraction_findings(reports):
        extracted = finding.get("extracted_fields")
        if isinstance(extracted, dict):
            fields.update(extracted)
    return fields


def _merged_medical_code_fields(reports: list[dict[str, Any]]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for report in reports:
        if report.get("agent_name") != "medical_review_causality":
            continue
        for finding in report.get("findings") or []:
            if not isinstance(finding, dict):
                continue
            if finding.get("normalized_kcd_code"):
                fields["normalized_kcd_candidate"] = finding.get("normalized_kcd_code")
            if finding.get("normalized_edi_code"):
                fields["normalized_edi_candidate"] = finding.get("normalized_edi_code")
    return fields


def _medical_report_routing(reports: list[dict[str, Any]]) -> str | None:
    for report in reports:
        if report.get("agent_name") != "medical_review_causality":
            continue
        for finding in report.get("findings") or []:
            if isinstance(finding, dict) and finding.get("recommended_medical_routing"):
                return str(finding["recommended_medical_routing"])
    return None


def _all_reason_codes(output: dict[str, Any], reports: list[dict[str, Any]]) -> set[str]:
    codes = set(str(code) for code in output.get("reason_codes") or [])
    for report in reports:
        codes.update(str(code) for code in report.get("reason_codes") or [])
    return codes


def _all_clause_ids(output: dict[str, Any], reports: list[dict[str, Any]]) -> set[str]:
    clause_ids: set[str] = set()
    for item in output.get("policy_basis") or []:
        if isinstance(item, dict):
            _add_clause_id(clause_ids, item.get("clause_id") or item.get("citation_id"))
    for report in reports:
        for item in (report.get("citations") or []) + (report.get("findings") or []):
            if isinstance(item, dict):
                _add_clause_id(clause_ids, item.get("clause_id") or item.get("citation_id"))
    return clause_ids


def _add_clause_id(target: set[str], value: Any) -> None:
    if not value:
        return
    raw = str(value)
    target.add(raw)
    if "#" in raw:
        target.add(raw.split("#", 1)[0])


def _has_source_document(output: dict[str, Any], reports: list[dict[str, Any]]) -> bool:
    for item in output.get("policy_basis") or []:
        if isinstance(item, dict) and (item.get("source") or item.get("source_document")):
            return True
    for report in reports:
        for item in report.get("citations") or []:
            if isinstance(item, dict) and (item.get("source") or item.get("source_document")):
                return True
    return False


def _has_verified_citation(output: dict[str, Any], reports: list[dict[str, Any]]) -> bool:
    haystack = json.dumps(
        {
            "policy_basis": output.get("policy_basis", []),
            "specialist_reports": reports,
        },
        ensure_ascii=False,
    ).lower()
    return "verified" in haystack or "pass" in haystack
