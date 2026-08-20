from __future__ import annotations

import json
from datetime import date
from typing import Any

from .explanation_confidence import evaluate_explanation_confidence
from .model_provider import MockModelProvider, ModelProvider
from .schema_validator import SchemaValidator
from .standards_registry import StandardsRegistry
from .specialist_agents import SpecialistAgent, default_specialist_agents
from .template_loader import TemplateBundle
from .tool_registry import ToolCallResult, ToolRegistry
from .agent_report import build_agent_report
from .document_extraction import DocumentExtractor
from .label_leakage import assert_no_label_leakage
from .safety_policy import apply_fail_closed_human_review


class WorkflowRunner:
    """Tool-first claim review workflow runner.

    The runner uses registered tools for factual/rule results, then lets the
    configured model improve reviewer-facing narrative fields only. It does not
    make a final payment decision.
    """

    def __init__(
        self,
        template: TemplateBundle,
        *,
        tool_registry: ToolRegistry,
        model_provider: ModelProvider | None = None,
        policy_retriever: Any | None = None,
        policy_retrieval_options: dict[str, Any] | None = None,
        specialist_agents: list[SpecialistAgent] | None = None,
        document_extractor: DocumentExtractor | None = None,
    ):
        self.template = template
        self.tool_registry = tool_registry
        self.model_provider = model_provider or MockModelProvider()
        self.policy_retriever = policy_retriever
        self.policy_retrieval_options = policy_retrieval_options or {}
        self.document_extractor = document_extractor
        self.specialist_agents = (
            specialist_agents
            if specialist_agents is not None
            else default_specialist_agents(self.model_provider)
        )
        self.validator = SchemaValidator(template)
        self.standards = StandardsRegistry(template)
        self.last_context: dict[str, Any] = {}

    def run(self, claim_payload: dict[str, Any]) -> dict[str, Any]:
        assert_no_label_leakage(
            claim_payload,
            context="claim review input",
            forbid_agent_output_fields=True,
        )
        self.validator.validate_claim_input(claim_payload)
        context: dict[str, Any] = {"claim_payload": claim_payload, "tool_trace": []}
        self._current_context = context
        self.last_context = context
        if self.policy_retriever is not None:
            context["policy_retriever"] = self.policy_retriever
            context["policy_retrieval_options"] = self.policy_retrieval_options
        if self.document_extractor is not None:
            try:
                context["document_extractions"] = self.document_extractor.extract_for_claim(claim_payload)
            except Exception as exc:
                context.setdefault("critical_failures", []).append(
                    {"component": "document_extraction", "error_type": type(exc).__name__}
                )
                context["document_extractions"] = [
                    {
                        "document_id": "unknown",
                        "document_type": "unknown",
                        "extraction_mode": "vlm_required",
                        "extraction_status": "failed",
                        "extraction_confidence_bucket": "low",
                        "extracted_fields": {},
                        "field_statuses": {"document_extraction": "failed"},
                        "error": str(exc),
                    }
                ]

        policy_result = self._run_tool(
            "policy_search",
            {
                "product_id": claim_payload["product_id"],
                "query": _policy_query(claim_payload),
            },
            context,
        )
        if policy_result.status != "success":
            return self._human_review_output(
                claim_payload,
                "COV_UNKNOWN",
                "Unknown coverage",
                ["TOOL_FAILURE", "HUMAN_REVIEW_REQUIRED"],
                _empty_calculation(claim_payload),
                [],
                False,
                "Policy search failed; reviewer confirmation is required.",
            )

        coverage_result = self._run_tool(
            "coverage_resolver",
            {"claim": claim_payload["claim"], "product_id": claim_payload["product_id"]},
            context,
        )
        if coverage_result.status != "success":
            return self._human_review_output(
                claim_payload,
                "COV_UNKNOWN",
                "Unknown coverage",
                ["TOOL_FAILURE", "LOW_CONFIDENCE_COVERAGE_MATCH", "HUMAN_REVIEW_REQUIRED"],
                _empty_calculation(claim_payload),
                _policy_basis(policy_result),
                False,
                "Coverage resolution failed; reviewer confirmation is required.",
            )

        coverage = coverage_result.result or {}
        coverage_code = coverage.get("coverage_code", "COV_UNKNOWN")
        coverage_name = coverage.get("coverage_name") or self.standards.coverage_name(coverage_code)
        if float(coverage.get("confidence", 0)) < 0.75:
            return self._human_review_output(
                claim_payload,
                coverage_code,
                coverage_name,
                ["LOW_CONFIDENCE_COVERAGE_MATCH", "HUMAN_REVIEW_REQUIRED"],
                _empty_calculation(claim_payload),
                _policy_basis(policy_result),
                False,
                "Coverage match confidence is below the allowed threshold; reviewer confirmation is required.",
            )

        fraud_result = self._run_tool(
            "fraud_signal_checker",
            {
                "insured_profile": claim_payload["insured_profile"],
                "claim": claim_payload["claim"],
                "claim_history": claim_payload["claim_history"],
                "signals": claim_payload["signals"],
            },
            context,
        )
        if fraud_result.status != "success":
            return self._human_review_output(
                claim_payload,
                coverage_code,
                coverage_name,
                ["TOOL_FAILURE", "HUMAN_REVIEW_REQUIRED"],
                _empty_calculation(claim_payload),
                _policy_basis(policy_result),
                False,
                "Fraud signal tool failed; reviewer confirmation is required.",
            )
        fraud = fraud_result.result or {}
        if fraud.get("fraud_suspected"):
            reason_codes = _unique(
                fraud.get("fraud_reason_codes", [])
                + ["FRAUD_SIGNAL", "HUMAN_REVIEW_REQUIRED"]
            )
            return self._human_review_output(
                claim_payload,
                coverage_code,
                coverage_name,
                reason_codes,
                _empty_calculation(claim_payload),
                _policy_basis(policy_result),
                True,
                "Fraud or duplicate receipt signals were detected; human review is required.",
            )
        if fraud.get("routing") == "human_review" or fraud.get("requires_human_review"):
            reason_codes = _unique(
                fraud.get("fraud_reason_codes", [])
                + ["HUMAN_REVIEW_REQUIRED"]
            )
            return self._human_review_output(
                claim_payload,
                coverage_code,
                coverage_name,
                reason_codes,
                _empty_calculation(claim_payload),
                _policy_basis(policy_result),
                False,
                "Fraud_Check routing requires human review before the claim can proceed.",
            )

        policy_reason = _policy_invalid_reason(claim_payload)
        if policy_reason:
            reason_code, summary = policy_reason
            return self._output(
                claim_payload,
                "deny",
                coverage_code,
                coverage_name,
                [],
                [reason_code],
                _empty_calculation(claim_payload),
                _policy_basis(policy_result),
                False,
                False,
                0.93,
                summary,
                ["Review policy status and coverage period before final decision."],
            )

        documents_result = self._run_tool(
            "document_checker",
            {
                "coverage_code": coverage_code,
                "submitted_documents": claim_payload.get("documents", []),
            },
            context,
        )
        if documents_result.status != "success":
            return self._human_review_output(
                claim_payload,
                coverage_code,
                coverage_name,
                ["TOOL_FAILURE", "HUMAN_REVIEW_REQUIRED"],
                _empty_calculation(claim_payload),
                _policy_basis(policy_result),
                False,
                "Document checker failed; reviewer confirmation is required.",
            )
        documents = documents_result.result or {}
        missing_documents = documents.get("missing_documents", [])
        if missing_documents:
            return self._output(
                claim_payload,
                "request_documents",
                coverage_code,
                coverage_name,
                missing_documents,
                ["MISSING_REQUIRED_DOCUMENT"],
                _empty_calculation(claim_payload),
                _policy_basis(policy_result),
                False,
                False,
                0.96,
                "Required documents are missing; request additional documents before review.",
                ["Do not calculate final payable amount until required documents are complete."],
            )

        exclusion_result = self._run_tool(
            "exclusion_checker",
            {
                "claim": claim_payload["claim"],
                "policy": claim_payload["policy"],
                "signals": claim_payload["signals"],
            },
            context,
        )
        if exclusion_result.status != "success":
            return self._human_review_output(
                claim_payload,
                coverage_code,
                coverage_name,
                ["TOOL_FAILURE", "HUMAN_REVIEW_REQUIRED"],
                _empty_calculation(claim_payload),
                _policy_basis(policy_result),
                False,
                "Exclusion checker failed; reviewer confirmation is required.",
            )
        exclusion = exclusion_result.result or {}
        if exclusion.get("excluded"):
            return self._output(
                claim_payload,
                "deny",
                coverage_code,
                coverage_name,
                [],
                exclusion.get("exclusion_reason_codes", ["UNSUPPORTED_TREATMENT_EXCLUDED"]),
                _empty_calculation(claim_payload),
                _policy_basis(policy_result),
                False,
                False,
                0.92,
                exclusion.get("explanation") or "A clear exclusion condition applies.",
                ["Review exclusion basis before final decision."],
            )

        calculation_result = self._run_tool(
            "payable_calculator",
            {
                "coverage_code": coverage_code,
                "claimed_amount": claim_payload["claim"]["claimed_amount"],
                "claim": claim_payload["claim"],
            },
            context,
        )
        if calculation_result.status != "success":
            return self._human_review_output(
                claim_payload,
                coverage_code,
                coverage_name,
                ["TOOL_FAILURE", "HUMAN_REVIEW_REQUIRED"],
                _empty_calculation(claim_payload),
                _policy_basis(policy_result),
                False,
                "Payable calculation failed; reviewer confirmation is required.",
            )
        calculation = calculation_result.result or _empty_calculation(claim_payload)

        risk_result = self._run_tool(
            "risk_checker",
            {
                "insured_profile": claim_payload["insured_profile"],
                "claim": claim_payload["claim"],
                "claim_history": claim_payload["claim_history"],
                "signals": claim_payload["signals"],
            },
            context,
        )
        if risk_result.status != "success":
            return self._human_review_output(
                claim_payload,
                coverage_code,
                coverage_name,
                ["TOOL_FAILURE", "HUMAN_REVIEW_REQUIRED"],
                calculation,
                _policy_basis(policy_result),
                False,
                "Risk checker failed; reviewer confirmation is required.",
            )
        risk = risk_result.result or {}
        if risk.get("requires_human_review"):
            reason_codes = _unique(
                risk.get("risk_reason_codes", [])
                + ["HUMAN_REVIEW_REQUIRED", "PROVISIONAL_CALCULATION_AVAILABLE"]
            )
            return self._human_review_output(
                claim_payload,
                coverage_code,
                coverage_name,
                reason_codes,
                calculation,
                _policy_basis(policy_result),
                False,
                "A mandatory human review rule applies; provisional calculation is available.",
            )

        if calculation.get("limit_applied"):
            decision = "partial_pay"
            reason_codes = [
                "COVERED_INCIDENT",
                "PER_CLAIM_LIMIT_APPLIED",
                "DEDUCTIBLE_APPLIED",
            ]
            summary = "Claim appears covered, but a per-claim limit applies before deductible."
        else:
            decision = "pay"
            reason_codes = ["COVERED_INCIDENT", "DOCUMENTS_COMPLETE", "DEDUCTIBLE_APPLIED"]
            summary = "Claim appears covered and required documents are complete."

        return self._output(
            claim_payload,
            decision,
            coverage_code,
            coverage_name,
            [],
            reason_codes,
            calculation,
            _policy_basis(policy_result),
            False,
            False,
            0.94,
            summary,
            ["This is an assistant recommendation; reviewer retains final authority."],
        )

    def _run_tool(
        self,
        tool_name: str,
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> ToolCallResult:
        result = self.tool_registry.run(tool_name, payload, context)
        context.setdefault("tool_trace", []).append(result.to_dict())
        return result

    def _human_review_output(
        self,
        claim_payload: dict[str, Any],
        coverage_code: str,
        coverage_name: str,
        reason_codes: list[str],
        calculation: dict[str, Any],
        policy_basis: list[dict[str, Any]],
        fraud_suspected: bool,
        review_summary: str,
    ) -> dict[str, Any]:
        return self._output(
            claim_payload,
            "human_review",
            coverage_code,
            coverage_name,
            [],
            reason_codes,
            calculation,
            policy_basis,
            True,
            fraud_suspected,
            0.86,
            review_summary,
            ["Human review is mandatory before any final payment decision."],
        )

    def _output(
        self,
        claim_payload: dict[str, Any],
        decision: str,
        coverage_code: str,
        coverage_name: str,
        missing_documents: list[str],
        reason_codes: list[str],
        calculation: dict[str, Any],
        policy_basis: list[dict[str, Any]],
        requires_human_review: bool,
        fraud_suspected: bool,
        confidence: float,
        review_summary: str,
        reviewer_notes: list[str],
    ) -> dict[str, Any]:
        output = {
            "claim_id": claim_payload["claim_id"],
            "recommended_decision": decision,
            "recommended_payable_amount": int(calculation.get("payable_amount", 0)),
            "coverage_code": coverage_code,
            "coverage_name": coverage_name,
            "missing_documents": sorted(set(missing_documents)),
            "reason_codes": _unique(reason_codes),
            "requires_human_review": requires_human_review,
            "fraud_suspected": fraud_suspected,
            "confidence": confidence,
            "confidence_assessment": _default_confidence_assessment(
                confidence=confidence,
                decision=decision,
                reason_codes=reason_codes,
                missing_documents=missing_documents,
                policy_basis=policy_basis,
                requires_human_review=requires_human_review,
                fraud_suspected=fraud_suspected,
                calculation=calculation,
            ),
            "calculation": {
                "claimed_amount": int(calculation.get("claimed_amount", 0)),
                "eligible_amount": int(calculation.get("eligible_amount", 0)),
                "limit_applied": bool(calculation.get("limit_applied", False)),
                "deductible_amount": int(calculation.get("deductible_amount", 0)),
                "payable_amount": int(calculation.get("payable_amount", 0)),
            },
            "policy_basis": policy_basis
            or [
                {
                    "source": "policy_documents.md",
                    "section": "synthetic-policy",
                    "summary": "Synthetic policy basis was not found; reviewer should confirm.",
                }
            ],
            "review_summary": review_summary,
            "reviewer_notes": reviewer_notes,
        }
        self._apply_model_narrative(output, claim_payload)
        self._attach_specialist_reports(output, claim_payload, getattr(self, "_current_context", {}))
        if getattr(self, "_current_context", {}).get("critical_failures"):
            apply_fail_closed_human_review(
                output,
                reviewer_note="A decision-critical evidence dependency failed; reviewer confirmation is required.",
            )
        decision_validation = self.tool_registry.run(
            "decision_validator",
            {"agent_output": output},
            {"claim_payload": claim_payload, "output_schema": self.template.output_schema},
        )
        if decision_validation.status != "success" or not (decision_validation.result or {}).get("valid"):
            output["recommended_decision"] = "human_review"
            output["requires_human_review"] = True
            output["recommended_payable_amount"] = output["calculation"]["payable_amount"]
            output["reason_codes"] = _unique(output["reason_codes"] + ["TOOL_FAILURE", "HUMAN_REVIEW_REQUIRED"])
            output["reviewer_notes"].append("Decision validator flagged the output.")
        output["explanation_confidence"] = evaluate_explanation_confidence(output)
        self.validator.validate_agent_output(output)
        return output

    def _attach_specialist_reports(
        self,
        output: dict[str, Any],
        claim_payload: dict[str, Any],
        context: dict[str, Any],
    ) -> None:
        reports: list[dict[str, Any]] = []
        force_human_review = False
        for agent in self.specialist_agents:
            try:
                report = agent.run(
                    {"claim_payload": claim_payload, "agent_output": output},
                    self._specialist_context(context),
                )
                self.validator.validate_agent_report(report)
            except Exception as exc:
                report = build_agent_report(
                    agent_name=getattr(agent, "name", "specialist_agent"),
                    agent_version=getattr(agent, "version", "1.0.0"),
                    status="failed",
                    summary="Specialist agent failed; reviewer confirmation is required.",
                    reason_codes=["SPECIALIST_AGENT_FAILURE"],
                    risk_level="high",
                    requires_human_review=True,
                    confidence_factors={
                        "evidence_clarity": 0.0,
                        "judgment_difficulty": 1.0,
                        "uncertainty": 1.0,
                    },
                    warnings=[str(exc)],
                )
            reports.append(report)
            force_human_review = force_human_review or bool(report.get("requires_human_review"))

        if reports:
            output["specialist_reports"] = reports
        if force_human_review and not output.get("requires_human_review"):
            output["recommended_decision"] = "human_review"
            output["requires_human_review"] = True
            output["reason_codes"] = _unique(
                output.get("reason_codes", [])
                + ["SPECIALIST_AGENT_HUMAN_REVIEW", "HUMAN_REVIEW_REQUIRED"]
            )
            output["reviewer_notes"] = _unique(
                list(output.get("reviewer_notes", []))
                + ["A specialist agent requires human review before final disposition."]
            )

    @staticmethod
    def _specialist_context(context: dict[str, Any]) -> dict[str, Any]:
        converted_trace: list[dict[str, Any]] = []
        for item in context.get("tool_trace", []):
            if hasattr(item, "result"):
                converted_trace.append(item.result.to_dict())
            elif isinstance(item, dict):
                converted_trace.append(item)
        return {**context, "tool_trace": converted_trace}

    def _apply_model_narrative(self, output: dict[str, Any], claim_payload: dict[str, Any]) -> None:
        narrative_schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["review_summary", "reviewer_notes", "confidence_assessment"],
            "properties": {
                "review_summary": {"type": "string", "minLength": 1},
                "reviewer_notes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 5,
                },
                "confidence_assessment": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "evidence_clarity",
                        "judgment_difficulty",
                        "uncertainty_level",
                        "uncertainty_explanation",
                        "assessment_basis",
                    ],
                    "properties": {
                        "evidence_clarity": {
                            "type": "string",
                            "enum": ["high", "medium", "low"],
                        },
                        "judgment_difficulty": {
                            "type": "string",
                            "enum": ["low", "medium", "high"],
                        },
                        "uncertainty_level": {
                            "type": "string",
                            "enum": ["low", "medium", "high"],
                        },
                        "uncertainty_explanation": {"type": "string", "minLength": 1},
                        "assessment_basis": {
                            "type": "array",
                            "items": {"type": "string", "minLength": 1},
                            "minItems": 1,
                            "maxItems": 5,
                        },
                    },
                },
            },
        }
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an insurance claim reviewer assistant. Return JSON only. "
                    "Do not change recommended_decision, payable amount, coverage_code, "
                    "reason_codes, fraud_suspected, requires_human_review, calculation, "
                    "policy_basis, or deterministic_confidence. Generate only concise "
                    "reviewer-facing summary, notes, evidence clarity, judgment difficulty, "
                    "and uncertainty explanation."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "claim_context": {
                            "claim_id": claim_payload["claim_id"],
                            "product_id": claim_payload["product_id"],
                            "insured_profile": claim_payload.get("insured_profile", {}),
                            "claim": claim_payload.get("claim", {}),
                            "documents": claim_payload.get("documents", []),
                            "claim_history": claim_payload.get("claim_history", {}),
                            "signals": claim_payload.get("signals", {}),
                        },
                        "deterministic_recommendation": output,
                    },
                    ensure_ascii=False,
                ),
            },
        ]
        try:
            narrative = self.model_provider.generate_json(
                messages,
                narrative_schema,
                {
                    "schema_name": "claim_review_narrative",
                    "fallback_summary": output["review_summary"],
                },
            )
        except Exception as exc:
            getattr(self, "_current_context", {}).update(
                {
                    "model_narrative": {
                        "status": "failed",
                        "criticality": "advisory",
                        "error_type": type(exc).__name__,
                    }
                }
            )
            output["reviewer_notes"] = _unique(
                list(output.get("reviewer_notes") or [])
                + ["LLM narrative assistance was unavailable; this recommendation uses deterministic evidence only."]
            )
            return
        getattr(self, "_current_context", {}).update(
            {"model_narrative": {"status": "success", "criticality": "advisory"}}
        )
        summary = narrative.get("review_summary")
        notes = narrative.get("reviewer_notes")
        if isinstance(summary, str) and summary.strip():
            output["review_summary"] = summary.strip()
        if isinstance(notes, list) and all(isinstance(note, str) for note in notes):
            cleaned_notes = [note.strip() for note in notes if note.strip()]
            if cleaned_notes:
                output["reviewer_notes"] = cleaned_notes
        assessment = narrative.get("confidence_assessment")
        if isinstance(assessment, dict):
            _merge_llm_confidence_assessment(output["confidence_assessment"], assessment)


