import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from ai_agent_template.developer_kit.claims_gateway import (
    DocumentSecurityError,
    DocumentTooLarge,
    DocumentUnavailable,
    FraudContextSeedLoader,
    FraudContextService,
)
from ai_agent_template.developer_kit.starter_kit.app.db.sqlite import SQLiteRepository


WORKSPACE = Path(__file__).resolve().parents[4]
TEMPLATE_ROOT = WORKSPACE / "ai_agent_template"
GENERATED_DIR = WORKSPACE / "data_generator" / "generated"


class FraudContextSeedAndServiceTest(unittest.TestCase):
    def test_seed_loader_is_idempotent_and_does_not_load_labels(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = _repository(temp_dir)
            loader = FraudContextSeedLoader(repository)
            first = loader.load_generated(GENERATED_DIR, split="dev")
            second = loader.load_generated(GENERATED_DIR, split="dev")
            counts = _counts(Path(temp_dir) / "repo.sqlite3")
            tables = _table_names(Path(temp_dir) / "repo.sqlite3")

        self.assertEqual(first["row_count"], second["row_count"])
        self.assertGreaterEqual(counts["fraud_current_claims"], 23)
        self.assertGreater(counts["historical_claims"], 100)
        self.assertGreater(counts["document_metadata"], 100)
        self.assertFalse(any("label" in table for table in tables))

    def test_fraud_context_recalculates_history_boundaries_from_historical_claims(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = _seeded_repository(temp_dir)
            service = _service(repository)

            repeat_2 = service.get_fraud_context("CLM-DEV-900009")["claim_history"]
            repeat_3 = service.get_fraud_context("CLM-DEV-900010")["claim_history"]
            duplicate_context = service.get_fraud_context("CLM-DEV-900002")
            provider_49 = service.get_fraud_context("CLM-DEV-900011")["claim_history"]
            provider_50 = service.get_fraud_context("CLM-DEV-900012")["claim_history"]

        self.assertEqual(repeat_2["same_insured_provider_claims_30d"], 2)
        self.assertEqual(repeat_3["same_insured_provider_claims_30d"], 3)
        self.assertEqual(provider_49["same_provider_claims_30d"], 49)
        self.assertEqual(provider_50["same_provider_claims_30d"], 50)
        self.assertTrue(repeat_3["prior_receipt_ids"])
        self.assertTrue(repeat_3["prior_receipt_hashes"])
        self.assertTrue(duplicate_context["historical_document_fingerprints"])
        self.assertIn("receipt_id", duplicate_context["historical_document_fingerprints"][0])

    def test_document_content_is_served_only_for_registered_safe_available_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = _seeded_repository(temp_dir)
            service = _service(repository)
            document = next(
                item
                for item in service.list_documents("CLM-DEV-900001")
                if item["document_status"] == "available"
            )
            content = service.get_document_content(document["document_id"])

        self.assertEqual(content.mime_type, "application/pdf")
        self.assertEqual(content.file_size, len(content.content))
        self.assertTrue(content.content_hash)

    def test_document_content_rejects_oversized_and_unsupported_mime(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = _seeded_repository(temp_dir)
            document = next(
                item
                for item in _service(repository).list_documents("CLM-DEV-900001")
                if item["document_status"] == "available"
            )
            tiny_limit_service = FraudContextService(
                repository=repository,
                documents_root=GENERATED_DIR,
                max_document_bytes=1,
            )
            with self.assertRaises(DocumentTooLarge):
                tiny_limit_service.get_document_content(document["document_id"])

            claim = repository.get_fraud_current_claim("CLM-DEV-900001")
            metadata = repository.get_document_metadata(document["document_id"])
            metadata["document_id"] = "DOC-BAD-MIME"
            metadata["mime_type"] = "text/plain"
            repository.seed_fraud_context(
                split="dev",
                seed_rows=[{"seed_type": "current_claim", "claim": claim}],
                historical_claims=[],
                document_metadata=[metadata],
                claim_document_links=[
                    {
                        "claim_id": claim["claim_id"],
                        "document_id": "DOC-BAD-MIME",
                        "document_type": metadata["document_type"],
                    }
                ],
                source_files=[],
            )
            with self.assertRaises(DocumentSecurityError):
                _service(repository).get_document_content("DOC-BAD-MIME")

    def test_unavailable_and_unsafe_documents_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = _seeded_repository(temp_dir)
            service = _service(repository)
            missing_doc = next(
                item
                for item in service.list_documents("CLM-DEV-900020")
                if item["document_status"] == "missing"
            )
            with self.assertRaises(DocumentUnavailable):
                service.get_document_content(missing_doc["document_id"])

            claim = repository.get_fraud_current_claim("CLM-DEV-900001")
            repository.seed_fraud_context(
                split="dev",
                seed_rows=[{"seed_type": "current_claim", "claim": claim}],
                historical_claims=[],
                document_metadata=[
                    {
                        "claim_id": claim["claim_id"],
                        "document_id": "DOC-BAD-PATH",
                        "document_type": "medical_receipt",
                        "file_path": "../outside.pdf",
                        "content_hash": "",
                        "text_fingerprint": "",
                        "perceptual_hash": "",
                        "mime_type": "application/pdf",
                        "file_size": 1,
                        "page_count": 1,
                        "document_status": "available",
                    }
                ],
                claim_document_links=[
                    {
                        "claim_id": claim["claim_id"],
                        "document_id": "DOC-BAD-PATH",
                        "document_type": "medical_receipt",
                    }
                ],
                source_files=[],
            )
            with self.assertRaises(DocumentSecurityError):
                service.get_document_content("DOC-BAD-PATH")


def _seeded_repository(temp_dir: str) -> SQLiteRepository:
    repository = _repository(temp_dir)
    FraudContextSeedLoader(repository).load_generated(GENERATED_DIR, split="dev")
    return repository


def _repository(temp_dir: str) -> SQLiteRepository:
    return SQLiteRepository(
        db_path=Path(temp_dir) / "repo.sqlite3",
        schema_path=TEMPLATE_ROOT / "db" / "schema.sql",
        migrations_dir=TEMPLATE_ROOT / "db" / "migrations",
    )


def _service(repository: SQLiteRepository) -> FraudContextService:
    return FraudContextService(
        repository=repository,
        documents_root=GENERATED_DIR,
        max_document_bytes=10_000_000,
    )


def _counts(db_path: Path) -> dict[str, int]:
    tables = ["fraud_current_claims", "historical_claims", "document_metadata", "claim_documents"]
    with closing(sqlite3.connect(db_path)) as connection:
        return {table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables}


def _table_names(db_path: Path) -> set[str]:
    with closing(sqlite3.connect(db_path)) as connection:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {row[0] for row in rows}
