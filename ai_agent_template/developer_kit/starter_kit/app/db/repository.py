from __future__ import annotations

from typing import Any, Protocol


class ClaimReviewRepository(Protocol):
    """Persistence boundary for claim review services.

    A future PostgreSQL repository should implement this same protocol so API
    and workflow services can stay database-agnostic.
    """

    def save_claim(self, claim_payload: dict[str, Any], status: str = "received") -> None:
        ...

    def get_claim(self, claim_id: str) -> dict[str, Any] | None:
        ...

    def save_agent_output(self, output: dict[str, Any]) -> None:
        ...

    def get_latest_output(self, claim_id: str) -> dict[str, Any] | None:
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
        error_code: str | None = None,
        duration_ms: int | None = None,
    ) -> None:
        ...

    def save_reviewer_action(
        self,
        *,
        claim_id: str,
        action_type: str,
        reviewer_note: str | None = None,
        override_decision: str | None = None,
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

