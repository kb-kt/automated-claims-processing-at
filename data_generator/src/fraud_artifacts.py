from __future__ import annotations

import copy
import hashlib
import random
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from .claim_generator import ClaimGenerator
from .pdf_documents import pdf_readability, write_pdf_document
from .schemas import GenerationConfig, Product


SUPPORTED_DOCUMENT_TYPES = {
    "medical_receipt",
    "medical_statement",
    "diagnosis_note",
    "hospitalization_certificate",
    "prescription",
    "pharmacy_receipt",
}

DOCUMENT_FAILURE_SCENARIOS = {
    "document_missing",
    "document_corrupted_pdf",
    "document_low_ocr_scan",
    "document_password_protected",
}

FRAUD_SCENARIOS = [
    "normal_clean",
    "exact_duplicate_receipt",
    "legacy_receipt_id_duplicate",
    "altered_duplicate_receipt",
    "forged_amount",
    "forged_date",
    "forged_provider",
    "fraudulent_document_signal",
    "same_insured_provider_repeat_2_boundary",
    "same_insured_provider_repeat_3",
    "provider_volume_49_boundary",
    "provider_volume_50",
    "complex_duplicate_and_amount",
    "complex_repeat_and_forged_document",
    "complex_provider_volume_and_duplicate",
    "hard_negative_large_provider",
    "hard_negative_regular_visits",
    "hard_negative_same_amount_distinct_receipts",
    "hard_negative_pdf_regenerated",
    "document_missing",
    "document_corrupted_pdf",
    "document_low_ocr_scan",
    "document_password_protected",
]


@dataclass
class FraudArtifactBundle:
    dev_claims: list[dict]
    eval_claims: list[dict]
    historical_claims: list[dict]
    insureds: list[dict]
    providers: list[dict]
    fraud_labels_dev: list[dict]
    fraud_labels_eval: list[dict]
    document_metadata_dev: list[dict] = field(default_factory=list)
    document_metadata_eval: list[dict] = field(default_factory=list)
    claim_document_links_dev: list[dict] = field(default_factory=list)
    claim_document_links_eval: list[dict] = field(default_factory=list)
    fraud_context_seed_dev: list[dict] = field(default_factory=list)
    fraud_context_seed_eval: list[dict] = field(default_factory=list)
    report: dict = field(default_factory=dict)


def build_fraud_artifacts(
    *,
    config: GenerationConfig,
    product: Product,
    dev_claims: list[dict],
    eval_claims: list[dict],
    output_dir: Path,
    write_documents: bool = True,
) -> FraudArtifactBundle:
    if not config.fraud_generation.get("enabled", True):
        return FraudArtifactBundle(
            dev_claims=dev_claims,
            eval_claims=eval_claims,
            historical_claims=[],
            insureds=[],
            providers=[],
            fraud_labels_dev=[],
            fraud_labels_eval=[],
        )

    builder = _FraudArtifactBuilder(config, product, output_dir)
    return builder.build(dev_claims, eval_claims, write_documents=write_documents)


def recalculate_claim_history(current_claim: dict, historical_claims: list[dict]) -> dict[str, Any]:
    claim = current_claim["claim"]
    current_date = date.fromisoformat(claim["treatment_start_date"])
    insured_id = current_claim["insured_profile"]["insured_id"]
    provider_id = claim["provider_id"]
    diagnosis_code = claim["diagnosis_code"]

    prior_receipt_ids: set[str] = set()
    prior_receipt_hashes: set[str] = set()
    same_insured_provider_30d = 0
    same_provider_30d = 0
    same_diagnosis_90d = 0
    manual_therapy_180d = 0

    for historical in historical_claims:
        historical_claim = historical["claim"]
        historical_date = date.fromisoformat(historical_claim["treatment_start_date"])
        if historical_date >= current_date:
            continue
        days = (current_date - historical_date).days
        if historical.get("insured_profile", {}).get("insured_id") == insured_id:
            prior_receipt_ids.add(historical_claim["receipt_id"])
            prior_receipt_hashes.add(historical_claim["receipt_hash"])
            if days <= 90 and historical_claim.get("diagnosis_code") == diagnosis_code:
                same_diagnosis_90d += 1
            if days <= 180 and historical_claim.get("treatment_code", "").startswith("TRT-MANUAL"):
                manual_therapy_180d += 1
            if days <= 30 and historical_claim.get("provider_id") == provider_id:
                same_insured_provider_30d += 1
        if days <= 30 and historical_claim.get("provider_id") == provider_id:
            same_provider_30d += 1

    return {
        "same_diagnosis_claims_90d": same_diagnosis_90d,
        "manual_therapy_count_180d": manual_therapy_180d,
        "same_insured_provider_claims_30d": same_insured_provider_30d,
        "same_provider_claims_30d": same_provider_30d,
        "prior_receipt_hashes": sorted(prior_receipt_hashes),
        "prior_receipt_ids": sorted(prior_receipt_ids),
    }


