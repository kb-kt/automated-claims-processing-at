from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

from .constants import (
    AGENT_FORBIDDEN_KEYS,
    ALLOWED_DECISIONS,
    CLAIM_REQUIRED_FIELDS,
    LABEL_REQUIRED_FIELDS,
)
from .fraud_artifacts import FraudArtifactBundle, recalculate_claim_history, validate_fraud_bundle_files
from .medical_artifacts import validate_medical_artifacts as validate_medical_artifact_rows
from .pdf_documents import pdf_readability
from .product_catalog import (
    load_catalog_products,
    validate_product_policy_relationships,
    validate_products,
)
from .schemas import ValidationResult


def validate_dataset(claims: list[dict], labels: list[dict]) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    claim_ids: set[str] = set()

    for index, claim in enumerate(claims, start=1):
        missing = CLAIM_REQUIRED_FIELDS - set(claim)
        if missing:
            errors.append(f"claim row {index} missing fields: {sorted(missing)}")
        claim_id = claim.get("claim_id")
        if claim_id in claim_ids:
            errors.append(f"duplicate claim_id: {claim_id}")
        claim_ids.add(claim_id)
        forbidden = _find_forbidden_keys(claim)
        if forbidden:
            errors.append(f"claim {claim_id} contains agent-forbidden keys: {sorted(forbidden)}")
        try:
            json.dumps(claim, ensure_ascii=False)
        except TypeError as exc:
            errors.append(f"claim {claim_id} is not JSON serializable: {exc}")

    label_claim_ids: set[str] = set()
    for index, label in enumerate(labels, start=1):
        missing = LABEL_REQUIRED_FIELDS - set(label)
        if missing:
            errors.append(f"label row {index} missing fields: {sorted(missing)}")
        claim_id = label.get("claim_id")
        if claim_id in label_claim_ids:
            errors.append(f"duplicate label claim_id: {claim_id}")
        label_claim_ids.add(claim_id)
        if claim_id not in claim_ids:
            errors.append(f"label references unknown claim_id: {claim_id}")
        decision = label.get("expected_decision")
        if decision not in ALLOWED_DECISIONS:
            errors.append(f"label {claim_id} has invalid decision: {decision}")
        if int(label.get("expected_payable_amount", 0)) < 0:
            errors.append(f"label {claim_id} has negative payable amount")
        if decision == "request_documents" and not label.get("missing_documents"):
            errors.append(f"label {claim_id} requests documents but missing_documents is empty")
        if label.get("fraud_suspected") and not label.get("requires_human_review"):
            errors.append(f"label {claim_id} fraud_suspected requires human review")
        try:
            json.dumps(label, ensure_ascii=False)
        except TypeError as exc:
            errors.append(f"label {claim_id} is not JSON serializable: {exc}")

    unlabeled = claim_ids - label_claim_ids
    if unlabeled:
        errors.append(f"claims without labels: {sorted(unlabeled)[:5]}")

    return ValidationResult(errors=errors, warnings=warnings)


