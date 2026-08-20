from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from ai_agent_template.developer_kit.starter_kit.app.core.settings import Settings


WORKSPACE = Path(__file__).resolve().parents[4]
GENERATED_DIR = WORKSPACE / "data_generator" / "generated"


def _pdf_bytes() -> bytes:
    return (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R >> endobj\n"
        b"trailer << /Root 1 0 R >>\n%%EOF\n"
    )


class StarterCustomerDocumentUploadApiTest(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("fastapi"), "FastAPI is not installed")
    def test_submit_upload_and_internal_content_round_trip(self) -> None:
        from fastapi.testclient import TestClient
        from ai_agent_template.developer_kit.starter_kit.app.main import create_app

        claim = _read_first_jsonl(GENERATED_DIR / "claims_dev.jsonl")
        claim["claim_id"] = "CLM-STARTER-UPLOAD-001"
        claim["documents"] = []
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            settings = replace(
                Settings.load(),
                sqlite_path=root / "starter.sqlite3",
                uploaded_documents_dir=root / "documents",
                fraud_generated_dir=GENERATED_DIR,
            )
            client = TestClient(create_app(settings=settings))
            submitted = client.post("/claims", json=claim)
            uploaded = client.post(
                "/claims/CLM-STARTER-UPLOAD-001/documents?document_type=medical_statement",
                content=_pdf_bytes(),
                headers={"Content-Type": "application/pdf"},
            )
            self.assertEqual(200, submitted.status_code, submitted.text)
            self.assertEqual(201, uploaded.status_code, uploaded.text)
            document = uploaded.json()["document"]
            content = client.get(f"/internal/v1/documents/{document['document_id']}/content")

        self.assertEqual(_pdf_bytes(), content.content)
        self.assertEqual(document["content_hash"], content.headers["x-content-hash"])


def _read_first_jsonl(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.loads(next(line for line in handle if line.strip()))


if __name__ == "__main__":
    unittest.main()
