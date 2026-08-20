from __future__ import annotations

from typing import Any, Protocol


class ClaimReviewRepository(Protocol):
    def initialize(self) -> None:
        ...

    def save_claim(self, claim_payload: dict[str, Any], status: str = "received") -> None:
        ...

    def get_claim(self, claim_id: str) -> dict[str, Any] | None:
        ...

    def get_fraud_current_claim(self, claim_id: str) -> dict[str, Any] | None:
        ...

    def list_historical_claims_for_claim(self, claim_id: str) -> list[dict[str, Any]]:
        ...

    def list_document_metadata_for_claim(self, claim_id: str) -> list[dict[str, Any]]:
        ...

    def get_document_metadata(self, document_id: str) -> dict[str, Any] | None:
        ...

    def save_uploaded_document(self, metadata: dict[str, Any]) -> None:
        ...

    def seed_fraud_context(
        self,
        *,
        split: str,
        seed_rows: list[dict[str, Any]],
        historical_claims: list[dict[str, Any]],
        document_metadata: list[dict[str, Any]],
        claim_document_links: list[dict[str, Any]],
        source_files: list[str],
    ) -> dict[str, Any]:
        ...

    def seed_medical_registry(
        self,
        *,
        medical_code_registry: list[dict[str, Any]],
        edi_code_registry: list[dict[str, Any]],
        diagnosis_treatment_rules: list[dict[str, Any]],
        source_files: list[str],
        insurer_medical_routing_rules: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        ...

    def get_medical_code(self, code: str, *, code_system: str = "KCD") -> dict[str, Any] | None:
        ...

    def get_procedure_code(self, code: str, *, code_system: str = "EDI") -> dict[str, Any] | None:
        ...

    def find_diagnosis_treatment_rule(self, kcd_code: str, edi_code: str) -> dict[str, Any] | None:
        ...

    def get_medical_routing_rule(self, rule_id: str) -> dict[str, Any] | None:
        ...

    def find_medical_routing_rule(
        self,
        *,
        reason_code: str,
        routing: str | None = None,
    ) -> dict[str, Any] | None:
        ...

    def list_claims(self, *, limit: int = 50) -> list[dict[str, Any]]:
        ...

    def list_review_queue(self, *, limit: int = 50, sla_hours: int = 24) -> list[dict[str, Any]]:
        ...

    def save_review(
        self,
        output: dict[str, Any],
        *,
        model_provider: str,
        model_id: str,
        schema_version: str = "1.0.0",
        workflow_version: str = "1.0.0",
    ) -> None:
        ...

    def get_latest_review(self, claim_id: str) -> dict[str, Any] | None:
        ...

    def save_specialist_agent_reports(self, claim_id: str, reports: list[dict[str, Any]]) -> None:
        ...

    def list_specialist_agent_reports(self, claim_id: str) -> list[dict[str, Any]]:
        ...

    def save_document_extraction_results(self, claim_id: str, results: list[dict[str, Any]]) -> None:
        ...

    def list_document_extraction_results(self, claim_id: str) -> list[dict[str, Any]]:
        ...

    def save_tool_call_log(
        self,
        *,
        claim_id: str,
        tool_name: str,
        tool_version: str,
        request: dict[str, Any],
        response: dict[str, Any] | None,
        status: str,
        metadata: dict[str, Any] | None = None,
        error_code: str | None = None,
        duration_ms: int | None = None,
    ) -> None:
        ...

    def save_reviewer_action(
        self,
        *,
        claim_id: str,
        action: str,
        reviewer_id: str | None = None,
        reviewer_note: str | None = None,
        override_decision: str | None = None,
        override_payable_amount: int | None = None,
        action_payload: dict[str, Any] | None = None,
    ) -> None:
        ...

    def list_reviewer_actions(self, claim_id: str) -> list[dict[str, Any]]:
        ...

    def save_retrieval_log(
        self,
        *,
        query: str,
        result: dict[str, Any],
        claim_id: str | None = None,
    ) -> None:
        ...

    def save_evaluation_run(
        self,
        *,
        run_id: str,
        dataset_name: str,
        claims_path: str,
        labels_path: str,
        output_path: str,
        metrics: dict[str, Any],
        passed: bool,
    ) -> None:
        ...

    def get_evaluation_run(self, run_id: str) -> dict[str, Any] | None:
        ...

    def save_audit_log(
        self,
        *,
        event_type: str,
        entity_type: str,
        actor_id: str | None = None,
        claim_id: str | None = None,
        entity_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        ...

    def list_audit_logs(self, *, claim_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        ...

    def applied_migrations(self) -> list[str]:
        ...
