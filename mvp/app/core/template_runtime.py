from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_agent_template.developer_kit.sdk.claim_agent_sdk import (
    DocumentExtractionService,
    PluginLoader,
    SchemaValidator,
    SpecialistAgent,
    SpecialistPluginLoader,
    TemplateBundle,
    ToolRegistry,
    check_document_vlm_conformance,
)
from ai_agent_template.developer_kit.sdk.claim_agent_sdk.model_provider import (
    ModelProvider,
    load_model_provider_config,
    load_model_provider_from_config,
)

from .policy_knowledge_service import PolicyKnowledgeService
from .settings import Settings


@dataclass
class TemplateRuntime:
    settings: Settings
    template: TemplateBundle
    validator: SchemaValidator
    tool_registry: ToolRegistry
    model_provider: ModelProvider
    specialist_agents: list[SpecialistAgent]
    document_extractor: DocumentExtractionService
    document_vlm_readiness: dict[str, Any]
    policy_knowledge: PolicyKnowledgeService

    @classmethod
    def build(cls, settings: Settings | None = None) -> "TemplateRuntime":
        resolved_settings = settings or Settings.load()
        template = TemplateBundle.load(resolved_settings.template_root)
        validator = SchemaValidator(template)
        registry = ToolRegistry(template)
        for plugin in PluginLoader(template).load_plugins(resolved_settings.plugin_config_path):
            registry.register(plugin)
        registry.validate_registered_plugins()
        model_provider = load_model_provider_from_config(resolved_settings.model_config_path)
        specialist_agents = SpecialistPluginLoader().load_plugins(
            resolved_settings.specialist_config_path,
            model_provider=model_provider,
        )
        document_vlm_provider = None
        document_vlm_readiness = {"enabled": False, "conformant": False, "reason": "disabled"}
        document_vlm_config = load_model_provider_config(resolved_settings.model_config_path, "document_vlm")
        if _enabled(document_vlm_config.get("enabled")):
            document_vlm_provider = load_model_provider_from_config(
                resolved_settings.model_config_path,
                provider_name="document_vlm",
            )
            document_vlm_readiness = check_document_vlm_conformance(document_vlm_provider)
            document_vlm_readiness["enabled"] = bool(document_vlm_readiness.get("conformant"))
        document_extractor = DocumentExtractionService(
            generated_dir=resolved_settings.fraud_generated_dir,
            document_vlm_provider=document_vlm_provider,
            enable_vlm=bool(document_vlm_readiness.get("conformant")),
        )
        policy_knowledge = PolicyKnowledgeService(template, resolved_settings)
        policy_knowledge.load_retriever()
        return cls(
            settings=resolved_settings,
            template=template,
            validator=validator,
            tool_registry=registry,
            model_provider=model_provider,
            specialist_agents=specialist_agents,
            document_extractor=document_extractor,
            document_vlm_readiness=document_vlm_readiness,
            policy_knowledge=policy_knowledge,
        )

    def readiness(self) -> dict[str, Any]:
        return {
            "template_root": str(self.template.root),
            "input_schema_version": self.template.input_schema.get("version", "unknown"),
            "output_schema_version": self.template.output_schema.get("version", "unknown"),
            "registered_tools": sorted(self.tool_registry._plugins),  # Read-only status surface.
            "model_provider": getattr(self.model_provider, "provider_name", "unknown"),
            "model_id": getattr(self.model_provider, "model_id", "unknown"),
            "specialist_agents": [getattr(agent, "name", "unknown") for agent in self.specialist_agents],
            "document_extraction": {
                "generated_dir": str(self.document_extractor.generated_dir),
                "vlm_enabled": self.document_extractor.enable_vlm,
                "document_vlm": self.document_vlm_readiness,
            },
            "policy_knowledge": self.policy_knowledge.readiness(),
        }


def _enabled(value: Any) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}