class _FraudArtifactBuilder:
    def __init__(self, config: GenerationConfig, product: Product, output_dir: Path):
        self.config = config
        self.product = product
        self.output_dir = output_dir
        self.base_date = date.fromisoformat(str(config.fraud_generation.get("base_date", "2026-07-01")))
        self.generator = ClaimGenerator(config, product)

    def build(
        self,
        dev_claims: list[dict],
        eval_claims: list[dict],
        *,
        write_documents: bool,
    ) -> FraudArtifactBundle:
        dev_targeted, dev_history, dev_fraud_labels = self._targeted_split("DEV")
        eval_targeted, eval_history, eval_fraud_labels = self._targeted_split("EVAL")
        resolved_dev_claims = _replace_prefix(dev_claims, dev_targeted)
        resolved_eval_claims = _replace_prefix(eval_claims, eval_targeted)
        historical_claims = dev_history + eval_history
        insureds = _insureds_from_claims(resolved_dev_claims + resolved_eval_claims + historical_claims)
        providers = _providers_from_claims(resolved_dev_claims + resolved_eval_claims + historical_claims)

        bundle = FraudArtifactBundle(
            dev_claims=resolved_dev_claims,
            eval_claims=resolved_eval_claims,
            historical_claims=historical_claims,
            insureds=insureds,
            providers=providers,
            fraud_labels_dev=dev_fraud_labels,
            fraud_labels_eval=eval_fraud_labels,
        )
        if write_documents and self.config.fraud_generation.get("generate_pdfs", True):
            self._write_documents(bundle, "dev", resolved_dev_claims, dev_fraud_labels)
            self._write_documents(bundle, "eval", resolved_eval_claims, eval_fraud_labels)
            _attach_historical_document_fingerprints(bundle, "dev", dev_fraud_labels)
            _attach_historical_document_fingerprints(bundle, "eval", eval_fraud_labels)
        bundle.fraud_context_seed_dev = _seed_rows("dev", resolved_dev_claims, dev_history, insureds, providers, bundle.document_metadata_dev, bundle.claim_document_links_dev)
        bundle.fraud_context_seed_eval = _seed_rows("eval", resolved_eval_claims, eval_history, insureds, providers, bundle.document_metadata_eval, bundle.claim_document_links_eval)
        bundle.report = _fraud_report(bundle)
        return bundle

    def _targeted_split(self, split: str) -> tuple[list[dict], list[dict], list[dict]]:
        claims: list[dict] = []
        historical: list[dict] = []
        fraud_labels: list[dict] = []
        rng = random.Random(self.config.seed + (101 if split == "DEV" else 202))
        for offset, scenario in enumerate(FRAUD_SCENARIOS, start=1):
            scenario_index = 900000 + offset
            claim = self._base_claim(split, scenario_index, scenario, rng)
            related_history = self._historical_for_scenario(split, scenario, claim, rng)
            claim["claim_history"] = recalculate_claim_history(claim, related_history)
            _apply_runtime_signals_for_scenario(claim, scenario)
            claims.append(claim)
            historical.extend(related_history)
            fraud_labels.append(_fraud_label_for_scenario(claim, scenario))
        return claims, historical, fraud_labels

    def _base_claim(self, split: str, index: int, scenario: str, rng: random.Random) -> dict:
        provider_type = "pharmacy" if "pharmacy" in scenario else "medical_institution"
        care_setting = "pharmacy" if provider_type == "pharmacy" else "outpatient"
        benefit_category = "covered" if provider_type == "pharmacy" else "noncovered"
        treatment_code = "TRT-RX-001" if provider_type == "pharmacy" else "TRT-NONCOV-001"
        diagnosis_code = "SYN-J06" if provider_type == "pharmacy" else "SYN-M54"
        documents = [
            "claim_form",
            "pharmacy_receipt",
            "prescription",
        ] if provider_type == "pharmacy" else [
            "claim_form",
            "medical_receipt",
            "medical_statement",
            "diagnosis_note",
        ]
        provider_id = _provider_id(split, scenario)
        insured_id = _insured_id(split, index)
        receipt_id = f"RCT-SYN-{split}-{index:06d}"
        receipt_hash = _receipt_hash(split, index)
        claim = self.generator._base(
            split,
            index,
            rng,
            scenario_type="synthetic_documented_claim",
            care_setting=care_setting,
            benefit_category=benefit_category,
            treatment_code=treatment_code,
            diagnosis_code=diagnosis_code,
            claimed_amount=180_000 + offset_amount(index),
            incident_date=self.base_date,
            provider_type=provider_type,
            documents=documents,
            receipt_id=receipt_id,
            receipt_hash=receipt_hash,
            provider_id=provider_id,
        )
        _set_insured(claim, insured_id, age=42 + (index % 21), sex="F" if index % 2 else "M")
        return claim

    def _historical_for_scenario(self, split: str, scenario: str, current: dict, rng: random.Random) -> list[dict]:
        if scenario in {"normal_clean", "forged_amount", "forged_date", "forged_provider", "fraudulent_document_signal", "document_missing", "document_corrupted_pdf", "document_low_ocr_scan", "document_password_protected"}:
            return self._boundary_noise_history(split, current, rng)
        if scenario == "exact_duplicate_receipt":
            return [self._historical_claim(split, current, rng, days_before=12, receipt_id=current["claim"]["receipt_id"], receipt_hash=current["claim"]["receipt_hash"])]
        if scenario == "legacy_receipt_id_duplicate":
            return [self._historical_claim(split, current, rng, days_before=14, receipt_id=current["claim"]["receipt_id"], receipt_hash=current["claim"]["receipt_hash"] + "-OLD")]
        if scenario == "altered_duplicate_receipt":
            return [self._historical_claim(split, current, rng, days_before=10, receipt_id=current["claim"]["receipt_id"] + "-ORIG", receipt_hash=current["claim"]["receipt_hash"] + "-ORIG")]
        if scenario == "same_insured_provider_repeat_2_boundary":
            return self._repeat_history(split, current, rng, count=2, same_insured=True)
        if scenario == "same_insured_provider_repeat_3":
            return self._repeat_history(split, current, rng, count=3, same_insured=True)
        if scenario == "provider_volume_49_boundary":
            return self._provider_volume_history(split, current, rng, count=49)
        if scenario == "provider_volume_50":
            return self._provider_volume_history(split, current, rng, count=50)
        if scenario == "complex_duplicate_and_amount":
            return [self._historical_claim(split, current, rng, days_before=8, receipt_id=current["claim"]["receipt_id"], receipt_hash=current["claim"]["receipt_hash"])]
        if scenario == "complex_repeat_and_forged_document":
            return self._repeat_history(split, current, rng, count=3, same_insured=True)
        if scenario == "complex_provider_volume_and_duplicate":
            rows = self._provider_volume_history(split, current, rng, count=50)
            rows.append(self._historical_claim(split, current, rng, days_before=5, receipt_id=current["claim"]["receipt_id"], receipt_hash=current["claim"]["receipt_hash"]))
            return rows
        if scenario == "hard_negative_large_provider":
            return self._provider_volume_history(split, current, rng, count=49)
        if scenario == "hard_negative_regular_visits":
            return self._repeat_history(split, current, rng, count=2, same_insured=True)
        if scenario == "hard_negative_same_amount_distinct_receipts":
            return [self._historical_claim(split, current, rng, days_before=20, amount=current["claim"]["claimed_amount"])]
        if scenario == "hard_negative_pdf_regenerated":
            return [self._historical_claim(split, current, rng, days_before=18, receipt_id=current["claim"]["receipt_id"] + "-REGEN", receipt_hash=current["claim"]["receipt_hash"] + "-REGEN")]
        return []

    def _boundary_noise_history(self, split: str, current: dict, rng: random.Random) -> list[dict]:
        return [
            self._historical_claim(split, current, rng, days_before=31),
            self._historical_claim(split, current, rng, days_before=-1),
        ]

    def _repeat_history(self, split: str, current: dict, rng: random.Random, *, count: int, same_insured: bool) -> list[dict]:
        days = [29, 30, 7, 12, 18]
        return [
            self._historical_claim(
                split,
                current,
                rng,
                days_before=days[index % len(days)],
                insured_id=current["insured_profile"]["insured_id"] if same_insured else _insured_id(split, 700000 + index),
            )
            for index in range(count)
        ]

    def _provider_volume_history(
        self,
        split: str,
        current: dict,
        rng: random.Random,
        *,
        count: int,
        different_provider: bool = False,
    ) -> list[dict]:
        rows = []
        for index in range(count):
            rows.append(
                self._historical_claim(
                    split,
                    current,
                    rng,
                    days_before=1 + (index % 30),
                    insured_id=_insured_id(split, 610000 + index),
                    provider_id=(
                        _provider_id(split, "hard_negative_other_provider")
                        if different_provider
                        else current["claim"]["provider_id"]
                    ),
                )
            )
        return rows

    def _historical_claim(
        self,
        split: str,
        current: dict,
        rng: random.Random,
        *,
        days_before: int,
        insured_id: str | None = None,
        provider_id: str | None = None,
        receipt_id: str | None = None,
        receipt_hash: str | None = None,
        amount: int | None = None,
    ) -> dict:
        index_seed = int(hashlib.sha256(
            f"{current['claim_id']}|{days_before}|{insured_id}|{provider_id}|{receipt_id}".encode("utf-8")
        ).hexdigest()[:8], 16) % 899999
        hist = self.generator._base(
            split,
            100000 + index_seed,
            rng,
            scenario_type="historical_claim",
            care_setting=current["claim"]["care_setting"],
            benefit_category=current["claim"]["benefit_category"],
            treatment_code=current["claim"]["treatment_code"],
            diagnosis_code=current["claim"]["diagnosis_code"],
            claimed_amount=int(amount if amount is not None else current["claim"]["claimed_amount"]),
            incident_date=date.fromisoformat(current["claim"]["treatment_start_date"]) - timedelta(days=days_before),
            documents=current["documents"],
            receipt_id=receipt_id,
            receipt_hash=receipt_hash,
            provider_id=provider_id or current["claim"]["provider_id"],
            provider_type=current["claim"]["provider_type"],
        )
        hist["claim_id"] = f"CLM-{split}-HIST-{index_seed:06d}"
        _set_insured(hist, insured_id or current["insured_profile"]["insured_id"], current["insured_profile"]["age_at_service"], current["insured_profile"]["sex"])
        hist["claim_history"] = {
            "same_diagnosis_claims_90d": 0,
            "manual_therapy_count_180d": 0,
            "same_insured_provider_claims_30d": 0,
            "same_provider_claims_30d": 0,
            "prior_receipt_hashes": [],
            "prior_receipt_ids": [],
        }
        hist["history_for_claim_id"] = current["claim_id"]
        return hist

    def _write_documents(
        self,
        bundle: FraudArtifactBundle,
        split: str,
        claims: list[dict],
        fraud_labels: list[dict],
    ) -> None:
        label_by_claim_id = {label["claim_id"]: label for label in fraud_labels}
        metadata_target = bundle.document_metadata_dev if split == "dev" else bundle.document_metadata_eval
        links_target = bundle.claim_document_links_dev if split == "dev" else bundle.claim_document_links_eval
        for claim in claims:
            provider = _provider_record_from_claim(claim)
            for doc_type in _document_types_for_claim(claim):
                if doc_type not in SUPPORTED_DOCUMENT_TYPES:
                    continue
                doc_index = len(metadata_target) + 1
                document_id = f"DOC-SYN-{split.upper()}-{doc_index:06d}"
                relative_path = Path("documents") / split / claim["claim_id"] / f"{doc_type}.pdf"
                doc_fields = _document_fields(claim, provider, document_id, doc_type)
                fingerprint_fields = dict(doc_fields)
                doc_behavior = _document_behavior(label_by_claim_id.get(claim["claim_id"], {}), doc_type)
                if doc_behavior.get("amount_delta"):
                    doc_fields["claimed_amount"] = int(doc_fields["claimed_amount"]) + int(doc_behavior["amount_delta"])
                if doc_behavior.get("date_delta_days"):
                    shifted = date.fromisoformat(str(doc_fields["treatment_start_date"])) + timedelta(days=int(doc_behavior["date_delta_days"]))
                    doc_fields["treatment_start_date"] = shifted.isoformat()
                    doc_fields["treatment_end_date"] = shifted.isoformat()
                    doc_fields["issue_date"] = (shifted + timedelta(days=1)).isoformat()
                if doc_behavior.get("provider_id"):
                    doc_fields["provider_id"] = doc_behavior["provider_id"]
                    doc_fields["provider_name"] = f"Synthetic Provider {doc_behavior['provider_id']}"
                render_mode = doc_behavior.get("render_mode") or _render_mode(doc_index, self.config)
                expected_readable = bool(doc_behavior.get("expected_readable", True))
                if doc_behavior.get("missing_file"):
                    pdf_meta = {
                        "content_hash": "",
                        "text_fingerprint": "",
                        "perceptual_hash": "",
                        "mime_type": "application/pdf",
                        "file_size": 0,
                        "page_count": 0,
                        "readable": False,
                        "render_mode": render_mode,
                    }
                else:
                    pdf_meta = write_pdf_document(
                        self.output_dir / relative_path,
                        title=f"{doc_type} {claim['claim_id']}",
                        fields=doc_fields,
                        render_mode=render_mode,
                        fingerprint_fields=fingerprint_fields if doc_behavior.get("reuse_fingerprint") else doc_fields,
                        expected_readable=expected_readable,
                    )
                metadata = {
                    "claim_id": claim["claim_id"],
                    "document_id": document_id,
                    "document_type": doc_type,
                    "file_path": relative_path.as_posix(),
                    "provider_id": str(doc_fields["provider_id"]),
                    "insured_id": str(doc_fields["insured_id"]),
                    "receipt_id": str(doc_fields["receipt_id"]),
                    "issued_at": str(doc_fields["issue_date"]),
                    "synthetic": True,
                    "synthetic_notice": "SYNTHETIC TEST DOCUMENT / 실제 사용 불가",
                    "document_status": doc_behavior.get("document_status", "available"),
                    "structured_fields": doc_fields,
                    **pdf_meta,
                }
                metadata_target.append(metadata)
                links_target.append(
                    {
                        "claim_id": claim["claim_id"],
                        "document_id": document_id,
                        "document_type": doc_type,
                        "file_path": relative_path.as_posix(),
                    }
                )
                if (
                    claim["claim_id"] in label_by_claim_id
                    and (
                        label_by_claim_id[claim["claim_id"]].get("fraud_suspected")
                        or label_by_claim_id[claim["claim_id"]].get("requires_human_review")
                    )
                ):
                    label_by_claim_id[claim["claim_id"]].setdefault("evidence_document_ids", []).append(document_id)


