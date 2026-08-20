from __future__ import annotations

import hashlib
import os
import re
import uuid
from pathlib import Path
from typing import Any, Protocol


ALLOWED_DOCUMENT_TYPES = {
    "claim_form",
    "medical_receipt",
    "medical_statement",
    "diagnosis_note",
    "pharmacy_receipt",
    "prescription",
    "hospitalization_certificate",
    "diagnosis_certificate",
    "physician_opinion",
}
PDF_MIME_TYPE = "application/pdf"
_PDF_PAGE_PATTERN = re.compile(rb"/Type\s*/Page(?!s)\b")


class DocumentUploadError(Exception):
    status_code = 400
    code = "DOCUMENT_UPLOAD_ERROR"

    def __init__(self, message: str, *, details: list[str] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or []


class UploadClaimNotFound(DocumentUploadError):
    status_code = 404
    code = "CLAIM_NOT_FOUND"


class InvalidDocumentUpload(DocumentUploadError):
    status_code = 400
    code = "INVALID_DOCUMENT_UPLOAD"


class UploadedDocumentTooLarge(DocumentUploadError):
    status_code = 413
    code = "DOCUMENT_TOO_LARGE"


class DocumentUploadRepository(Protocol):
    def get_claim(self, claim_id: str) -> dict[str, Any] | None:
        ...

    def save_uploaded_document(self, metadata: dict[str, Any]) -> None:
        ...

    def save_audit_log(
        self,
        *,
        event_type: str,
        entity_type: str,
        actor_id: str | None = None,
        claim_id: str | None = None,
        entity_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        ...


class DocumentUploadService:
    def __init__(
        self,
        *,
        repository: DocumentUploadRepository,
        documents_root: Path,
        max_document_bytes: int = 10_000_000,
    ) -> None:
        self.repository = repository
        self.documents_root = documents_root.resolve()
        self.max_document_bytes = int(max_document_bytes)

    def upload_pdf(
        self,
        *,
        claim_id: str,
        document_type: str,
        content: bytes,
        mime_type: str,
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        claim_payload = self.repository.get_claim(claim_id)
        if claim_payload is None:
            raise UploadClaimNotFound(f"Claim not found: {claim_id}")
        if document_type not in ALLOWED_DOCUMENT_TYPES:
            raise InvalidDocumentUpload(
                f"Unsupported document type: {document_type}",
                details=[f"allowed={','.join(sorted(ALLOWED_DOCUMENT_TYPES))}"],
            )
        normalized_mime = mime_type.split(";", 1)[0].strip().lower()
        if normalized_mime != PDF_MIME_TYPE:
            raise InvalidDocumentUpload("Only application/pdf documents are accepted.")
        if not content:
            raise InvalidDocumentUpload("Uploaded PDF is empty.")
        if len(content) > self.max_document_bytes:
            raise UploadedDocumentTooLarge(
                f"Uploaded PDF exceeds the {self.max_document_bytes}-byte limit."
            )
        if not content.startswith(b"%PDF-") or b"%%EOF" not in content[-2048:]:
            raise InvalidDocumentUpload("Uploaded content is not a structurally valid PDF.")

        page_count = len(_PDF_PAGE_PATTERN.findall(content))
        if page_count < 1:
            raise InvalidDocumentUpload("Uploaded PDF does not contain a readable page object.")

        content_hash = hashlib.sha256(content).hexdigest()
        document_id = f"DOC-UPL-{uuid.uuid4().hex[:20].upper()}"
        claim_partition = hashlib.sha256(claim_id.encode("utf-8")).hexdigest()[:16]
        relative_path = Path("claims") / claim_partition / f"{document_id}.pdf"
        destination = (self.documents_root / relative_path).resolve()
        try:
            destination.relative_to(self.documents_root)
        except ValueError as exc:  # pragma: no cover - defensive invariant
            raise InvalidDocumentUpload("Resolved upload path is outside the document store.") from exc

        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".pdf.tmp")
        metadata = {
            "document_id": document_id,
            "claim_id": claim_id,
            "document_type": document_type,
            "file_path": relative_path.as_posix(),
            "content_hash": content_hash,
            "text_fingerprint": "",
            "perceptual_hash": "",
            "mime_type": PDF_MIME_TYPE,
            "file_size": len(content),
            "page_count": page_count,
            "document_status": "available",
            "storage_scope": "runtime_upload",
            "source": "customer_upload",
            "synthetic": False,
        }
        claim = dict(claim_payload.get("claim") or {})
        insured_profile = dict(claim_payload.get("insured_profile") or {})
        for key, value in {
            "receipt_id": claim.get("receipt_id"),
            "provider_id": claim.get("provider_id"),
            "insured_id": insured_profile.get("insured_id"),
            "issued_at": claim.get("claim_date"),
        }.items():
            if value not in (None, ""):
                metadata[key] = value
        try:
            temporary.write_bytes(content)
            os.replace(temporary, destination)
            self.repository.save_uploaded_document(metadata)
        except Exception:
            temporary.unlink(missing_ok=True)
            destination.unlink(missing_ok=True)
            raise

        self.repository.save_audit_log(
            event_type="claim_document_uploaded",
            entity_type="claim_document",
            actor_id=actor_id,
            claim_id=claim_id,
            entity_id=document_id,
            metadata={
                "document_type": document_type,
                "content_hash": content_hash,
                "file_size": len(content),
                "page_count": page_count,
                "storage_scope": "runtime_upload",
            },
        )
        return _public_upload_metadata(metadata)


async def read_limited_request_body(request: Any, max_bytes: int) -> bytes:
    declared_length = request.headers.get("content-length")
    if declared_length:
        try:
            if int(declared_length) > max_bytes:
                raise UploadedDocumentTooLarge(
                    f"Uploaded PDF exceeds the {max_bytes}-byte limit."
                )
        except ValueError as exc:
            raise InvalidDocumentUpload("Content-Length must be an integer.") from exc

    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > max_bytes:
            raise UploadedDocumentTooLarge(
                f"Uploaded PDF exceeds the {max_bytes}-byte limit."
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _public_upload_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        key: metadata[key]
        for key in [
            "document_id",
            "claim_id",
            "document_type",
            "content_hash",
            "mime_type",
            "file_size",
            "page_count",
            "document_status",
        ]
    }