def validate_generated_dir(path: Path) -> ValidationResult:
    claims = _read_jsonl(path / "claims_dev.jsonl") + _read_jsonl(path / "claims_eval.jsonl")
    labels = _read_jsonl(path / "labels_dev.jsonl") + _read_jsonl(path / "labels_eval.jsonl")
    validation = validate_dataset(claims, labels)
    catalog_path = path / "products" / "product_catalog.json"
    policies_path = path / "policies.jsonl"
    if catalog_path.exists() and policies_path.exists():
        products = load_catalog_products(catalog_path)
        validation = merge_validation_results(
            validation,
            validate_products(products),
            validate_product_policy_relationships(
                products,
                _read_jsonl(policies_path),
                claims,
            ),
        )
    fraud_paths = [
        path / "historical_claims.jsonl",
        path / "fraud_labels_dev.jsonl",
        path / "fraud_labels_eval.jsonl",
        path / "document_metadata_dev.jsonl",
        path / "document_metadata_eval.jsonl",
    ]
    if all(item.exists() for item in fraud_paths):
        validation = merge_validation_results(
            validation,
            validate_fraud_artifacts(
                path,
                dev_claims=_read_jsonl(path / "claims_dev.jsonl"),
                eval_claims=_read_jsonl(path / "claims_eval.jsonl"),
                historical_claims=_read_jsonl(path / "historical_claims.jsonl"),
                fraud_labels_dev=_read_jsonl(path / "fraud_labels_dev.jsonl"),
                fraud_labels_eval=_read_jsonl(path / "fraud_labels_eval.jsonl"),
                document_metadata_dev=_read_jsonl(path / "document_metadata_dev.jsonl"),
                document_metadata_eval=_read_jsonl(path / "document_metadata_eval.jsonl"),
                validate_files=True,
            ),
        )
    medical_paths = [
        path / "medical_code_registry.json",
        path / "edi_code_registry.json",
        path / "diagnosis_treatment_rules.json",
        path / "insurer_medical_routing_rules.json",
        path / "medical_labels_dev.jsonl",
        path / "medical_labels_eval.jsonl",
        path / "code_mapping_labels_dev.jsonl",
        path / "code_mapping_labels_eval.jsonl",
        path / "policy_coverage_labels_dev.jsonl",
        path / "policy_coverage_labels_eval.jsonl",
        path / "medical_document_metadata_dev.jsonl",
        path / "medical_document_metadata_eval.jsonl",
    ]
    if all(item.exists() for item in medical_paths):
        validation = merge_validation_results(
            validation,
            validate_medical_artifacts(
                dev_claims=_read_jsonl(path / "claims_dev.jsonl"),
                eval_claims=_read_jsonl(path / "claims_eval.jsonl"),
                medical_code_registry=_read_json(path / "medical_code_registry.json"),
                edi_code_registry=_read_json(path / "edi_code_registry.json"),
                diagnosis_treatment_rules=_read_json(path / "diagnosis_treatment_rules.json"),
                insurer_medical_routing_rules=_read_json(path / "insurer_medical_routing_rules.json"),
                medical_labels_dev=_read_jsonl(path / "medical_labels_dev.jsonl"),
                medical_labels_eval=_read_jsonl(path / "medical_labels_eval.jsonl"),
                code_mapping_labels_dev=_read_jsonl(path / "code_mapping_labels_dev.jsonl"),
                code_mapping_labels_eval=_read_jsonl(path / "code_mapping_labels_eval.jsonl"),
                policy_coverage_labels_dev=_read_jsonl(path / "policy_coverage_labels_dev.jsonl"),
                policy_coverage_labels_eval=_read_jsonl(path / "policy_coverage_labels_eval.jsonl"),
                medical_document_metadata_dev=_read_jsonl(path / "medical_document_metadata_dev.jsonl"),
                medical_document_metadata_eval=_read_jsonl(path / "medical_document_metadata_eval.jsonl"),
            ),
        )
    return validation


def merge_validation_results(*results: ValidationResult) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    for result in results:
        errors.extend(result.errors)
        warnings.extend(result.warnings)
    return ValidationResult(errors=errors, warnings=warnings)


