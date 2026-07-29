import json
import re
import unittest
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]


class TemplateContractsTest(unittest.TestCase):
    def test_json_files_are_parseable(self) -> None:
        for path in BASE_DIR.rglob("*.json"):
            with self.subTest(path=str(path.relative_to(BASE_DIR))):
                with path.open("r", encoding="utf-8") as file:
                    json.load(file)

    def test_json_schemas_use_draft_2020_12(self) -> None:
        for path in (BASE_DIR / "schemas").glob("*.schema.json"):
            with self.subTest(schema=path.name):
                schema = _read_json(path)
                self.assertEqual(
                    schema.get("$schema"),
                    "https://json-schema.org/draft/2020-12/schema",
                )
                self.assertEqual(schema.get("version"), "1.0.0")

    def test_tool_contracts_match_workflow_tool_refs(self) -> None:
        contract_names = {
            _read_json(path)["tool_name"]
            for path in (BASE_DIR / "tools" / "contracts").glob("*.contract.json")
        }
        workflow_text = (BASE_DIR / "workflows" / "claim_review_workflow.yaml").read_text(
            encoding="utf-8"
        )
        workflow_tools = set(re.findall(r"^\s+tool:\s+([a-z_]+)\s*$", workflow_text, re.MULTILINE))

        self.assertEqual(
            contract_names,
            {
                "policy_search",
                "coverage_resolver",
                "document_checker",
                "exclusion_checker",
                "payable_calculator",
                "risk_checker",
                "fraud_signal_checker",
                "decision_validator",
            },
        )
        self.assertEqual(workflow_tools, contract_names)

    def test_contract_shape(self) -> None:
        required = {
            "tool_name",
            "version",
            "description",
            "input_schema",
            "output_schema",
            "timeout_ms",
            "failure_policy",
            "owner",
        }
        for path in (BASE_DIR / "tools" / "contracts").glob("*.contract.json"):
            with self.subTest(contract=path.name):
                contract = _read_json(path)
                self.assertTrue(required <= set(contract))
                self.assertRegex(contract["version"], r"^\d+\.\d+\.\d+$")
                self.assertIn(contract["failure_policy"], {"human_review", "fail", "retry"})

    def test_examples_follow_core_contract_rules(self) -> None:
        input_example = _read_json(BASE_DIR / "examples" / "customer_claim_input.example.json")
        output_example = _read_json(BASE_DIR / "examples" / "reviewer_assistant_output.example.json")

        for key in _read_json(BASE_DIR / "schemas" / "claim_review_input.schema.json")["required"]:
            self.assertIn(key, input_example)
        for key in _read_json(BASE_DIR / "schemas" / "claim_review_output.schema.json")["required"]:
            self.assertIn(key, output_example)

        self.assertEqual(
            output_example["recommended_payable_amount"],
            output_example["calculation"]["payable_amount"],
        )
        if output_example["requires_human_review"]:
            self.assertEqual(output_example["recommended_decision"], "human_review")
        if output_example["fraud_suspected"]:
            self.assertTrue(output_example["requires_human_review"])

    def test_model_config_uses_requested_provider_defaults(self) -> None:
        text = (BASE_DIR / "config" / "model_config.yaml").read_text(encoding="utf-8")
        self.assertIn("base_url: https://m2.geniemars.kt.co.kr:10601/v1", text)
        self.assertIn("api_key: dummy", text)
        self.assertIn("model_id: gemma-4-26B-4aB-it", text)
        self.assertIn("active_provider: general_llm", text)
        app_config = (BASE_DIR / "config" / "app_config.yaml").read_text(encoding="utf-8")
        self.assertIn("api_framework: FastAPI", app_config)
        self.assertIn('json_schema_draft: "2020-12"', app_config)

    def test_sqlite_schema_contains_required_tables(self) -> None:
        sql = (BASE_DIR / "db" / "schema.sql").read_text(encoding="utf-8")
        for table in [
            "claim_reviews",
            "agent_outputs",
            "tool_call_logs",
            "reviewer_actions",
            "evaluation_runs",
            "config_versions",
        ]:
            with self.subTest(table=table):
                self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", sql)

    def test_workflow_prompt_references_exist(self) -> None:
        workflow_text = (BASE_DIR / "workflows" / "claim_review_workflow.yaml").read_text(
            encoding="utf-8"
        )
        prompt_refs = re.findall(r"prompt:\s+([^\s]+)", workflow_text)
        self.assertTrue(prompt_refs)
        for ref in prompt_refs:
            with self.subTest(prompt=ref):
                self.assertTrue((BASE_DIR / ref).exists())

    def test_required_prompt_files_exist(self) -> None:
        for relative in [
            "prompts/system_prompt.md",
            "prompts/claim_review_prompt.md",
            "prompts/output_format_prompt.md",
            "prompts/human_review_policy_prompt.md",
        ]:
            with self.subTest(prompt=relative):
                path = BASE_DIR / relative
                self.assertTrue(path.exists())
                text = path.read_text(encoding="utf-8")
                self.assertIn("Version: 1.0.0", text)

    def test_api_examples_reference_valid_claim_and_output_shapes(self) -> None:
        request = _read_json(BASE_DIR / "examples" / "api_review_request.example.json")
        response = _read_json(BASE_DIR / "examples" / "api_review_response.example.json")
        self.assertIn("claim", request)
        self.assertIn("policy_document_ref", request)
        self.assertIn("options", request)
        self.assertEqual(request["options"]["model_provider"], "general_llm")
        self.assertEqual(request["options"]["model_name"], "gemma-4-26B-4aB-it")
        self.assertEqual(response["claim_id"], request["claim"]["claim_id"])
        self.assertIn("agent_output", response)
        self.assertEqual(response["agent_output"]["claim_id"], response["claim_id"])

    def test_operational_docs_exist(self) -> None:
        for relative in [
            "docs/API_SPEC_DRAFT.md",
            "docs/STANDARDIZATION.md",
            "docs/OPERATIONS_TEMPLATE.md",
            "api/endpoints.md",
            "api/dto.md",
            "api/errors.md",
            "ui/customer_claim_screen.md",
            "ui/reviewer_assistant_screen.md",
        ]:
            with self.subTest(doc=relative):
                path = BASE_DIR / relative
                self.assertTrue(path.exists())
                self.assertGreater(len(path.read_text(encoding="utf-8")), 50)

    def test_evaluation_assets_exist(self) -> None:
        for relative in [
            "docs/EVALUATION.md",
            "eval/metrics.md",
            "eval/evaluation_plan.md",
            "eval/thresholds.yaml",
            "eval/failure_taxonomy.md",
            "tests/schema_validation_cases.md",
            "tests/workflow_validation_cases.md",
            "examples/evaluation_result.example.json",
        ]:
            with self.subTest(asset=relative):
                path = BASE_DIR / relative
                self.assertTrue(path.exists())
                self.assertGreater(len(path.read_text(encoding="utf-8")), 50)

    def test_thresholds_include_required_mvp_gates(self) -> None:
        thresholds = (BASE_DIR / "eval" / "thresholds.yaml").read_text(encoding="utf-8")
        required = {
            "schema_validity": ("==", "1.0"),
            "decision_accuracy": (">=", "0.90"),
            "coverage_accuracy": (">=", "0.95"),
            "payable_amount_exact_match": (">=", "0.95"),
            "missing_document_exact_match": (">=", "0.95"),
            "human_review_recall": (">=", "0.98"),
            "fraud_suspected_recall": (">=", "0.98"),
            "false_denial_rate": ("<=", "0.01"),
            "human_review_miss_rate": ("<=", "0.01"),
        }
        for metric, (operator, target) in required.items():
            with self.subTest(metric=metric):
                pattern = (
                    rf"{metric}:\s*\n"
                    rf"\s+operator:\s+\"{re.escape(operator)}\"\s*\n"
                    rf"\s+target:\s+{re.escape(target)}"
                )
                self.assertRegex(thresholds, pattern)

    def test_evaluation_result_example_shape(self) -> None:
        schema = _read_json(BASE_DIR / "schemas" / "evaluation_result.schema.json")
        example = _read_json(BASE_DIR / "examples" / "evaluation_result.example.json")
        for key in schema["required"]:
            self.assertIn(key, example)
        for metric in [
            "schema_validity",
            "decision_accuracy",
            "coverage_accuracy",
            "human_review_recall",
            "fraud_suspected_recall",
            "false_denial_rate",
            "human_review_miss_rate",
        ]:
            self.assertIn(metric, example["metrics"])


def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


if __name__ == "__main__":
    unittest.main()
