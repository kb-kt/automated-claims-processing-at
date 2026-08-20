from __future__ import annotations

from typing import Any

from ai_agent_template.developer_kit.sdk.claim_agent_sdk import (
    ProductCatalogRegistry,
    RuntimeMedicalRegistryService,
    WorkflowRunner,
    apply_fail_closed_human_review,
    assert_no_label_leakage,
    build_decision_provenance,
)
from ai_agent_template.developer_kit.sdk.claim_agent_sdk import verify_policy_basis
from ai_agent_template.developer_kit.sdk.claim_agent_sdk.errors import (
    SafetyValidationError,
    SchemaValidationError,
)

from ..db.repository import ClaimReviewRepository
from .claim_payload_normalizer import normalize_claim_payload
from .errors import NotFound, ValidationFailed
from .masking import mask_queue_item
from .template_runtime import TemplateRuntime
from .tooling import RecordingToolRegistry, build_recording_registry


ALLOWED_REVIEWER_ACTIONS = {
    "accept_recommendation",
    "modify_recommendation",
    "request_documents",
    "defer",
    "mark_human_review",
}


class ReviewService:
    def __init__(self, *, repository: ClaimReviewRepository, runtime: TemplateRuntime):
        self.repository = repository
        self.runtime = runtime

    def run_review(
        self,
        *,
        claim_id: str | None = None,
        claim_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if claim_payload is None:
            if not claim_id:
                raise ValidationFailed("claim_id or claim payload is required.")
            claim_payload = self.repository.get_claim(claim_id)
        if claim_payload is None:
            raise NotFound(f"Claim not found: {claim_id}")
        try:
            assert_no_label_leakage(
                claim_payload,
                context="MVP claim review",
                forbid_agent_output_fields=True,
            )
        except SafetyValidationError as exc:
            raise ValidationFailed("Claim payload contains evaluation-only fields.", exc.findings) from exc
        claim_payload = normalize_claim_payload(claim_payload)

        try:
            self.runtime.validator.validate_claim_input(claim_payload)
        except SchemaValidationError as exc:
            raise ValidationFailed("Stored claim payload does not match input schema.", exc.errors) from exc
        ProductCatalogRegistry.from_generated_dir(
            self.runtime.settings.fraud_generated_dir
        ).validate_relationship(
            product_id=claim_payload["product_id"],
            policy_id=claim_payload["policy_id"],
        )

        self.repository.save_claim(claim_payload, status="reviewing")
        self.repository.save_audit_log(
            event_type="review_started",
            claim_id=claim_payload["claim_id"],
            entity_type="review",
            entity_id=claim_payload["claim_id"],
            metadata={"source": "review_service"},
        )
        workflow_payload, medical_registry_failed = self._enrich_medical_registry(claim_payload)
        try:
            self.runtime.validator.validate_claim_input(workflow_payload)
        except SchemaValidationError as exc:
            raise ValidationFailed("Runtime-enriched claim payload does not match input schema.", exc.errors) from exc

        registry = build_recording_registry(
            self.runtime.template,
            self.runtime.settings.plugin_config_path,
        )
        runner = WorkflowRunner(
            self.runtime.template,
            tool_registry=registry,
            model_provider=self.runtime.model_provider,
            policy_retriever=self.runtime.policy_knowledge.load_retriever(),
            policy_retrieval_options={
                "retrieval_mode": self.runtime.settings.retrieval_mode,
                "top_k": self.runtime.settings.retrieval_top_k,
            },
            specialist_agents=self.runtime.specialist_agents,
            document_extractor=self.runtime.document_extractor,
        )
        output = runner.run(workflow_payload)
        product_registry = ProductCatalogRegistry.from_generated_dir(
            self.runtime.settings.fraud_generated_dir
        )
        if not product_registry.is_active_adjudication_product(claim_payload["product_id"]):
            apply_fail_closed_human_review(
                output,
                reason_code="PRODUCT_ADJUDICATION_PROFILE_UNAVAILABLE",
                reviewer_note=(
                    "The selected product has no active insurer-approved adjudication profile; "
                    "product-specific reviewer confirmation is required."
                ),
            )
        if medical_registry_failed:
            apply_fail_closed_human_review(
                output,
                reviewer_note="Medical registry enrichment failed; reviewer confirmation is required.",
            )
        citation_check = verify_policy_basis(output)
        provenance = build_decision_provenance(
            self.runtime.template,
            model_provider=self.runtime.model_provider,
            tool_registry=registry,
            specialist_agents=self.runtime.specialist_agents,
            policy_sources=[
                self.runtime.settings.policy_documents_path,
                self.runtime.settings.products_json_path,
            ],
            medical_evidence=workflow_payload.get("medical_evidence", {}),
        )
        if not citation_check["verified"]:
            output["reviewer_notes"] = (
                list(output.get("reviewer_notes", []))[:4]
                + [
                    "Policy citation verifier could not confirm every policy basis entry; reviewer confirmation is required."
                ]
            )
        self.runtime.validator.validate_agent_output(output)
        self.repository.save_review(
            output,
            model_provider=getattr(self.runtime.model_provider, "provider_name", "unknown"),
            model_id=getattr(self.runtime.model_provider, "model_id", "unknown"),
            schema_version=self.runtime.template.output_schema.get("version", "1.0.0"),
            workflow_version=provenance["workflow_version"],
        )
        self.repository.save_specialist_agent_reports(
            output["claim_id"],
            list(output.get("specialist_reports") or []),
        )
        self.repository.save_document_extraction_results(
            output["claim_id"],
            list(runner.last_context.get("document_extractions") or []),
        )
        self._persist_tool_records(workflow_payload["claim_id"], registry)
        self.repository.save_audit_log(
            event_type="review_completed",
            claim_id=output["claim_id"],
            entity_type="review",
            entity_id=output["claim_id"],
            metadata={
                "recommended_decision": output["recommended_decision"],
                "requires_human_review": output["requires_human_review"],
                "fraud_suspected": output["fraud_suspected"],
                "citation_verification": citation_check,
                "model_provider": getattr(self.runtime.model_provider, "provider_name", "unknown"),
                "model_id": getattr(self.runtime.model_provider, "model_id", "unknown"),
                "model_narrative": runner.last_context.get("model_narrative", {"status": "not_run"}),
                "decision_provenance": provenance,
                "specialist_report_count": len(output.get("specialist_reports") or []),
                "failed_specialist_report_count": sum(
                    1
                    for report in output.get("specialist_reports") or []
                    if report.get("status") == "failed"
                ),
            },
        )
        return {
            "claim_id": output["claim_id"],
            "review_status": "completed",
            "output": output,
        }

    def _enrich_medical_registry(self, claim_payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        try:
            return RuntimeMedicalRegistryService(self.repository).enrich_claim_payload(claim_payload), False
        except Exception as exc:
            self.repository.save_audit_log(
                event_type="medical_registry_enrichment_failed",
                claim_id=claim_payload.get("claim_id"),
                entity_type="claim",
                entity_id=claim_payload.get("claim_id"),
                metadata={"error_type": type(exc).__name__},
            )
            return claim_payload, True

    def get_review(self, claim_id: str) -> dict[str, Any] | None:
        return self.repository.get_latest_review(claim_id)

    def list_review_queue(self, *, limit: int = 50, sla_hours: int = 24) -> dict[str, Any]:
        return {
            "queue": [
                mask_queue_item(item)
                for item in self.repository.list_review_queue(limit=limit, sla_hours=sla_hours)
            ]
        }

    def save_reviewer_action(self, claim_id: str, action_payload: dict[str, Any]) -> dict[str, Any]:
        if self.repository.get_claim(claim_id) is None:
            raise NotFound(f"Claim not found: {claim_id}")
        action = action_payload.get("action")
        if action not in ALLOWED_REVIEWER_ACTIONS:
            raise ValidationFailed(
                "Reviewer action is not allowed.",
                [f"action must be one of {sorted(ALLOWED_REVIEWER_ACTIONS)}"],
            )
        self.repository.save_reviewer_action(
            claim_id=claim_id,
            action=action,
            reviewer_id=action_payload.get("reviewer_id"),
            reviewer_note=action_payload.get("reviewer_note"),
            override_decision=action_payload.get("override_decision"),
            override_payable_amount=action_payload.get("override_payable_amount"),
            action_payload=action_payload,
        )
        self.repository.save_audit_log(
            event_type="reviewer_action_saved",
            actor_id=action_payload.get("reviewer_id"),
            claim_id=claim_id,
            entity_type="reviewer_action",
            entity_id=claim_id,
            metadata={
                "action": action,
                "override_decision": action_payload.get("override_decision"),
                "has_reviewer_note": bool(action_payload.get("reviewer_note")),
            },
        )
        return {
            "claim_id": claim_id,
            "status": "stored",
            "action": action,
        }

    def list_reviewer_actions(self, claim_id: str) -> dict[str, Any]:
        if self.repository.get_claim(claim_id) is None:
            raise NotFound(f"Claim not found: {claim_id}")
        return {
            "claim_id": claim_id,
            "actions": self.repository.list_reviewer_actions(claim_id),
        }

    def list_audit_logs(self, *, claim_id: str | None = None, limit: int = 100) -> dict[str, Any]:
        if claim_id and self.repository.get_claim(claim_id) is None:
            raise NotFound(f"Claim not found: {claim_id}")
        return {
            "claim_id": claim_id,
            "audit_logs": self.repository.list_audit_logs(claim_id=claim_id, limit=limit),
        }

    def list_specialist_agent_reports(self, claim_id: str) -> dict[str, Any]:
        if self.repository.get_claim(claim_id) is None:
            raise NotFound(f"Claim not found: {claim_id}")
        return {
            "claim_id": claim_id,
            "reports": self.repository.list_specialist_agent_reports(claim_id),
        }

    def _persist_tool_records(self, claim_id: str, registry: RecordingToolRegistry) -> None:
        for record in registry.records:
            result = record.result
            response = result.to_dict()
            self.repository.save_tool_call_log(
                claim_id=claim_id,
                tool_name=result.tool_name,
                tool_version=str(result.metadata.get("contract_version", "1.0.0")),
                request=record.request,
                response=response,
                status=result.status,
                metadata=result.metadata,
                error_code=(result.error or {}).get("error_code") if result.error else None,
                duration_ms=result.duration_ms,
            )
            if result.tool_name == "policy_search" and result.status == "success":
                self.repository.save_retrieval_log(
                    claim_id=claim_id,
                    query=str(record.request.get("query", "")),
                    result=result.result or {"matches": []},
                )