def _policy_query(claim_payload: dict[str, Any]) -> str:
    claim = claim_payload["claim"]
    return " ".join(
        [
            claim.get("care_setting", ""),
            claim.get("benefit_category", ""),
            claim.get("treatment_code", ""),
        ]
    )


def _policy_basis(policy_result: ToolCallResult) -> list[dict[str, Any]]:
    if policy_result.status != "success":
        return []
    matches = (policy_result.result or {}).get("matches", [])
    basis: list[dict[str, Any]] = []
    optional_fields = [
        "chunk_id",
        "product_id",
        "product_version",
        "effective_date",
        "coverage_code",
        "clause_id",
        "citation_id",
        "retrieval_score",
        "retrieval_method",
    ]
    for item in matches[:3]:
        entry: dict[str, Any] = {
            "source": item.get("source", "policy_documents.md"),
            "section": item.get("section", "synthetic-policy"),
            "summary": item.get("summary", "Synthetic policy basis."),
        }
        for field in optional_fields:
            if item.get(field) not in ("", None):
                entry[field] = item[field]
        basis.append(entry)
    return basis


def _empty_calculation(claim_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "claimed_amount": int(claim_payload["claim"].get("claimed_amount", 0)),
        "eligible_amount": 0,
        "limit_applied": False,
        "deductible_amount": 0,
        "payable_amount": 0,
    }


