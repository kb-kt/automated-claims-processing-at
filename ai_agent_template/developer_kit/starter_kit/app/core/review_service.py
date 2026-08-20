from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_agent_template.developer_kit.sdk.claim_agent_sdk import (
    DocumentExtractionService,
    KeywordPolicyRetriever,
    SchemaValidator,
    SpecialistPluginLoader,
    TemplateBundle,
    WorkflowRunner,
    RuntimeMedicalRegistryService,
    NotFoundApiError,
    ProductCatalogRegistry,
    ValidationApiError,
    apply_fail_closed_human_review,
    assert_no_label_leakage,
    build_decision_provenance,
    check_document_vlm_conformance,
    verify_policy_basis,
)
from ai_agent_template.developer_kit.sdk.claim_agent_sdk.model_provider import (
    load_model_provider_config,
    load_model_provider_from_config,
)

from ..db.repository import ClaimReviewRepository
from ..db.sqlite import SQLiteRepository
from .masking import mask_queue_item
from .settings import Settings
from .tooling import RecordingToolRegistry, build_recording_registry


ALLOWED_REVIEWER_ACTIONS = {
    "accept_recommendation",
    "modify_recommendation",
    "request_documents",
    "defer",
    "mark_human_review",
}


class ReviewService:
    def __init__(
        self,
        settings: Settings | None = None,
        repository: ClaimReviewRepository | None = None,
    ):
        self.settings = settings or Settings.load()
        self.template = TemplateBundle.load(self.settings.template_root)
        self.validator = SchemaValidator(self.template)
        self.repository = repository or self._build_default_repository()

    def _build_default_repository(self) -> ClaimReviewRepository:
        return SQLiteRepository(
            db_path=self.settings.sqlite_path,
            schema_path=Path(self.template.root) / "db" / "schema.sql",
            migrations_dir=Path(self.template.root) / "db" / "migrations",
        )

    def submit_claim(self, claim_payload: dict[str, Any]) -> dict[str, Any]:
        assert_no_label_leakage(
            claim_payload,
            context="starter kit claim submission",
            forbid_agent_output_fields=True,
        )
        self.validator.validate_claim_input(claim_payload)
        self._validate_product_policy(claim_payload)
        self.repository.save_claim(claim_payload)
        self.repository.save_audit_log(
            event_type="claim_submitted",
            claim_id=claim_payload["claim_id"],
            entity_type="claim",
            entity_id=claim_payload["claim_id"],
            metadata={"source": "starter_kit"},
        )
        return {
            "claim_id": claim_payload["claim_id"],
            "status": "received",
        }

    def list_claims(self, *, limit: int = 50) -> dict[str, Any]:
        return {"claims": self.repository.list_claims(limit=limit)}

    def run_review(self, claim_id: str | None = None, claim_payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if claim_payload is None:
            if not claim_id:
                raise ValidationApiError("claim_id or claim_payload is required.")
            claim_payload = self.repository.get_claim(claim_id)
        if claim_payload is None:
            raise NotFoundApiError(f"Claim not found: {claim_id}")

        assert_no_label_leakage(
            claim_payload,
            context="starter kit claim review",
            forbid_agent_output_fields=True,
        )
        self.validator.validate_claim_input(claim_payload)
        self._validate_product_policy(claim_payload)
        self.repository.save_claim(claim_payload, status="reviewing")
        self.repository.save_audit_log(
            event_type="review_started",
            claim_id=claim_payload["claim_id"],
            entity_type="review",
            entity_id=claim_payload["claim_id"],
            metadata={"source": "starter_kit"},
        )
        workflow_payload, medical_registry_failed = self._enrich_medical_registry(claim_payload)
        self.validator.validate_claim_input(workflow_payload)
        registry = self._build_tool_registry()
        model_provider = self._load_model_provider()
        specialist_agents = SpecialistPluginLoader().load_plugins(
            self.settings.specialist_config_path,
            model_provider=model_provider,
        )
        runner = WorkflowRunner(
            self.template,
            tool_registry=registry,
            model_provider=model_provider,
            specialist_agents=specialist_agents,
            document_extractor=self._build_document_extractor(),
            policy_retriever=self._load_policy_retriever(),
            policy_retrieval_options={
                "retrieval_mode": self.settings.retrieval_mode,
                "top_k": self.settings.retrieval_top_k,
            },
        )
        output = runner.run(workflow_payload)
        product_registry = ProductCatalogRegistry.from_generated_dir(
            self.settings.fraud_generated_dir
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
            self.template,
            model_provider=model_provider,
            tool_registry=registry,
            specialist_agents=specialist_agents,
            policy_sources=[
                path
                for path in self.template.policy_document_candidates()
                + self.template.product_json_candidates()
                if path.exists()
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
        self.validator.validate_agent_output(output)
        self.repository.save_agent_output(
            output,
            model_provider=getattr(model_provider, "provider_name", "unknown"),
            model_name=getattr(model_provider, "model_id", "unknown"),
            schema_version=self.template.output_schema.get("version", "1.0.0"),
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
                "model_provider": getattr(model_provider, "provider_name", "unknown"),
                "model_id": getattr(model_provider, "model_id", "unknown"),
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
        return output

    def _validate_product_policy(self, claim_payload: dict[str, Any]) -> None:
        ProductCatalogRegistry.from_generated_dir(
            self.settings.fraud_generated_dir
        ).validate_relationship(
            product_id=claim_payload["product_id"],
            policy_id=claim_payload["policy_id"],
        )

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
        return self.repository.get_latest_output(claim_id)

    def list_review_queue(self, *, limit: int = 50, sla_hours: int = 24) -> dict[str, Any]:
        return {
            "queue": [
                mask_queue_item(item)
                for item in self.repository.list_review_queue(limit=limit, sla_hours=sla_hours)
            ]
        }

    def save_reviewer_action(self, claim_id: str, action_payload: dict[str, Any]) -> dict[str, Any]:
        if self.repository.get_claim(claim_id) is None:
            raise NotFoundApiError(f"Claim not found: {claim_id}")
        action = action_payload.get("action")
        if action not in ALLOWED_REVIEWER_ACTIONS:
            raise ValidationApiError(
                "Reviewer action is invalid.",
                [f"allowed={','.join(sorted(ALLOWED_REVIEWER_ACTIONS))}"],
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
        return {"claim_id": claim_id, "status": "stored", "action": action}

    def list_reviewer_actions(self, claim_id: str) -> dict[str, Any]:
        if self.repository.get_claim(claim_id) is None:
            raise NotFoundApiError(f"Claim not found: {claim_id}")
        return {
            "claim_id": claim_id,
            "actions": self.repository.list_reviewer_actions(claim_id),
        }

    def list_audit_logs(self, *, claim_id: str | None = None, limit: int = 100) -> dict[str, Any]:
        if claim_id and self.repository.get_claim(claim_id) is None:
            raise NotFoundApiError(f"Claim not found: {claim_id}")
        return {
            "claim_id": claim_id,
            "audit_logs": self.repository.list_audit_logs(claim_id=claim_id, limit=limit),
        }

    def list_specialist_agent_reports(self, claim_id: str) -> dict[str, Any]:
        if self.repository.get_claim(claim_id) is None:
            raise NotFoundApiError(f"Claim not found: {claim_id}")
        return {
            "claim_id": claim_id,
            "reports": self.repository.list_specialist_agent_reports(claim_id),
        }

    def _build_tool_registry(self) -> RecordingToolRegistry:
        if self.settings.plugin_config_path and self.settings.plugin_config_path.exists():
            return build_recording_registry(self.template, self.settings.plugin_config_path)

        registry = RecordingToolRegistry(self.template)
        from ai_agent_template.developer_kit.plugins.synthetic import default_synthetic_plugins

        for plugin in default_synthetic_plugins():
            registry.register(plugin)
        registry.validate_registered_plugins()
        return registry

    def _load_model_provider(self):
        if self.settings.model_config_path and self.settings.model_config_path.exists():
            return load_model_provider_from_config(self.settings.model_config_path)
        from ai_agent_template.developer_kit.sdk.claim_agent_sdk import MockModelProvider

        return MockModelProvider()

    def _build_document_extractor(self) -> DocumentExtractionService:
        provider = None
        enable_vlm = False
        if self.settings.model_config_path and self.settings.model_config_path.exists():
            config = load_model_provider_config(self.settings.model_config_path, "document_vlm")
            if _enabled(config.get("enabled")):
                provider = load_model_provider_from_config(
                    self.settings.model_config_path,
                    provider_name="document_vlm",
                )
                enable_vlm = bool(check_document_vlm_conformance(provider).get("conformant"))
        return DocumentExtractionService(
            generated_dir=self.settings.fraud_generated_dir,
            document_vlm_provider=provider,
            enable_vlm=enable_vlm,
        )

    def _load_policy_retriever(self):
        if not self.settings.retrieval_enabled:
            return None
        try:
            retriever = KeywordPolicyRetriever.from_template(self.template)
        except Exception:
            return None
        if not retriever.chunks:
            return None
        return retriever

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


def _enabled(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}
