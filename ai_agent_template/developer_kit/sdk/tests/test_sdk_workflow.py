import json
import tempfile
import unittest
from pathlib import Path

from ai_agent_template.developer_kit.plugins.synthetic import default_synthetic_plugins
from ai_agent_template.developer_kit.plugins.synthetic.coverage_resolver_plugin import (
    SyntheticCoverageResolverPlugin,
)
from ai_agent_template.developer_kit.sdk.claim_agent_sdk import (
    EvaluationRunner,
    KeywordPolicyRetriever,
    MedicalRegistryBundle,
    RegistrySourceMetadata,
    DocumentExtractionService,
    PluginLoader,
    PromptLoader,
    RuntimeMedicalRegistryService,
    SchemaValidator,
    SpecialistPluginLoader,
    StandardsRegistry,
    TemplateBundle,
    ToolRegistry,
    WorkflowLoader,
    WorkflowRunner,
    build_agent_report,
    evaluate_explanation_confidence,
    default_specialist_agents,
    check_document_vlm_conformance,
    load_insurer_medical_routing_rules,
    load_official_edi_rows,
    load_official_kcd_rows,
    verify_policy_basis,
)


WORKSPACE = Path(__file__).resolve().parents[4]
TEMPLATE_ROOT = WORKSPACE / "ai_agent_template"


class SdkWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.template = TemplateBundle.load(TEMPLATE_ROOT)

    def test_template_loader_and_standards_registry(self) -> None:
        standards = StandardsRegistry(self.template)
        self.assertIn("pay", standards.list_decision_codes())
        self.assertIn("COV_OUTPATIENT_COVERED", standards.list_coverage_codes())
        self.assertIn("claim_form", standards.list_document_codes())
        self.assertIn("HUMAN_REVIEW_REQUIRED", standards.list_reason_codes())

    def test_schema_validator_accepts_examples(self) -> None:
        validator = SchemaValidator(self.template)
        validator.validate_claim_input(
            _read_json(TEMPLATE_ROOT / "examples" / "customer_claim_input.example.json")
        )
        validator.validate_agent_output(
            _read_json(TEMPLATE_ROOT / "examples" / "reviewer_assistant_output.example.json")
        )

    def test_medical_registry_bundle_loads_generated_kcd_edi_data(self) -> None:
        bundle = MedicalRegistryBundle.from_generated_dir(WORKSPACE / "data_generator" / "generated")

        self.assertEqual(bundle.kcd_by_submitted_code("SYN-M54")["code"], "M54.5")
        self.assertEqual(bundle.edi_by_submitted_code("TRT-NONCOV-001")["code"], "EDI-MM010")
        self.assertEqual(
            bundle.diagnosis_treatment_rule("M54.5", "EDI-MM010")["relationship"],
            "compatible",
        )
        self.assertEqual(
            bundle.insurer_medical_routing_rule("SYN-MED-ROUTE-AMBIGUOUS-CODE")["routing"],
            "human_review",
        )

    def test_official_registry_importer_normalizes_approved_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            kcd_path = root / "kcd.csv"
            edi_path = root / "edi.csv"
            rules_path = root / "rules.json"
            kcd_path.write_text("분류번호,한글명,동의어\nM54.5,Low back pain,back pain\n", encoding="utf-8")
            edi_path.write_text("수가코드,행위명,분류\nEDI-MM010,Manual therapy,manual\n", encoding="utf-8")
            rules_path.write_text(
                json.dumps(
                    [
                        {
                            "rule_id": "INSURER-MED-ROUTE-AMBIGUOUS-CODE",
                            "rule_version": "2026.1",
                            "rule_name": "Ambiguous Code Review",
                            "description": "Route ambiguous mappings to a medical reviewer.",
                            "routing": "human_review",
                            "reason_code": "AMBIGUOUS_MEDICAL_CODE_MAPPING",
                            "default_confidence": 0.86,
                            "approval_status": "insurer_approved",
                            "owner": "Example Insurer",
                            "effective_from": "2026-01-01",
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            metadata = RegistrySourceMetadata(
                version="official-test-2026.1",
                effective_from="2026-01-01",
                source_file=str(kcd_path),
                source_url="https://official.example/kcd",
                license_note="approved internal test file",
            )

            kcd_rows = load_official_kcd_rows(kcd_path, metadata)
            edi_rows = load_official_edi_rows(edi_path, metadata)
            routing_rules = load_insurer_medical_routing_rules(rules_path)

        self.assertEqual(kcd_rows[0]["code"], "M54.5")
        self.assertFalse(kcd_rows[0]["synthetic"])
        self.assertEqual(edi_rows[0]["code"], "EDI-MM010")
        self.assertEqual(routing_rules[0]["approval_status"], "insurer_approved")

    def test_runtime_medical_registry_enriches_claim_evidence(self) -> None:
        claim = _read_first_jsonl(WORKSPACE / "data_generator" / "generated" / "claims_eval.jsonl")
        claim = json.loads(json.dumps(claim))
        claim.pop("medical_evidence", None)
        claim["claim"]["diagnosis_code"] = "SYN-M54"
        claim["claim"]["treatment_code"] = "TRT-NONCOV-001"

        enriched = RuntimeMedicalRegistryService(_FakeMedicalRegistry()).enrich_claim_payload(claim)
        SchemaValidator(self.template).validate_claim_input(enriched)

        evidence = enriched["medical_evidence"]
        self.assertEqual(evidence["code_mapping_candidates"]["kcd"][0]["code"], "M54.5")
        self.assertEqual(evidence["code_mapping_candidates"]["edi"][0]["code"], "EDI-MM010")
        self.assertEqual(
            evidence["insurer_medical_routing_rules"][0]["reason_code"],
            "DIAGNOSIS_TREATMENT_COMPATIBLE",
        )

    def test_agent_report_builder_returns_standard_shape(self) -> None:
        report = build_agent_report(
            agent_name="medical_review",
            summary="Synthetic medical review report.",
            reason_codes=["DIAGNOSIS_TREATMENT_COMPATIBLE"],
            confidence_factors={
                "evidence_clarity": 0.9,
                "judgment_difficulty": 0.2,
                "uncertainty": 0.1,
            },
        )

        self.assertEqual(report["agent_name"], "medical_review")
        self.assertEqual(report["status"], "success")
        self.assertFalse(report["requires_human_review"])

    def test_document_extraction_service_extracts_synthetic_pdf_metadata(self) -> None:
        claim = _read_first_jsonl(WORKSPACE / "data_generator" / "generated" / "claims_eval.jsonl")
        extractions = DocumentExtractionService(
            generated_dir=WORKSPACE / "data_generator" / "generated"
        ).extract_for_claim(claim)

        self.assertTrue(extractions)
        self.assertIn(extractions[0]["extraction_mode"], {"text_pdf", "ocr_text", "vlm_required"})
        self.assertIn("extracted_fields", extractions[0])

    def test_document_vlm_conformance_probe(self) -> None:
        result = check_document_vlm_conformance(DocumentVlmProbeModelProvider())

        self.assertTrue(result["conformant"])

    def test_workflow_loader_reads_tool_steps(self) -> None:
        tools = WorkflowLoader(self.template).tool_names()
        self.assertEqual(
            tools,
            [
                "policy_search",
                "coverage_resolver",
                "fraud_signal_checker",
                "document_checker",
                "exclusion_checker",
                "payable_calculator",
                "risk_checker",
                "decision_validator",
            ],
        )

    def test_prompt_loader_and_plugin_loader_follow_config(self) -> None:
        prompts = PromptLoader(self.template).load_all()
        self.assertIn("claim_review_prompt.md", prompts)
        self.assertEqual(prompts["claim_review_prompt.md"].version, "1.0.0")

        plugins = PluginLoader(self.template).load_plugins(
            TEMPLATE_ROOT / "developer_kit" / "starter_kit" / "config" / "plugins.yaml"
        )
        self.assertEqual({plugin.name for plugin in plugins}, set(self.template.tool_contracts()))
        specialist_agents = SpecialistPluginLoader().load_plugins(
            TEMPLATE_ROOT / "developer_kit" / "starter_kit" / "config" / "specialist_plugins.synthetic_insurer.yaml",
            model_provider=NarrativeOnlyModelProvider(),
        )
        self.assertEqual(
            [agent.name for agent in specialist_agents],
            [
                "policy_coverage_analysis",
                "document_understanding",
                "medical_review_causality",
                "fraud_risk_analysis",
            ],
        )

    def test_keyword_policy_retriever_returns_schema_valid_matches(self) -> None:
        retriever = KeywordPolicyRetriever.from_template(self.template)
        result = retriever.retrieve(
            {
                "query": "outpatient noncovered deductible limit",
                "top_k": 2,
                "filters": {"product_id": "SYN-MED-001"},
            }
        )
        SchemaValidator(self.template).validate_retrieval_result(result)
        self.assertTrue(result["matches"])
        self.assertIn("retrieval_score", result["matches"][0])
        self.assertIn("citation_id", result["matches"][0])

    def test_workflow_runner_generates_schema_valid_output(self) -> None:
        claim = _read_first_jsonl(WORKSPACE / "data_generator" / "generated" / "claims_eval.jsonl")
        output = _run_workflow(self.template, claim)
        SchemaValidator(self.template).validate_agent_output(output)
        self.assertEqual(output["claim_id"], claim["claim_id"])
        self.assertEqual(output["coverage_code"], "COV_OUTPATIENT_NONCOVERED")
        self.assertEqual(output["recommended_decision"], "partial_pay")
        self.assertEqual(
            [report["agent_name"] for report in output["specialist_reports"]],
            [
                "policy_coverage_analysis",
                "document_understanding",
                "medical_review_causality",
                "fraud_risk_analysis",
            ],
        )
        for report in output["specialist_reports"]:
            SchemaValidator(self.template).validate_agent_report(report)
        document_report = next(
            report
            for report in output["specialist_reports"]
            if report["agent_name"] == "document_understanding"
        )
        self.assertTrue(
            any(item.get("finding_type") == "document_extraction" for item in document_report["findings"])
        )

    def test_workflow_runner_preserves_policy_retrieval_citation_metadata(self) -> None:
        claim = _read_first_jsonl(WORKSPACE / "data_generator" / "generated" / "claims_eval.jsonl")
        registry = ToolRegistry(self.template)
        for plugin in default_synthetic_plugins():
            registry.register(plugin)
        registry.validate_registered_plugins()
        output = WorkflowRunner(
            self.template,
            tool_registry=registry,
            policy_retriever=KeywordPolicyRetriever.from_template(self.template),
        ).run(claim)
        SchemaValidator(self.template).validate_agent_output(output)
        self.assertTrue(any("citation_id" in basis for basis in output["policy_basis"]))
        citation_check = verify_policy_basis(output)
        self.assertTrue(citation_check["verified"])
        self.assertGreater(citation_check["citation_count"], 0)

    def test_workflow_runner_uses_model_for_narrative_only(self) -> None:
        claim = _read_first_jsonl(WORKSPACE / "data_generator" / "generated" / "claims_eval.jsonl")
        registry = ToolRegistry(self.template)
        for plugin in default_synthetic_plugins():
            registry.register(plugin)
        registry.validate_registered_plugins()

        output = WorkflowRunner(
            self.template,
            tool_registry=registry,
            model_provider=NarrativeOnlyModelProvider(),
            policy_retriever=KeywordPolicyRetriever.from_template(self.template),
        ).run(claim)

        self.assertEqual(output["recommended_decision"], "partial_pay")
        self.assertEqual(output["recommended_payable_amount"], output["calculation"]["payable_amount"])
        self.assertEqual(output["confidence"], 0.94)
        self.assertEqual(
            output["confidence_assessment"]["score_source"],
            "deterministic_rules_with_llm_assistance",
        )
        self.assertEqual(output["confidence_assessment"]["deterministic_confidence"], 0.94)
        self.assertEqual(output["confidence_assessment"]["evidence_clarity"], "high")
        self.assertEqual(output["confidence_assessment"]["judgment_difficulty"], "medium")
        self.assertEqual(output["confidence_assessment"]["uncertainty_level"], "low")
        self.assertIn("LLM assessed", output["confidence_assessment"]["uncertainty_explanation"])
        self.assertEqual(output["explanation_confidence"]["source"], "llm_output_validation")
        self.assertEqual(output["explanation_confidence"]["calculation_alignment"], "pass")
        self.assertFalse(output["explanation_confidence"]["unsupported_claims_detected"])
        self.assertGreaterEqual(output["explanation_confidence"]["score"], 0.9)
        self.assertEqual(output["review_summary"], "LLM narrative summary based on locked tool results.")
        self.assertEqual(output["reviewer_notes"], ["LLM note; final decision remains with reviewer."])
        policy_report = next(
            report
            for report in output["specialist_reports"]
            if report["agent_name"] == "policy_coverage_analysis"
        )
        self.assertEqual(policy_report["summary"], "LLM specialist summary based on locked evidence.")

    def test_model_backed_specialist_agents_fallback_when_model_fails(self) -> None:
        claim = _read_first_jsonl(WORKSPACE / "data_generator" / "generated" / "claims_eval.jsonl")
        registry = ToolRegistry(self.template)
        for plugin in default_synthetic_plugins():
            registry.register(plugin)
        registry.validate_registered_plugins()

        output = WorkflowRunner(
            self.template,
            tool_registry=registry,
            model_provider=FailingModelProvider(),
            specialist_agents=default_specialist_agents(FailingModelProvider()),
        ).run(claim)

        self.assertEqual(output["recommended_decision"], "partial_pay")
        self.assertTrue(output["specialist_reports"])
        for report in output["specialist_reports"]:
            self.assertTrue(
                any("deterministic evidence report was used" in warning for warning in report["warnings"])
            )

    def test_explanation_confidence_flags_unsupported_final_language(self) -> None:
        output = {
            "recommended_decision": "partial_pay",
            "recommended_payable_amount": 140000,
            "missing_documents": [],
            "requires_human_review": False,
            "fraud_suspected": False,
            "calculation": {"payable_amount": 140000},
            "policy_basis": [
                {"source": "policy.md", "section": "1", "summary": "basis", "citation_id": "policy.md#1"}
            ],
            "confidence_assessment": {"uncertainty_level": "low"},
            "review_summary": "Payment is confirmed for this claim.",
            "reviewer_notes": [],
        }
        result = evaluate_explanation_confidence(output)
        self.assertTrue(result["unsupported_claims_detected"])
        self.assertLess(result["score"], 0.9)
        self.assertIn("explanation uses final-decision language", result["validation_issues"])

    def test_low_confidence_coverage_forces_human_review(self) -> None:
        claim = _read_first_jsonl(WORKSPACE / "data_generator" / "generated" / "claims_eval.jsonl")
        registry = ToolRegistry(self.template)
        for plugin in default_synthetic_plugins():
            if plugin.name != "coverage_resolver":
                registry.register(plugin)
        registry.register(LowConfidenceCoveragePlugin())
        registry.validate_registered_plugins()

        output = WorkflowRunner(self.template, tool_registry=registry).run(claim)
        self.assertEqual(output["recommended_decision"], "human_review")
        self.assertIn("LOW_CONFIDENCE_COVERAGE_MATCH", output["reason_codes"])

    def test_age_based_condition_forces_human_review_without_fraud(self) -> None:
        claim = _read_first_jsonl(WORKSPACE / "data_generator" / "generated" / "claims_eval.jsonl")
        claim["claim_id"] = "AGE-REVIEW-001"
        claim["insured_profile"]["age_at_service"] = 84
        claim["insured_profile"]["age_band"] = "80plus"
        output = _run_workflow(self.template, claim)
        self.assertEqual(output["recommended_decision"], "human_review")
        self.assertFalse(output["fraud_suspected"])
        self.assertIn("AGE_BASED_REVIEW_REQUIRED", output["reason_codes"])

    def test_fraud_signal_uses_receipt_hash_and_token_aggregates(self) -> None:
        claim = _read_first_jsonl(WORKSPACE / "data_generator" / "generated" / "claims_eval.jsonl")
        claim["claim_id"] = "HASH-FRAUD-001"
        claim["claim_history"]["prior_receipt_hashes"] = [claim["claim"]["receipt_hash"]]
        claim["claim_history"]["same_insured_provider_claims_30d"] = 3
        output = _run_workflow(self.template, claim)
        self.assertEqual(output["recommended_decision"], "human_review")
        self.assertTrue(output["fraud_suspected"])
        self.assertIn("DUPLICATE_RECEIPT_SUSPECTED", output["reason_codes"])
        self.assertIn("SAME_INSURED_PROVIDER_REPEAT_SUSPECTED", output["reason_codes"])
        fraud_report = next(
            report
            for report in output["specialist_reports"]
            if report["agent_name"] == "fraud_risk_analysis"
        )
        self.assertTrue(fraud_report["requires_human_review"])
        self.assertEqual(fraud_report["risk_level"], "high")

    def test_evaluation_runner_scores_workflow_outputs(self) -> None:
        claims = _read_jsonl(WORKSPACE / "data_generator" / "generated" / "claims_eval.jsonl", limit=5)
        labels = _read_jsonl(WORKSPACE / "data_generator" / "generated" / "labels_eval.jsonl", limit=5)
        with tempfile.TemporaryDirectory() as temp_dir:
            outputs_path = Path(temp_dir) / "outputs.jsonl"
            labels_path = Path(temp_dir) / "labels.jsonl"
            _write_jsonl(outputs_path, [_run_workflow(self.template, claim) for claim in claims])
            _write_jsonl(labels_path, labels)
            result = EvaluationRunner(self.template).evaluate(outputs_path, labels_path)
        self.assertEqual(result["dataset_size"], 5)
        self.assertEqual(result["metrics"]["schema_validity"], 1.0)
        self.assertGreaterEqual(result["metrics"]["coverage_accuracy"], 1.0)
        self.assertIn("specialist_report_schema_validity", result["metrics"])
        self.assertIn("document_field_extraction_success_rate", result["metrics"])
        self.assertIn("document_mismatch_detection_rate", result["metrics"])
        self.assertIn("low_confidence_document_human_review_recall", result["metrics"])
        self.assertIn("kcd_mapping_accuracy", result["metrics"])
        self.assertIn("edi_mapping_accuracy", result["metrics"])
        self.assertIn("medical_causality_routing_accuracy", result["metrics"])
        self.assertIn("citation_requirement_pass_rate", result["metrics"])


def _run_workflow(template: TemplateBundle, claim: dict) -> dict:
    registry = ToolRegistry(template)
    for plugin in default_synthetic_plugins():
        registry.register(plugin)
    registry.validate_registered_plugins()
    return WorkflowRunner(
        template,
        tool_registry=registry,
        document_extractor=DocumentExtractionService(
            generated_dir=WORKSPACE / "data_generator" / "generated"
        ),
    ).run(claim)


def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _read_first_jsonl(path: Path) -> dict:
    return _read_jsonl(path, limit=1)[0]


def _read_jsonl(path: Path, limit: int) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                rows.append(json.loads(line))
            if len(rows) >= limit:
                break
    return rows


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


class _FakeMedicalRegistry:
    def get_medical_code(self, code: str, *, code_system: str = "KCD") -> dict | None:
        if code == "SYN-M54":
            return {"code": "M54.5", "code_name": "Low back pain", "source_synthetic_code": code}
        return None

    def get_procedure_code(self, code: str, *, code_system: str = "EDI") -> dict | None:
        if code == "TRT-NONCOV-001":
            return {"code": "EDI-MM010", "code_name": "Manual therapy", "source_synthetic_code": code}
        return None

    def find_diagnosis_treatment_rule(self, kcd_code: str, edi_code: str) -> dict | None:
        if (kcd_code, edi_code) == ("M54.5", "EDI-MM010"):
            return {
                "kcd_code": kcd_code,
                "edi_code": edi_code,
                "relationship": "compatible",
                "medical_necessity_level": "partially_supported",
                "required_documents": ["diagnosis_note"],
                "review_policy": "continue_claim_review",
                "reason_code": "DIAGNOSIS_TREATMENT_COMPATIBLE",
                "version": "test-rule-1.0.0",
            }
        return None

    def find_medical_routing_rule(self, *, reason_code: str, routing: str | None = None) -> dict | None:
        if reason_code == "DIAGNOSIS_TREATMENT_COMPATIBLE":
            return {
                "rule_id": "TEST-MED-ROUTE-CONTINUE",
                "rule_version": "1.0.0",
                "routing": routing or "continue_claim_review",
                "reason_code": reason_code,
                "default_confidence": 0.84,
                "approval_status": "insurer_approved",
            }
        return None


if __name__ == "__main__":
    unittest.main()


class LowConfidenceCoveragePlugin(SyntheticCoverageResolverPlugin):
    def run(self, payload: dict, context: dict) -> dict:
        envelope = super().run(payload, context)
        envelope["result"]["confidence"] = 0.5
        return envelope


class NarrativeOnlyModelProvider:
    provider_name = "test_llm"
    model_id = "test-narrative-model"
    version = "1.0.0"

    def generate_json(self, messages: list[dict], output_schema: dict, options: dict) -> dict:
        schema_name = options.get("schema_name", "")
        if str(schema_name).endswith("_specialist_report_patch"):
            return {
                "summary": "LLM specialist summary based on locked evidence.",
                "findings": [
                    {
                        "finding_type": "model_refined",
                        "summary": "LLM refined the specialist report without changing locked decisions.",
                    }
                ],
                "warnings": [],
                "confidence_factors": {
                    "evidence_clarity": 0.91,
                    "judgment_difficulty": 0.31,
                    "uncertainty": 0.11,
                },
            }
        return {
            "review_summary": "LLM narrative summary based on locked tool results.",
            "reviewer_notes": ["LLM note; final decision remains with reviewer."],
            "confidence_assessment": {
                "evidence_clarity": "high",
                "judgment_difficulty": "medium",
                "uncertainty_level": "low",
                "uncertainty_explanation": "LLM assessed policy basis and calculation as clear.",
                "assessment_basis": [
                    "LLM checked citation presence.",
                    "LLM checked deterministic calculation consistency.",
                ],
            },
        }


class FailingModelProvider:
    provider_name = "failing_llm"
    model_id = "failing-model"
    version = "1.0.0"

    def generate_json(self, messages: list[dict], output_schema: dict, options: dict) -> dict:
        raise RuntimeError("model unavailable")


class DocumentVlmProbeModelProvider:
    provider_name = "document_vlm_probe"
    model_id = "probe"
    version = "1.0.0"

    def generate_json(self, messages: list[dict], output_schema: dict, options: dict) -> dict:
        return {
            "document_type": "medical_receipt",
            "extracted_fields": {"receipt_id": "RCT-SYN-PROBE"},
            "confidence": 0.9,
        }
