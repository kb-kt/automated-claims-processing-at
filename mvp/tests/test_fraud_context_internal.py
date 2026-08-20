import importlib.util
import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from ai_agent_template.developer_kit.claims_gateway import FraudContextSeedLoader, FraudContextService

from mvp.app.core.settings import Settings
from mvp.app.core.template_runtime import TemplateRuntime
from mvp.app.db.sqlite import SQLiteRepository


WORKSPACE = Path(__file__).resolve().parents[2]
MVP_ROOT = WORKSPACE / "mvp"
GENERATED_DIR = WORKSPACE / "data_generator" / "generated"


class MvpFraudContextInternalTest(unittest.TestCase):
    def test_seed_and_service_match_template_contract_boundaries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = _seeded_repo(Path(temp_dir))
            service = FraudContextService(
                repository=repository,
                documents_root=GENERATED_DIR,
                max_document_bytes=10_000_000,
            )
            context = service.get_fraud_context("CLM-DEV-900012")
            tables = _table_names(Path(temp_dir) / "mvp.sqlite3")

        self.assertEqual(context["schema_version"], "1.0.0")
        self.assertEqual(context["claim_history"]["same_provider_claims_30d"], 50)
        self.assertTrue(context["document_metadata"])
        self.assertFalse(any("label" in table for table in tables))

    @unittest.skipUnless(importlib.util.find_spec("fastapi"), "FastAPI is not installed")
    def test_internal_api_auth_and_document_content(self) -> None:
        from fastapi.testclient import TestClient
        from mvp.app.main import create_app

        with tempfile.TemporaryDirectory() as temp_dir:
            repository = _seeded_repo(Path(temp_dir))
            settings = replace(
                Settings.load(),
                sqlite_path=Path(temp_dir) / "mvp.sqlite3",
                fraud_generated_dir=GENERATED_DIR,
            )
            app = create_app(
                settings=settings,
                repository=repository,
                runtime=TemplateRuntime.build(settings),
            )
            with patch.dict("os.environ", {"CLAIMS_INTERNAL_API_KEY": "secret"}):
                client = TestClient(app)
                unauthorized = client.get("/internal/v1/fraud-context/claims/CLM-DEV-900001")
                forbidden = client.get(
                    "/internal/v1/fraud-context/claims/CLM-DEV-900001",
                    headers={"Authorization": "Bearer wrong"},
                )
                context = client.get(
                    "/internal/v1/fraud-context/claims/CLM-DEV-900001",
                    headers={"Authorization": "Bearer secret"},
                )
                documents = client.get(
                    "/internal/v1/claims/CLM-DEV-900001/documents",
                    headers={"Authorization": "Bearer secret"},
                )
                document_id = documents.json()["documents"][0]["document_id"]
                content = client.get(
                    f"/internal/v1/documents/{document_id}/content",
                    headers={"Authorization": "Bearer secret"},
                )

        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(context.status_code, 200)
        self.assertEqual(context.json()["schema_version"], "1.0.0")
        self.assertEqual(documents.status_code, 200)
        self.assertEqual(content.status_code, 200)
        self.assertEqual(content.headers["content-type"], "application/pdf")
        self.assertTrue(content.headers.get("x-content-hash"))


def _seeded_repo(temp_dir: Path) -> SQLiteRepository:
    repository = SQLiteRepository(
        db_path=temp_dir / "mvp.sqlite3",
        schema_path=MVP_ROOT / "app" / "db" / "schema.sql",
        migrations_dir=MVP_ROOT / "app" / "db" / "migrations",
    )
    loader = FraudContextSeedLoader(repository)
    loader.load_generated(GENERATED_DIR, split="dev")
    loader.load_generated(GENERATED_DIR, split="eval")
    return repository


def _table_names(db_path: Path) -> set[str]:
    with closing(sqlite3.connect(db_path)) as connection:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {row[0] for row in rows}
