from __future__ import annotations

from typing import Any

from ai_agent_template.developer_kit.sdk.claim_agent_sdk.errors import SchemaValidationError

from ..db.repository import ClaimReviewRepository
from .claim_payload_normalizer import normalize_claim_payload
from .errors import ValidationFailed
from .template_runtime import TemplateRuntime


class ClaimService:
    def __init__(self, *, repository: ClaimReviewRepository, runtime: TemplateRuntime):
        self.repository = repository
        self.runtime = runtime

    def submit_claim(self, claim_payload: dict[str, Any]) -> dict[str, Any]:
        claim_payload = normalize_claim_payload(claim_payload)
        try:
            self.runtime.validator.validate_claim_input(claim_payload)
        except SchemaValidationError as exc:
            raise ValidationFailed("Claim payload does not match input schema.", exc.errors) from exc
        self.repository.save_claim(claim_payload, status="received")
        self.repository.save_audit_log(
            event_type="claim_submitted",
            claim_id=claim_payload["claim_id"],
            entity_type="claim",
            entity_id=claim_payload["claim_id"],
            metadata={
                "product_id": claim_payload["product_id"],
                "schema_version": self.runtime.template.input_schema.get("version", "1.0.0"),
            },
        )
        return {
            "claim_id": claim_payload["claim_id"],
            "status": "accepted",
            "schema_version": self.runtime.template.input_schema.get("version", "1.0.0"),
        }

    def get_claim(self, claim_id: str) -> dict[str, Any] | None:
        claim = self.repository.get_claim(claim_id)
        return normalize_claim_payload(claim) if claim else None

    def list_claims(self, *, limit: int = 50) -> dict[str, Any]:
        return {"claims": self.repository.list_claims(limit=limit)}