def _default_confidence_assessment(
    *,
    confidence: float,
    decision: str,
    reason_codes: list[str],
    missing_documents: list[str],
    policy_basis: list[dict[str, Any]],
    requires_human_review: bool,
    fraud_suspected: bool,
    calculation: dict[str, Any],
) -> dict[str, Any]:
    has_citation = any(item.get("citation_id") or item.get("clause_id") for item in policy_basis)
    if requires_human_review or fraud_suspected:
        evidence_clarity = "medium" if has_citation else "low"
        judgment_difficulty = "high"
        uncertainty_level = "high"
        explanation = "Human review is required because risk, fraud, or workflow uncertainty was detected."
    elif missing_documents:
        evidence_clarity = "high"
        judgment_difficulty = "low"
        uncertainty_level = "medium"
        explanation = "Required documents are missing, so payable review should wait for supplementation."
    elif decision == "deny":
        evidence_clarity = "medium" if has_citation else "low"
        judgment_difficulty = "medium"
        uncertainty_level = "medium"
        explanation = "Denial recommendation depends on policy status, coverage period, or exclusion basis."
    elif calculation.get("limit_applied"):
        evidence_clarity = "high" if has_citation else "medium"
        judgment_difficulty = "medium"
        uncertainty_level = "low"
        explanation = "Coverage is matched and the main uncertainty is limit and deductible application."
    else:
        evidence_clarity = "high" if has_citation else "medium"
        judgment_difficulty = "low"
        uncertainty_level = "low"
        explanation = "Coverage, documents, and calculation results are aligned by deterministic tools."

    basis = [
        "Final confidence score is deterministic and is not replaced by LLM self-confidence.",
        f"Decision path: {decision}.",
    ]
    if reason_codes:
        basis.append(f"Reason codes: {', '.join(_unique(reason_codes)[:4])}.")
    if has_citation:
        basis.append("Policy basis includes citation or clause metadata.")
    if fraud_suspected:
        basis.append("Fraud signal requires reviewer confirmation.")

    return {
        "score_source": "deterministic_rules_with_llm_assistance",
        "deterministic_confidence": float(confidence),
        "evidence_clarity": evidence_clarity,
        "judgment_difficulty": judgment_difficulty,
        "uncertainty_level": uncertainty_level,
        "uncertainty_explanation": explanation,
        "assessment_basis": basis[:5],
    }


