from __future__ import annotations

from ai_agent_template.developer_kit.claims_gateway.fastapi_internal import create_internal_router
from ai_agent_template.developer_kit.claims_gateway.fraud_context import FraudContextService


def _service(request):
    container = request.app.state.container
    return FraudContextService(
        repository=container.repository,
        documents_root=container.settings.fraud_generated_dir,
        uploaded_documents_root=container.settings.uploaded_documents_dir,
        max_document_bytes=container.settings.max_document_bytes,
    )


router = create_internal_router(_service)