def _replace_prefix(original: list[dict], targeted: list[dict]) -> list[dict]:
    if not original:
        return targeted
    preserved_first = [copy.deepcopy(original[0])]
    remaining_original = copy.deepcopy(original[1:])
    if len(remaining_original) >= len(targeted):
        return preserved_first + targeted + remaining_original[len(targeted):]
    return preserved_first + targeted


def _attach_historical_document_fingerprints(
    bundle: FraudArtifactBundle,
    split: str,
    fraud_labels: list[dict],
) -> None:
    altered_claim_ids = {
        label["claim_id"]
        for label in fraud_labels
        if label.get("fraud_scenario") == "altered_duplicate_receipt"
    }
    metadata = bundle.document_metadata_dev if split == "dev" else bundle.document_metadata_eval
    current_receipts = {
        row["claim_id"]: row
        for row in metadata
        if row.get("claim_id") in altered_claim_ids and row.get("document_type") == "medical_receipt"
    }
    for historical in bundle.historical_claims:
        current_claim_id = historical.get("history_for_claim_id")
        current_document = current_receipts.get(current_claim_id)
        if current_document is None:
            continue
        historical_claim = historical.get("claim") or {}
        historical_id = str(historical.get("claim_id") or "")
        content_hash = hashlib.sha256(
            f"historical-original|{historical_id}|{current_document['content_hash']}".encode("utf-8")
        ).hexdigest()
        historical["document_fingerprints"] = [
            {
                "claim_id": historical_id,
                "document_id": f"{historical_id}:medical_receipt",
                "receipt_id": historical_claim.get("receipt_id", ""),
                "content_hash": content_hash,
                "text_fingerprint": current_document.get("text_fingerprint", ""),
                "perceptual_hash": current_document.get("perceptual_hash", ""),
                "document_type": "medical_receipt",
                "document_status": "metadata_only",
            }
        ]