def _merge_llm_confidence_assessment(target: dict[str, Any], update: dict[str, Any]) -> None:
    for field, allowed in {
        "evidence_clarity": {"high", "medium", "low"},
        "judgment_difficulty": {"low", "medium", "high"},
        "uncertainty_level": {"low", "medium", "high"},
    }.items():
        value = update.get(field)
        if isinstance(value, str) and value in allowed:
            target[field] = value

    explanation = update.get("uncertainty_explanation")
    if isinstance(explanation, str) and explanation.strip():
        target["uncertainty_explanation"] = explanation.strip()

    basis = update.get("assessment_basis")
    if isinstance(basis, list) and all(isinstance(item, str) for item in basis):
        cleaned = [item.strip() for item in basis if item.strip()]
        if cleaned:
            target["assessment_basis"] = cleaned[:5]


def _policy_invalid_reason(claim_payload: dict[str, Any]) -> tuple[str, str] | None:
    policy = claim_payload["policy"]
    claim = claim_payload["claim"]
    if policy.get("status") != "active":
        return "LAPSED_POLICY", "Policy status is not active; deny review is recommended."
    coverage_start = date.fromisoformat(policy["coverage_start_date"])
    coverage_end = date.fromisoformat(policy["coverage_end_date"])
    incident_date = date.fromisoformat(claim["incident_date"])
    treatment_start = date.fromisoformat(claim["treatment_start_date"])
    if incident_date < coverage_start or treatment_start < coverage_start:
        return (
            "INCIDENT_BEFORE_COVERAGE_START",
            "Incident or treatment date is before coverage start; deny review is recommended.",
        )
    if incident_date > coverage_end or treatment_start > coverage_end:
        return (
            "INCIDENT_AFTER_COVERAGE_END",
            "Incident or treatment date is after coverage end; deny review is recommended.",
        )
    return None


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            result.append(value)
            seen.add(value)
    return result