def validate_fraud_artifacts(
    output_dir: Path,
    *,
    dev_claims: list[dict],
    eval_claims: list[dict],
    historical_claims: list[dict],
    fraud_labels_dev: list[dict],
    fraud_labels_eval: list[dict],
    document_metadata_dev: list[dict],
    document_metadata_eval: list[dict],
    validate_files: bool = True,
) -> ValidationResult:
    bundle = FraudArtifactBundle(
        dev_claims=dev_claims,
        eval_claims=eval_claims,
        historical_claims=historical_claims,
        insureds=[],
        providers=[],
        fraud_labels_dev=fraud_labels_dev,
        fraud_labels_eval=fraud_labels_eval,
        document_metadata_dev=document_metadata_dev,
        document_metadata_eval=document_metadata_eval,
    )
    errors: list[str] = []
    warnings: list[str] = []

    fraud_labels = fraud_labels_dev + fraud_labels_eval
    label_by_claim_id = {label.get("claim_id"): label for label in fraud_labels}
    current_claims = dev_claims + eval_claims
    current_by_id = {claim.get("claim_id"): claim for claim in current_claims}
    history_by_current_id: dict[str, list[dict]] = {}
    for historical in historical_claims:
        history_by_current_id.setdefault(str(historical.get("history_for_claim_id", "")), []).append(historical)

    for label in fraud_labels:
        claim_id = label.get("claim_id")
        if claim_id not in current_by_id:
            errors.append(f"fraud label references unknown claim_id: {claim_id}")
        leaked = _find_forbidden_keys(label.get("runtime_payload", {})) if isinstance(label.get("runtime_payload"), dict) else set()
        if leaked:
            errors.append(f"fraud label {claim_id} contains embedded runtime payload with forbidden keys: {sorted(leaked)}")
        if label.get("fraud_suspected") and not label.get("requires_human_review"):
            errors.append(f"fraud label {claim_id} fraud_suspected must require human review")

    for claim in current_claims:
        claim_id = claim.get("claim_id")
        if claim_id in label_by_claim_id:
            forbidden = _find_forbidden_keys(claim)
            if forbidden:
                errors.append(f"runtime claim {claim_id} leaked label-only keys: {sorted(forbidden)}")
            actual_history = claim.get("claim_history", {})
            expected_history = recalculate_claim_history(claim, history_by_current_id.get(str(claim_id), []))
            if actual_history != expected_history:
                errors.append(
                    "claim_history mismatch for "
                    f"{claim_id}: expected {expected_history}, got {actual_history}"
                )

    errors.extend(_validate_document_metadata(output_dir, current_by_id, fraud_labels, document_metadata_dev, validate_files))
    errors.extend(_validate_document_metadata(output_dir, current_by_id, fraud_labels, document_metadata_eval, validate_files))
    errors.extend(_validate_split_isolation(dev_claims, eval_claims, historical_claims, document_metadata_dev, document_metadata_eval))
    errors.extend(_validate_boundary_scenarios(current_by_id, label_by_claim_id))
    if validate_files:
        errors.extend(validate_fraud_bundle_files(output_dir, bundle))

    return ValidationResult(errors=errors, warnings=warnings)


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
) -> ValidationResult:
    return ValidationResult(
        errors=validate_medical_artifact_rows(
            dev_claims=dev_claims,
            eval_claims=eval_claims,
            medical_code_registry=medical_code_registry,
            edi_code_registry=edi_code_registry,
            diagnosis_treatment_rules=diagnosis_treatment_rules,
            insurer_medical_routing_rules=insurer_medical_routing_rules,
            medical_labels_dev=medical_labels_dev,
            medical_labels_eval=medical_labels_eval,
            code_mapping_labels_dev=code_mapping_labels_dev,
            code_mapping_labels_eval=code_mapping_labels_eval,
            policy_coverage_labels_dev=policy_coverage_labels_dev,
            policy_coverage_labels_eval=policy_coverage_labels_eval,
            medical_document_metadata_dev=medical_document_metadata_dev,
            medical_document_metadata_eval=medical_document_metadata_eval,
        ),
        warnings=[],
    )


def _validate_document_metadata(
    output_dir: Path,
    current_by_id: dict[str, dict],
    fraud_labels: list[dict],
    metadata_rows: list[dict],
    validate_files: bool,
) -> list[str]:
    errors: list[str] = []
    claim_ids = set(current_by_id)
    evidence_ids = {
        document_id
        for label in fraud_labels
        for document_id in label.get("evidence_document_ids", [])
    }
    for metadata in metadata_rows:
        claim_id = metadata.get("claim_id")
        if claim_id not in claim_ids:
            errors.append(f"document metadata references unknown claim_id: {claim_id}")
            continue
        if Path(str(metadata.get("file_path", ""))).is_absolute():
            errors.append(f"document metadata has absolute path: {metadata.get('file_path')}")
        if metadata.get("synthetic") is not True:
            errors.append(f"document metadata is not marked synthetic: {metadata.get('document_id')}")
        leaked = _find_forbidden_keys(metadata)
        if leaked:
            errors.append(f"document metadata leaked label-only keys: {metadata.get('document_id')} {sorted(leaked)}")
        claim = current_by_id[claim_id]
        fields = metadata.get("structured_fields", {})
        if fields:
            _validate_document_claim_alignment(errors, metadata, fields, claim)
        if metadata.get("document_status") == "missing":
            continue
        if validate_files:
            path = output_dir / Path(str(metadata["file_path"]))
            if not path.exists():
                errors.append(f"document file does not exist: {metadata.get('file_path')}")
                continue
            actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual_hash != metadata.get("content_hash"):
                errors.append(f"document content hash mismatch: {metadata.get('file_path')}")
            if pdf_readability(path) != bool(
                metadata.get("readable", metadata.get("document_status") == "available")
            ):
                errors.append(f"document readability mismatch: {metadata.get('file_path')}")
        if metadata.get("document_id") in evidence_ids and metadata.get("document_status") == "available":
            if not metadata.get("content_hash"):
                errors.append(f"evidence document has empty hash: {metadata.get('document_id')}")
    return errors


