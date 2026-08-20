from __future__ import annotations

from ai_agent_template.developer_kit.claims_gateway.fastapi_internal import create_internal_router
from ai_agent_template.developer_kit.claims_gateway.fraud_context import FraudContextService

from ..core.settings import Settings
from ..db.sqlite import SQLiteRepository


def _service(request):
    settings = getattr(request.app.state, "settings", None) or Settings.load()
    repository = SQLiteRepository(
        db_path=settings.sqlite_path,
        schema_path=settings.template_root / "db" / "schema.sql",
        migrations_dir=settings.template_root / "db" / "migrations",
    )
    return FraudContextService(
        repository=repository,
        documents_root=settings.fraud_generated_dir,
        uploaded_documents_root=settings.uploaded_documents_dir,
        max_document_bytes=settings.max_document_bytes,
    )


router = create_internal_router(_service)
