from __future__ import annotations

from pathlib import Path
from typing import Any

from ai_agent_template.developer_kit.sdk.claim_agent_sdk import (
    PluginLoader,
    KeywordPolicyRetriever,
    SchemaValidator,
    TemplateBundle,
    ToolRegistry,
    WorkflowRunner,
)
from ai_agent_template.developer_kit.sdk.claim_agent_sdk.model_provider import (
    load_model_provider_from_config,
)

from ..db.repository import ClaimReviewRepository
from ..db.sqlite import SQLiteRepository
from .settings import Settings


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
        self.validator.validate_claim_input(claim_payload)
        self.repository.save_claim(claim_payload)
        return {
            "claim_id": claim_payload["claim_id"],
            "status": "received",
        }

    def run_review(self, claim_id: str | None = None, claim_payload: dict[str, Any] | None = None) -> dict[str, Any]:
        if claim_payload is None:
            if not claim_id:
                raise ValueError("claim_id or claim_payload is required")
            claim_payload = self.repository.get_claim(claim_id)
        if claim_payload is None:
            raise KeyError(f"Claim not found: {claim_id}")

        registry = ToolRegistry(self.template)
        for plugin in self._load_plugins():
            registry.register(plugin)
        registry.validate_registered_plugins()
        runner = WorkflowRunner(
            self.template,
            tool_registry=registry,
            model_provider=self._load_model_provider(),
            policy_retriever=self._load_policy_retriever(),
            policy_retrieval_options={
                "retrieval_mode": self.settings.retrieval_mode,
                "top_k": self.settings.retrieval_top_k,
            },
        )
        output = runner.run(claim_payload)
        self.repository.save_claim(claim_payload, status="reviewing")
        self.repository.save_agent_output(output)
        return output

    def get_review(self, claim_id: str) -> dict[str, Any] | None:
        return self.repository.get_latest_output(claim_id)

    def _load_plugins(self) -> list[Any]:
        if self.settings.plugin_config_path and self.settings.plugin_config_path.exists():
            return PluginLoader(self.template).load_plugins(self.settings.plugin_config_path)
        from ai_agent_template.developer_kit.plugins.synthetic import default_synthetic_plugins

        return default_synthetic_plugins()

    def _load_model_provider(self):
        if self.settings.model_config_path and self.settings.model_config_path.exists():
            return load_model_provider_from_config(self.settings.model_config_path)
        from ai_agent_template.developer_kit.sdk.claim_agent_sdk import MockModelProvider

        return MockModelProvider()

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
