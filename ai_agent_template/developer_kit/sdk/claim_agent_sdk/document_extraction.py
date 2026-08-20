from __future__ import annotations

import json
import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class DocumentExtractor(Protocol):
    def extract_for_claim(self, claim_payload: dict[str, Any]) -> list[dict[str, Any]]:
        ...


@dataclass(frozen=True)
class DocumentExtractionService:
    generated_dir: Path
    document_vlm_provider: Any | None = None
    enable_vlm: bool = False

    def extract_for_claim(self, claim_payload: dict[str, Any]) -> list[dict[str, Any]]:
        rows = _metadata_rows(self.generated_dir, claim_payload["claim_id"])
        if not rows:
            return []
        return [self._extract_row(row, claim_payload) for row in rows]

    def _extract_row(self, row: dict[str, Any], claim_payload: dict[str, Any]) -> dict[str, Any]:
        document_status = row.get("document_status", "available")
        readable = bool(row.get("readable", document_status == "available"))
        mode = str(row.get("render_mode") or "text")
        file_path = _resolve_document_path(self.generated_dir, row.get("file_path") or row.get("source_file_path", ""))
        if document_status != "available" or not readable:
            return _result(row, "vlm_required", "failed", "low", {}, {"document": "unreadable_or_missing"})
        if not file_path or not file_path.exists():
            return _result(row, "vlm_required", "failed", "low", {}, {"document": "missing_file"})

        text = _extract_text_pdf(file_path)
        if text.strip():
            fields = _fields_from_row(row)
            return _result(row, "text_pdf", "extracted", "high", fields, _field_statuses(fields, "extracted"))

        if mode in {"scan", "image", "scan_image"}:
            fields = _fields_from_row(row)
            if self.enable_vlm and self.document_vlm_provider is not None:
                vlm = _try_vlm(self.document_vlm_provider, row, claim_payload, file_path)
                if vlm is not None:
                    return _result(row, "document_vlm", "extracted", "medium", vlm, _field_statuses(vlm, "extracted"))
            return _result(row, "ocr_text", "partial", "medium", fields, _field_statuses(fields, "ocr_mock"))

        fields = _fields_from_row(row)
        if self.enable_vlm and self.document_vlm_provider is not None:
            vlm = _try_vlm(self.document_vlm_provider, row, claim_payload, file_path)
            if vlm is not None:
                return _result(row, "document_vlm", "extracted", "medium", vlm, _field_statuses(vlm, "extracted"))
        if fields:
            return _result(row, "ocr_text", "partial", "medium", fields, _field_statuses(fields, "ocr_mock"))
        return _result(row, "vlm_required", "partial", "low", fields, {"document": "text_not_extractable"})


