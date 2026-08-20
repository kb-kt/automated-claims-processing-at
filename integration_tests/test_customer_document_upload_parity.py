from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai_agent_template.developer_kit.claims_gateway import (
    DocumentUploadService,
    FraudContextService,
    InvalidDocumentUpload,
    UploadedDocumentTooLarge,
)
from ai_agent_template.developer_kit.starter_kit.app.db.sqlite import (
    SQLiteRepository as StarterSQLiteRepository,
)
from mvp.app.db.sqlite import SQLiteRepository as MvpSQLiteRepository


WORKSPACE = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = WORKSPACE / "ai_agent_template"
MVP_ROOT = WORKSPACE / "mvp"


def _pdf_bytes() -> bytes:
    return (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R >> endobj\n"
        b"trailer << /Root 1 0 R >>\n%%EOF\n"
    )


def _claim() -> dict:
    return {
        "claim_id": "CLM-UPLOAD-PARITY-001",
        "policy_id": "POL-UPLOAD-001",
        "product_id": "SYN-MED-001",
        "documents": [],
        "insured_profile": {"insured_id": "INS-UPLOAD-001"},
        "claim": {
            "receipt_id": "RCT-UPLOAD-001",
            "receipt_hash": "PRE-UPLOAD-HASH",
            "provider_id": "PROV-UPLOAD-001",
            "claim_date": "2026-08-18",
        },
    }


class CustomerDocumentUploadParityTest(unittest.TestCase):
    def test_template_and_mvp_store_and_serve_uploaded_pdf_identically(self) -> None:
        for name, repository_factory in _repository_factories().items():
            with self.subTest(runtime=name), tempfile.TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                repository = repository_factory(root)
                repository.save_claim(_claim())
                upload_service = DocumentUploadService(
                    repository=repository,
                    documents_root=root / "uploads",
                    max_document_bytes=1_000_000,
                )
                uploaded = upload_service.upload_pdf(
                    claim_id="CLM-UPLOAD-PARITY-001",
                    document_type="medical_receipt",
                    content=_pdf_bytes(),
                    mime_type="application/pdf",
                )
                context_service = FraudContextService(
                    repository=repository,
                    documents_root=root / "generated",
                    uploaded_documents_root=root / "uploads",
                    max_document_bytes=1_000_000,
                )
                listed = context_service.list_documents("CLM-UPLOAD-PARITY-001")
                content = context_service.get_document_content(uploaded["document_id"])
                stored_claim = repository.get_claim("CLM-UPLOAD-PARITY-001")

                self.assertEqual(uploaded["content_hash"], content.content_hash)
                self.assertEqual(_pdf_bytes(), content.content)
                self.assertEqual(1, uploaded["page_count"])
                self.assertEqual("runtime_upload", listed[0]["storage_scope"])
                self.assertIn("medical_receipt", stored_claim["documents"])
                self.assertEqual(uploaded["content_hash"], stored_claim["claim"]["receipt_hash"])

    def test_upload_validation_rejects_non_pdf_and_oversized_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repository = _repository_factories()["mvp"](root)
            repository.save_claim(_claim())
            service = DocumentUploadService(
                repository=repository,
                documents_root=root / "uploads",
                max_document_bytes=len(_pdf_bytes()) - 1,
            )
            with self.assertRaises(InvalidDocumentUpload):
                service.upload_pdf(
                    claim_id="CLM-UPLOAD-PARITY-001",
                    document_type="medical_receipt",
                    content=b"not-a-pdf",
                    mime_type="text/plain",
                )
            with self.assertRaises(UploadedDocumentTooLarge):
                service.upload_pdf(
                    claim_id="CLM-UPLOAD-PARITY-001",
                    document_type="medical_receipt",
                    content=_pdf_bytes(),
                    mime_type="application/pdf",
                )


def _repository_factories():
    return {
        "template": lambda root: StarterSQLiteRepository(
            db_path=root / "template.sqlite3",
            schema_path=TEMPLATE_ROOT / "db" / "schema.sql",
            migrations_dir=TEMPLATE_ROOT / "db" / "migrations",
        ),
        "mvp": lambda root: MvpSQLiteRepository(
            db_path=root / "mvp.sqlite3",
            schema_path=MVP_ROOT / "app" / "db" / "schema.sql",
            migrations_dir=MVP_ROOT / "app" / "db" / "migrations",
        ),
    }


if __name__ == "__main__":
    unittest.main()
