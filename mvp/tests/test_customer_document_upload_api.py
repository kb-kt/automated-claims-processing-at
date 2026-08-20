from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from ai_agent_template.developer_kit.sdk.claim_agent_sdk import ApiAccessControl
from mvp.app.core.settings import Settings
from mvp.app.core.template_runtime import TemplateRuntime
from mvp.app.db.sqlite import SQLiteRepository


WORKSPACE = Path(__file__).resolve().parents[2]
MVP_ROOT = WORKSPACE / "mvp"
GENERATED_DIR = WORKSPACE / "data_generator" / "generated"


def _pdf_bytes() -> bytes:
    return (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R >> endobj\n"
        b"trailer << /Root 1 0 R >>\n%%EOF\n"
    )


class CustomerDocumentUploadApiTest(unittest.TestCase):
    def test_customer_role_can_upload_but_not_read_claims(self) -> None:
        access = ApiAccessControl(
            enabled=True,
            customer_api_key="customer-secret",
            reviewer_api_key="reviewer-secret",
        )
        upload = access.authorize(
            method="POST",
            path="/claims/CLM-1/documents",
            authorization="Bearer customer-secret",
        )
        claim_read = access.authorize(
            method="GET",
            path="/claims/CLM-1",
            authorization="Bearer customer-secret",
        )
        self.assertTrue(upload.allowed)
        self.assertFalse(claim_read.allowed)

    @unittest.skipUnless(importlib.util.find_spec("fastapi"), "FastAPI is not installed")
    def test_submit_upload_and_internal_content_round_trip(self) -> None:
        from fastapi.testclient import TestClient
        from mvp.app.main import create_app

        claim = _read_first_jsonl(GENERATED_DIR / "claims_dev.jsonl")
        claim["claim_id"] = "CLM-UPLOAD-API-001"
        claim["documents"] = []
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ", {"CLAIMS_INTERNAL_API_KEY": ""}, clear=False
        ):
            root = Path(temp_dir)
            settings = replace(
                Settings.load(),
                sqlite_path=root / "mvp.sqlite3",
                uploaded_documents_dir=root / "documents",
                fraud_generated_dir=GENERATED_DIR,
            )
            repository = SQLiteRepository(
                db_path=settings.sqlite_path,
                schema_path=MVP_ROOT / "app" / "db" / "schema.sql",
                migrations_dir=MVP_ROOT / "app" / "db" / "migrations",
            )
            app = create_app(
                settings=settings,
                repository=repository,
                runtime=TemplateRuntime.build(settings),
            )
            client = TestClient(app)
            submitted = client.post("/claims", json=claim)
            uploaded = client.post(
                "/claims/CLM-UPLOAD-API-001/documents?document_type=medical_receipt",
                content=_pdf_bytes(),
                headers={"Content-Type": "application/pdf"},
            )
            document = uploaded.json()["document"]
            content = client.get(f"/internal/v1/documents/{document['document_id']}/content")
            stored_claim = repository.get_claim("CLM-UPLOAD-API-001")

        self.assertEqual(200, submitted.status_code)
        self.assertEqual(201, uploaded.status_code)
        self.assertEqual(_pdf_bytes(), content.content)
        self.assertEqual(document["content_hash"], content.headers["x-content-hash"])
        self.assertIn("medical_receipt", stored_claim["documents"])
        self.assertEqual(document["content_hash"], stored_claim["claim"]["receipt_hash"])


def _read_first_jsonl(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.loads(next(line for line in handle if line.strip()))


if __name__ == "__main__":
    unittest.main()