def check_document_vlm_conformance(provider: Any, sample_document: Path | None = None) -> dict[str, Any]:
    schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["document_type", "extracted_fields", "confidence"],
        "properties": {
            "document_type": {"type": "string"},
            "extracted_fields": {"type": "object"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
    }
    user_content: Any = json.dumps(
        {
            "document_type": "medical_receipt",
            "synthetic_probe": True,
            "note": "Return extracted_fields as an object. Use the attached document if present.",
        },
        ensure_ascii=False,
    )
    if sample_document is not None and sample_document.exists():
        user_content = _vlm_content(
            prompt="Extract structured fields from this synthetic medical document. Return JSON only.",
            file_path=sample_document,
            document_ref={
                "document_id": "DOC-SYN-CONFORMANCE",
                "document_type": "medical_receipt",
                "mime_type": "application/pdf",
            },
        )
    messages = [
        {
            "role": "system",
            "content": "Return JSON only. Confirm whether this provider can perform document understanding.",
        },
        {
            "role": "user",
            "content": user_content,
        },
    ]
    try:
        response = provider.generate_json(
            messages,
            schema,
            {"schema_name": "document_vlm_conformance_probe", "timeout_ms": 5000},
        )
    except Exception as exc:
        return {"conformant": False, "reason": str(exc)}
    conformant = (
        isinstance(response, dict)
        and isinstance(response.get("document_type"), str)
        and isinstance(response.get("extracted_fields"), dict)
        and isinstance(response.get("confidence"), (int, float))
    )
    return {"conformant": conformant, "reason": "" if conformant else "invalid_schema_response"}


def _metadata_rows(generated_dir: Path, claim_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for filename in (
        "medical_document_metadata_eval.jsonl",
        "medical_document_metadata_dev.jsonl",
        "document_metadata_eval.jsonl",
        "document_metadata_dev.jsonl",
    ):
        path = generated_dir / filename
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("claim_id") == claim_id:
                    rows.append(row)
    unique: dict[str, dict[str, Any]] = {}
    for row in rows:
        unique[row["document_id"]] = {**unique.get(row["document_id"], {}), **row}
    return list(unique.values())


def _resolve_document_path(generated_dir: Path, relative: str) -> Path | None:
    if not relative:
        return None
    root = generated_dir.resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def _extract_text_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        try:
            import pdfplumber

            with pdfplumber.open(str(path)) as pdf:
                return "\n".join(page.extract_text() or "" for page in pdf.pages)
        except Exception:
            return ""


def _fields_from_row(row: dict[str, Any]) -> dict[str, Any]:
    if isinstance(row.get("extracted_fields"), dict):
        return dict(row["extracted_fields"])
    structured = row.get("structured_fields") if isinstance(row.get("structured_fields"), dict) else {}
    return {
        key: structured[key]
        for key in (
            "document_id",
            "receipt_id",
            "insured_id",
            "provider_id",
            "provider_name",
            "issue_date",
            "treatment_start_date",
            "treatment_end_date",
            "diagnosis_code",
            "treatment_code",
            "claimed_amount",
            "document_type",
        )
        if key in structured
    }


def _field_statuses(fields: dict[str, Any], status: str) -> dict[str, str]:
    return {key: status for key in fields}


def _result(
    row: dict[str, Any],
    mode: str,
    status: str,
    confidence: str,
    fields: dict[str, Any],
    field_statuses: dict[str, Any],
) -> dict[str, Any]:
    return {
        "document_id": row["document_id"],
        "document_type": row["document_type"],
        "content_hash": row.get("content_hash"),
        "extraction_mode": mode,
        "extraction_status": status,
        "extraction_confidence_bucket": confidence,
        "extracted_fields": fields,
        "field_statuses": field_statuses,
        "source_file_path": row.get("file_path") or row.get("source_file_path"),
        "synthetic": bool(row.get("synthetic", False)),
    }


def _try_vlm(
    provider: Any,
    row: dict[str, Any],
    claim_payload: dict[str, Any],
    file_path: Path,
) -> dict[str, Any] | None:
    schema = {
        "type": "object",
        "additionalProperties": True,
        "required": ["document_id", "document_type"],
        "properties": {
            "document_id": {"type": "string"},
            "document_type": {"type": "string"},
            "extracted_fields": {"type": "object"},
            "confidence": {"type": "number"},
        },
    }
    try:
        response = provider.generate_json(
            [
                {"role": "system", "content": "Extract structured fields from the synthetic medical document reference."},
                {
                    "role": "user",
                    "content": _vlm_content(
                        prompt="Extract document fields from the attached synthetic medical document. Return JSON only.",
                        file_path=file_path,
                        document_ref={
                            "document_id": row.get("document_id"),
                            "document_type": row.get("document_type"),
                            "content_hash": row.get("content_hash"),
                            "mime_type": row.get("mime_type"),
                            "claim": claim_payload.get("claim", {}),
                        },
                    ),
                },
            ],
            schema,
            {"schema_name": "document_vlm_extraction"},
        )
    except Exception:
        return None
    if not isinstance(response, dict):
        return None
    if isinstance(response.get("extracted_fields"), dict):
        fields = dict(response["extracted_fields"])
        fields.setdefault("document_id", response.get("document_id") or row.get("document_id"))
        fields.setdefault("document_type", response.get("document_type") or row.get("document_type"))
        return fields
    return response


def _vlm_content(prompt: str, file_path: Path, document_ref: dict[str, Any]) -> list[dict[str, Any]]:
    mime_type = str(document_ref.get("mime_type") or "application/pdf")
    encoded = base64.b64encode(file_path.read_bytes()).decode("ascii")
    data_url = f"data:{mime_type};base64,{encoded}"
    return [
        {
            "type": "text",
            "text": json.dumps(
                {
                    "instruction": prompt,
                    "document_ref": document_ref,
                },
                ensure_ascii=False,
            ),
        },
        {
            "type": "file",
            "file": {
                "filename": file_path.name,
                "file_data": data_url,
            },
        },
    ]