def _apply_runtime_signals_for_scenario(claim: dict, scenario: str) -> None:
    if scenario in {
        "altered_duplicate_receipt",
        "exact_duplicate_receipt",
        "legacy_receipt_id_duplicate",
        "complex_duplicate_and_amount",
        "complex_provider_volume_and_duplicate",
    }:
        claim["signals"]["suspected_duplicate_receipt"] = True
    if scenario in {
        "fraudulent_document_signal",
        "complex_repeat_and_forged_document",
    }:
        claim["signals"]["fraudulent_document"] = True
    if scenario in {
        "forged_amount",
        "forged_provider",
        "forged_date",
        "altered_duplicate_receipt",
        "complex_duplicate_and_amount",
        *DOCUMENT_FAILURE_SCENARIOS,
    }:
        claim["signals"]["document_claim_mismatch"] = True


def _fraud_label_for_scenario(claim: dict, scenario: str) -> dict:
    reason_codes: list[str] = []
    requires_human_review = False
    fraud_suspected = False
    if scenario in {
        "exact_duplicate_receipt",
        "legacy_receipt_id_duplicate",
        "altered_duplicate_receipt",
        "complex_duplicate_and_amount",
        "complex_provider_volume_and_duplicate",
    }:
        reason_codes.append("DUPLICATE_RECEIPT_SUSPECTED")
    if scenario in {"forged_amount", "complex_duplicate_and_amount"}:
        reason_codes.append("DOCUMENT_AMOUNT_MISMATCH")
    if scenario == "forged_date":
        reason_codes.append("DOCUMENT_DATE_MISMATCH")
    if scenario == "forged_provider":
        reason_codes.append("DOCUMENT_PROVIDER_MISMATCH")
    if scenario in {"fraudulent_document_signal", "complex_repeat_and_forged_document"}:
        reason_codes.append("FRAUD_SIGNAL")
    if scenario in {"same_insured_provider_repeat_3", "complex_repeat_and_forged_document"}:
        reason_codes.append("SAME_INSURED_PROVIDER_REPEAT_SUSPECTED")
    if scenario in {"provider_volume_50", "complex_provider_volume_and_duplicate"}:
        reason_codes.append("PROVIDER_PATTERN_ANOMALY_SUSPECTED")
    if scenario.startswith("document_"):
        requires_human_review = True
    if reason_codes:
        fraud_suspected = True
        requires_human_review = True
    return {
        "claim_id": claim["claim_id"],
        "fraud_suspected": fraud_suspected,
        "fraud_reason_codes": list(dict.fromkeys(reason_codes)),
        "fraud_scenario": scenario,
        "requires_human_review": requires_human_review,
        "evidence_document_ids": [],
    }


