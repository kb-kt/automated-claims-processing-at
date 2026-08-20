from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Protocol


ALLOWED_MIME_TYPES = {"application/pdf"}


class ClaimsInternalError(Exception):
    status_code = 500
    code = "INTERNAL_ERROR"

    def __init__(self, message: str, *, details: list[str] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or []


class NotFound(ClaimsInternalError):
    status_code = 404
    code = "NOT_FOUND"


class DocumentNotFound(NotFound):
    code = "DOCUMENT_NOT_FOUND"


class DocumentUnavailable(ClaimsInternalError):
    status_code = 422
    code = "DOCUMENT_UNAVAILABLE"


class DocumentSecurityError(ClaimsInternalError):
    status_code = 403
    code = "DOCUMENT_SECURITY_ERROR"


class DocumentTooLarge(ClaimsInternalError):
    status_code = 413
    code = "DOCUMENT_TOO_LARGE"


@dataclass(frozen=True)
class DocumentContent:
    content: bytes
    mime_type: str
    content_hash: str
    file_size: int


class FraudContextRepository(Protocol):
    def get_claim(self, claim_id: str) -> dict[str, Any] | None:
        ...

    def get_fraud_current_claim(self, claim_id: str) -> dict[str, Any] | None:
        ...

    def list_historical_claims_for_claim(self, claim_id: str) -> list[dict[str, Any]]:
        ...

    def list_document_metadata_for_claim(self, claim_id: str) -> list[dict[str, Any]]:
        ...

    def get_document_metadata(self, document_id: str) -> dict[str, Any] | None:
        ...


class FraudContextService:
    def __init__(
        self,
        *,
        repository: FraudContextRepository,
        documents_root: Path,
        uploaded_documents_root: Path | None = None,
        max_document_bytes: int = 10_000_000,
    ):
        self.repository = repository
        self.documents_root = documents_root.resolve()
        self.uploaded_documents_root = (
            uploaded_documents_root.resolve() if uploaded_documents_root else None
        )
        self.max_document_bytes = int(max_document_bytes)

    def get_fraud_context(self, claim_id: str) -> dict[str, Any]:
        claim = self._get_claim_payload(claim_id)
        historical = self.repository.list_historical_claims_for_claim(claim_id)
        document_metadata = [
            _public_document_metadata(row)
            for row in self.repository.list_document_metadata_for_claim(claim_id)
        ]
        claim_history = (
            _recalculate_claim_history(claim, historical)
            if historical
            else dict(claim.get("claim_history") or {})
        )
        return {
            "schema_version": "1.0.0",
            "claim_id": claim_id,
            "claim_history": claim_history,
            "document_metadata": document_metadata,
            "historical_document_fingerprints": _historical_document_fingerprints(historical),
        }

    def list_documents(self, claim_id: str) -> list[dict[str, Any]]:
        self._get_claim_payload(claim_id)
        return [
            _public_document_metadata(row)
            for row in self.repository.list_document_metadata_for_claim(claim_id)
        ]

    def get_document_content(self, document_id: str) -> DocumentContent:
        metadata = self.repository.get_document_metadata(document_id)
        if metadata is None:
            raise DocumentNotFound(f"Document not found: {document_id}")

        status = str(metadata.get("document_status") or "available")
        if status == "missing":
            raise DocumentUnavailable(f"Document file is missing: {document_id}", details=["missing"])
        if status in {"corrupted", "password_protected"}:
            raise DocumentUnavailable(f"Document is not readable: {document_id}", details=[status])

        mime_type = str(metadata.get("mime_type") or "")
        if mime_type not in ALLOWED_MIME_TYPES:
            raise DocumentSecurityError(f"Unsupported document MIME type: {mime_type}")

        relative_path = Path(str(metadata.get("file_path") or ""))
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise DocumentSecurityError("Invalid registered document path.")
        storage_scope = str(metadata.get("storage_scope") or "generated")
        if storage_scope == "generated":
            root = self.documents_root
        elif storage_scope == "runtime_upload" and self.uploaded_documents_root is not None:
            root = self.uploaded_documents_root
        else:
            raise DocumentSecurityError(f"Unsupported document storage scope: {storage_scope}")
        path = (root / relative_path).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise DocumentSecurityError("Registered document path escapes document root.") from exc
        if not path.exists():
            raise DocumentUnavailable(f"Document file does not exist: {document_id}", details=["missing"])
        file_size = path.stat().st_size
        if file_size > self.max_document_bytes:
            raise DocumentTooLarge(f"Document exceeds max size: {document_id}")
        content = path.read_bytes()
        content_hash = hashlib.sha256(content).hexdigest()
        expected_hash = str(metadata.get("content_hash") or "")
        if expected_hash and content_hash != expected_hash:
            raise DocumentUnavailable(f"Document hash mismatch: {document_id}", details=["hash_mismatch"])
        return DocumentContent(
            content=content,
            mime_type=mime_type,
            content_hash=content_hash,
            file_size=len(content),
        )

    def _get_claim_payload(self, claim_id: str) -> dict[str, Any]:
        claim = self.repository.get_claim(claim_id) or self.repository.get_fraud_current_claim(claim_id)
        if claim is None:
            raise NotFound(f"Claim not found: {claim_id}")
        return claim


def _public_document_metadata(row: dict[str, Any]) -> dict[str, Any]:
    metadata = {
        "document_id": row["document_id"],
        "claim_id": row.get("claim_id", ""),
        "document_type": row["document_type"],
        "content_hash": row.get("content_hash", ""),
        "text_fingerprint": row.get("text_fingerprint", ""),
        "perceptual_hash": row.get("perceptual_hash", ""),
        "mime_type": row.get("mime_type", "application/pdf"),
        "file_size": int(row.get("file_size") or 0),
        "page_count": int(row.get("page_count") or 0),
        "document_status": row.get("document_status", "available"),
    }
    for field in ["receipt_id", "provider_id", "insured_id", "issued_at", "render_mode", "readable"]:
        if field in row:
            metadata[field] = row[field]
    if "storage_scope" in row:
        metadata["storage_scope"] = row["storage_scope"]
    return metadata


def _historical_document_fingerprints(historical_claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fingerprints: list[dict[str, Any]] = []
    for historical in historical_claims:
        indexed = historical.get("document_fingerprints") or []
        if indexed:
            fingerprints.extend(_public_historical_fingerprint(row, historical) for row in indexed)
            continue
        claim = historical.get("claim") or {}
        receipt_id = claim.get("receipt_id")
        receipt_hash = claim.get("receipt_hash")
        if not receipt_id and not receipt_hash:
            continue
        fingerprints.append(
            {
                "claim_id": historical.get("claim_id"),
                "document_id": f"{historical.get('claim_id')}:medical_receipt",
                "receipt_id": receipt_id,
                "content_hash": receipt_hash,
                "text_fingerprint": receipt_hash,
                "perceptual_hash": "",
                "document_type": "medical_receipt",
                "document_status": "metadata_only",
            }
        )
    return fingerprints


def _public_historical_fingerprint(row: dict[str, Any], historical: dict[str, Any]) -> dict[str, Any]:
    claim_id = str(row.get("claim_id") or historical.get("claim_id") or "")
    return {
        "claim_id": claim_id,
        "document_id": str(row.get("document_id") or f"{claim_id}:medical_receipt"),
        "receipt_id": str(row.get("receipt_id") or ""),
        "content_hash": str(row.get("content_hash") or ""),
        "text_fingerprint": str(row.get("text_fingerprint") or ""),
        "perceptual_hash": str(row.get("perceptual_hash") or ""),
        "document_type": str(row.get("document_type") or "medical_receipt"),
        "document_status": str(row.get("document_status") or "metadata_only"),
    }


def _recalculate_claim_history(current_claim: dict[str, Any], historical_claims: list[dict[str, Any]]) -> dict[str, Any]:
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
        historical_insured_id = historical.get("insured_profile", {}).get("insured_id")
        if historical_insured_id == insured_id:
            prior_receipt_ids.add(historical_claim["receipt_id"])
            prior_receipt_hashes.add(historical_claim["receipt_hash"])
            if days <= 90 and historical_claim.get("diagnosis_code") == diagnosis_code:
                same_diagnosis_90d += 1
            if days <= 180 and str(historical_claim.get("treatment_code", "")).startswith("TRT-MANUAL"):
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