def _validate_document_claim_alignment(
    errors: list[str],
    metadata: dict,
    fields: dict,
    claim: dict,
) -> None:
    claim_body = claim["claim"]
    scenario = str(claim.get("scenario_type", ""))
    metadata_type = str(metadata.get("document_type"))
    expected_mismatch_statuses = {"corrupted", "password_protected", "low_ocr", "missing"}
    if metadata.get("document_status") in expected_mismatch_statuses:
        return

    if metadata_type in {"medical_receipt", "pharmacy_receipt"}:
        if int(fields.get("claimed_amount", -1)) != int(claim_body.get("claimed_amount", -2)):
            if not claim.get("signals", {}).get("document_claim_mismatch"):
                errors.append(f"unexpected amount mismatch: {metadata.get('document_id')}")
        if str(fields.get("provider_id")) != str(claim_body.get("provider_id")):
            if not claim.get("signals", {}).get("document_claim_mismatch"):
                errors.append(f"unexpected provider mismatch: {metadata.get('document_id')}")
        if str(fields.get("treatment_start_date")) != str(claim_body.get("treatment_start_date")):
            if not claim.get("signals", {}).get("document_claim_mismatch"):
                errors.append(f"unexpected treatment date mismatch: {metadata.get('document_id')}")
    elif not scenario.startswith("synthetic_"):
        for key in ["provider_id", "insured_id", "receipt_id"]:
            expected = claim_body.get(key) if key != "insured_id" else claim["insured_profile"]["insured_id"]
            if str(fields.get(key)) != str(expected):
                errors.append(f"document field {key} mismatch: {metadata.get('document_id')}")


def _validate_split_isolation(
    dev_claims: list[dict],
    eval_claims: list[dict],
    historical_claims: list[dict],
    document_metadata_dev: list[dict],
    document_metadata_eval: list[dict],
) -> list[str]:
    errors: list[str] = []
    dev_related = dev_claims + [row for row in historical_claims if str(row.get("claim_id", "")).startswith("CLM-DEV-")]
    eval_related = eval_claims + [row for row in historical_claims if str(row.get("claim_id", "")).startswith("CLM-EVAL-")]
    dev_insured = {row["insured_profile"]["insured_id"] for row in dev_related}
    eval_insured = {row["insured_profile"]["insured_id"] for row in eval_related}
    if dev_insured & eval_insured:
        errors.append(f"dev/eval insured leakage: {sorted(dev_insured & eval_insured)[:5]}")
    dev_receipts = {row["claim"]["receipt_id"] for row in dev_related} | {row["claim"]["receipt_hash"] for row in dev_related}
    eval_receipts = {row["claim"]["receipt_id"] for row in eval_related} | {row["claim"]["receipt_hash"] for row in eval_related}
    if dev_receipts & eval_receipts:
        errors.append(f"dev/eval receipt lineage leakage: {sorted(dev_receipts & eval_receipts)[:5]}")
    dev_fingerprints = {row.get("text_fingerprint") for row in document_metadata_dev if row.get("text_fingerprint")}
    eval_fingerprints = {row.get("text_fingerprint") for row in document_metadata_eval if row.get("text_fingerprint")}
    if dev_fingerprints & eval_fingerprints:
        errors.append("dev/eval document fingerprint leakage")
    return errors


def _validate_boundary_scenarios(
    current_by_id: dict[str, dict],
    label_by_claim_id: dict[str, dict],
) -> list[str]:
    errors: list[str] = []
    for claim_id, label in label_by_claim_id.items():
        claim = current_by_id.get(str(claim_id))
        if not claim:
            continue
        scenario = label.get("fraud_scenario")
        history = claim.get("claim_history", {})
        if scenario == "same_insured_provider_repeat_2_boundary" and history.get("same_insured_provider_claims_30d") != 2:
            errors.append(f"same insured/provider boundary should be 2: {claim_id}")
        if scenario == "same_insured_provider_repeat_3" and history.get("same_insured_provider_claims_30d") != 3:
            errors.append(f"same insured/provider threshold should be 3: {claim_id}")
        if scenario == "provider_volume_49_boundary" and history.get("same_provider_claims_30d") != 49:
            errors.append(f"provider volume boundary should be 49: {claim_id}")
        if scenario == "provider_volume_50" and history.get("same_provider_claims_30d") != 50:
            errors.append(f"provider volume threshold should be 50: {claim_id}")
    return errors


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                records.append(json.loads(line))
    return records


def _read_json(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _find_forbidden_keys(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in AGENT_FORBIDDEN_KEYS or key.startswith("expected_"):
                found.add(key)
            found.update(_find_forbidden_keys(nested))
    elif isinstance(value, list):
        for item in value:
            found.update(_find_forbidden_keys(item))
    return found