def _document_behavior(label: dict, doc_type: str) -> dict[str, Any]:
    scenario = label.get("fraud_scenario")
    if scenario == "document_missing" and doc_type == "diagnosis_note":
        return {"missing_file": True, "expected_readable": False, "document_status": "missing"}
    if scenario == "document_low_ocr_scan":
        return {"render_mode": "scan_low_ocr", "document_status": "low_ocr"}
    if doc_type not in {"medical_receipt", "pharmacy_receipt"}:
        return {}
    if scenario in {"forged_amount", "complex_duplicate_and_amount"}:
        return {"amount_delta": 43100, "document_status": "available"}
    if scenario == "forged_date":
        return {"date_delta_days": 5, "document_status": "available"}
    if scenario == "forged_provider":
        return {"provider_id": "PROV-SYN-FORGED-999", "document_status": "available"}
    if scenario == "altered_duplicate_receipt":
        return {"amount_delta": 12000, "reuse_fingerprint": True, "document_status": "available"}
    if scenario == "hard_negative_pdf_regenerated":
        return {"reuse_fingerprint": False, "document_status": "available"}
    if scenario == "document_corrupted_pdf":
        return {"expected_readable": False, "document_status": "corrupted"}
    if scenario == "document_password_protected":
        return {"expected_readable": False, "document_status": "password_protected"}
    return {}


