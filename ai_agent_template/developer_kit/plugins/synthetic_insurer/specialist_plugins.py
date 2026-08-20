from __future__ import annotations

from typing import Any

from ai_agent_template.developer_kit.sdk.claim_agent_sdk.specialist_agents import (
    DocumentUnderstandingAgent,
    FraudRiskAnalysisAgent,
    MedicalReviewCausalityAgent,
    ModelBackedSpecialistAgent,
    PolicyCoverageAnalysisAgent,
)


class SyntheticInsurerPolicyCoveragePlugin(ModelBackedSpecialistAgent):
    def __init__(self, model_provider: Any | None = None):
        super().__init__(_SyntheticInsurerPolicyCoverageAgent(), model_provider)


class SyntheticInsurerDocumentUnderstandingPlugin(ModelBackedSpecialistAgent):
    def __init__(self, model_provider: Any | None = None):
        super().__init__(_SyntheticInsurerDocumentUnderstandingAgent(), model_provider)


class SyntheticInsurerMedicalReviewPlugin(ModelBackedSpecialistAgent):
    def __init__(self, model_provider: Any | None = None):
        super().__init__(_SyntheticInsurerMedicalReviewAgent(), model_provider)


class SyntheticInsurerFraudRiskPlugin(ModelBackedSpecialistAgent):
    def __init__(self, model_provider: Any | None = None):
        super().__init__(_SyntheticInsurerFraudRiskAgent(), model_provider)


class _SyntheticInsurerPolicyCoverageAgent(PolicyCoverageAnalysisAgent):
    def run(self, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        report = super().run(payload, context)
        report["summary"] = (
            "[Synthetic Insurer A] "
            + report["summary"]
            + " Guideline profile applies conservative citation review for riders, exclusions, limits, and deductibles."
        )
        report["warnings"] = _prepend_synthetic_warning(report.get("warnings", []))
        report["findings"].append(
            {
                "finding_type": "synthetic_insurer_guideline",
                "clause_id": "SYN-INSURER-A-POLICY-001",
                "summary": "Synthetic insurer profile requires reviewer confirmation when citation verification is partial or failed.",
            }
        )
        return report


class _SyntheticInsurerDocumentUnderstandingAgent(DocumentUnderstandingAgent):
    def run(self, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        report = super().run(payload, context)
        report["summary"] = (
            "[Synthetic Insurer A] "
            + report["summary"]
            + " Document fields are treated as structured test evidence, not official OCR/VLM extraction."
        )
        report["warnings"] = _prepend_synthetic_warning(report.get("warnings", []))
        report["findings"].append(
            {
                "finding_type": "synthetic_document_rule",
                "summary": "Synthetic insurer profile requires receipt, statement, and diagnosis-note consistency before payment recommendation.",
            }
        )
        return report


class _SyntheticInsurerMedicalReviewAgent(MedicalReviewCausalityAgent):
    def run(self, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        report = super().run(payload, context)
        report["summary"] = (
            "[Synthetic Insurer A] "
            + report["summary"]
            + " Medical causality is evaluated with synthetic KCD/EDI-style guidelines until official registries are imported."
        )
        report["warnings"] = _prepend_synthetic_warning(report.get("warnings", []))
        report["findings"].append(
            {
                "finding_type": "synthetic_medical_guideline",
                "summary": "Synthetic insurer profile flags repeated diagnosis, frequent manual therapy, and pre-existing-condition signals for reviewer attention.",
            }
        )
        return report


class _SyntheticInsurerFraudRiskAgent(FraudRiskAnalysisAgent):
    def run(self, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        report = super().run(payload, context)
        report["summary"] = (
            "[Synthetic Insurer A] "
            + report["summary"]
            + " Fraud suspicion is always routed to human review and never to automatic denial."
        )
        report["warnings"] = _prepend_synthetic_warning(report.get("warnings", []))
        report["findings"].append(
            {
                "finding_type": "synthetic_fraud_guideline",
                "summary": "Synthetic insurer profile uses tokenized receipt hashes and aggregate behavior counters only.",
            }
        )
        return report


def _prepend_synthetic_warning(warnings: list[str]) -> list[str]:
    return [
        "Synthetic insurer plugin pack is for development and evaluation only; it is not insurer-approved production logic.",
        *warnings,
    ]