def _document_types_for_claim(claim: dict) -> list[str]:
    document_types = set(SUPPORTED_DOCUMENT_TYPES)
    document_types.update(doc for doc in claim.get("documents", []) if doc in SUPPORTED_DOCUMENT_TYPES)
    return sorted(document_types)


def _document_fields(claim: dict, provider: dict, document_id: str, doc_type: str) -> dict[str, Any]:
    claim_body = claim["claim"]
    return {
        "document_id": document_id,
        "receipt_id": claim_body["receipt_id"],
        "insured_id": claim["insured_profile"]["insured_id"],
        "provider_id": claim_body["provider_id"],
        "provider_name": provider["provider_name"],
        "issue_date": claim_body["claim_date"],
        "treatment_start_date": claim_body["treatment_start_date"],
        "treatment_end_date": claim_body["treatment_end_date"],
        "diagnosis_code": claim_body["diagnosis_code"],
        "treatment_code": claim_body["treatment_code"],
        "claimed_amount": int(claim_body["claimed_amount"]),
        "document_type": doc_type,
    }


def _render_mode(index: int, config: GenerationConfig) -> str:
    ratio = float(config.fraud_generation.get("scan_pdf_ratio", 0.35))
    if ratio <= 0:
        return "text"
    interval = max(2, round(1 / ratio))
    return "scan_image_simulated" if index % interval == 0 else "text"


def _seed_rows(
    split: str,
    current_claims: list[dict],
    historical_claims: list[dict],
    insureds: list[dict],
    providers: list[dict],
    documents: list[dict],
    links: list[dict],
) -> list[dict]:
    prefix = split.upper()
    split_claims = [claim for claim in current_claims if claim["claim_id"].startswith(f"CLM-{prefix}-")]
    split_history = [claim for claim in historical_claims if claim["claim_id"].startswith(f"CLM-{prefix}-")]
    split_insured_ids = {claim["insured_profile"]["insured_id"] for claim in split_claims + split_history}
    split_provider_ids = {claim["claim"]["provider_id"] for claim in split_claims + split_history}
    rows: list[dict] = []
    rows.extend({"seed_type": "insured", "insured": row} for row in insureds if row["insured_id"] in split_insured_ids)
    rows.extend({"seed_type": "provider", "provider": row} for row in providers if row["provider_id"] in split_provider_ids)
    rows.extend({"seed_type": "historical_claim", "claim": claim} for claim in split_history)
    rows.extend({"seed_type": "current_claim", "claim": claim} for claim in split_claims)
    rows.extend({"seed_type": "document", "document": row} for row in documents)
    rows.extend({"seed_type": "claim_document_link", "claim_document_link": row} for row in links)
    return rows


def _fraud_report(bundle: FraudArtifactBundle) -> dict:
    labels = bundle.fraud_labels_dev + bundle.fraud_labels_eval
    return {
        "fraud_scenario_distribution": _counter(label["fraud_scenario"] for label in labels),
        "fraud_label_counts": {
            "dev": len(bundle.fraud_labels_dev),
            "eval": len(bundle.fraud_labels_eval),
            "fraud_suspected": sum(1 for label in labels if label["fraud_suspected"]),
            "human_review": sum(1 for label in labels if label["requires_human_review"]),
        },
        "historical_claims": len(bundle.historical_claims),
        "documents": len(bundle.document_metadata_dev) + len(bundle.document_metadata_eval),
    }


def _insureds_from_claims(claims: list[dict]) -> list[dict]:
    records: dict[str, dict] = {}
    for claim in claims:
        profile = claim["insured_profile"]
        records[profile["insured_id"]] = {
            "insured_id": profile["insured_id"],
            "age_at_service": profile["age_at_service"],
            "age_band": profile["age_band"],
            "sex": profile["sex"],
            "policyholder_relation": profile["policyholder_relation"],
            "synthetic": True,
        }
    return [records[key] for key in sorted(records)]


def _providers_from_claims(claims: list[dict]) -> list[dict]:
    records: dict[str, dict] = {}
    for claim in claims:
        provider = _provider_record_from_claim(claim)
        records[provider["provider_id"]] = provider
    return [records[key] for key in sorted(records)]


def _provider_record_from_claim(claim: dict) -> dict:
    provider_id = claim["claim"]["provider_id"]
    return {
        "provider_id": provider_id,
        "provider_name": f"Synthetic Provider {provider_id}",
        "provider_type": claim["claim"].get("provider_type", "medical_institution"),
        "synthetic": True,
    }


def _set_insured(claim: dict, insured_id: str, age: int, sex: str) -> None:
    claim["insured_profile"].update(
        {
            "insured_id": insured_id,
            "age_at_service": int(age),
            "age_band": _age_band(int(age)),
            "sex": sex,
        }
    )
    claim["claimant"].update(
        {
            "synthetic_person_id": insured_id,
            "age": int(age),
            "gender": "F" if sex == "F" else "M",
        }
    )


def _age_band(age: int) -> str:
    if age >= 80:
        return "80plus"
    if age < 10:
        return "0-9"
    return f"{age // 10}0s"


def _provider_id(split: str, scenario: str) -> str:
    digest = hashlib.sha256(f"{split}|{scenario}".encode("utf-8")).hexdigest()[:6].upper()
    return f"PROV-SYN-{split}-{digest}"


def _insured_id(split: str, index: int) -> str:
    return f"INS-SYN-{split}-{index:06d}"


def _receipt_hash(split: str, index: int) -> str:
    return f"RH-SYN-{split}-{index:06d}"


def offset_amount(index: int) -> int:
    return (index % 17) * 1000


def _counter(values) -> dict:
    return dict(sorted(Counter(values).items()))


def validate_fraud_bundle_files(output_dir: Path, bundle: FraudArtifactBundle) -> list[str]:
    errors: list[str] = []
    for metadata in bundle.document_metadata_dev + bundle.document_metadata_eval:
        relative = Path(metadata["file_path"])
        if relative.is_absolute():
            errors.append(f"absolute document path is not allowed: {relative}")
            continue
        path = output_dir / relative
        if metadata.get("document_status") == "missing":
            if path.exists():
                errors.append(f"missing document scenario wrote a file unexpectedly: {relative.as_posix()}")
            continue
        if not path.exists():
            errors.append(f"document file missing: {relative.as_posix()}")
            continue
        actual_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual_hash != metadata["content_hash"]:
            errors.append(f"document hash mismatch: {relative.as_posix()}")
        readable = pdf_readability(path)
        if readable != bool(metadata.get("readable", metadata.get("document_status") == "available")):
            errors.append(f"document readability mismatch: {relative.as_posix()}")
    return errors
