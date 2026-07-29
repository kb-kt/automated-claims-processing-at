import json
import unittest
from pathlib import Path

from ai_agent_template.developer_kit.plugin_interface import (
    PolicyKnowledgePluginConformance,
    ToolPluginConformance,
)
from ai_agent_template.developer_kit.plugins.synthetic import (
    SyntheticPolicyKnowledgePlugin,
    default_synthetic_plugins,
)
from ai_agent_template.developer_kit.sdk.claim_agent_sdk import TemplateBundle


WORKSPACE = Path(__file__).resolve().parents[4]
TEMPLATE_ROOT = WORKSPACE / "ai_agent_template"


class PluginConformanceTest(unittest.TestCase):
    def test_synthetic_plugins_conform_to_tool_contracts(self) -> None:
        template = TemplateBundle.load(TEMPLATE_ROOT)
        conformance = ToolPluginConformance(template)
        claim = _read_first_jsonl(WORKSPACE / "data_generator" / "generated" / "claims_eval.jsonl")
        output_example = _read_json(TEMPLATE_ROOT / "examples" / "reviewer_assistant_output.example.json")
        samples = {
            "policy_search": {"product_id": claim["product_id"], "query": "outpatient noncovered"},
            "coverage_resolver": {"claim": claim["claim"], "product_id": claim["product_id"]},
            "document_checker": {
                "coverage_code": "COV_OUTPATIENT_NONCOVERED",
                "submitted_documents": claim["documents"],
            },
            "exclusion_checker": {
                "claim": claim["claim"],
                "policy": claim["policy"],
                "signals": claim["signals"],
            },
            "payable_calculator": {
                "coverage_code": "COV_OUTPATIENT_NONCOVERED",
                "claimed_amount": claim["claim"]["claimed_amount"],
                "claim": claim["claim"],
            },
            "risk_checker": {
                "insured_profile": claim["insured_profile"],
                "claim": claim["claim"],
                "claim_history": claim["claim_history"],
                "signals": claim["signals"],
            },
            "fraud_signal_checker": {
                "insured_profile": claim["insured_profile"],
                "claim": claim["claim"],
                "claim_history": claim["claim_history"],
                "signals": claim["signals"],
            },
            "decision_validator": {"agent_output": output_example},
        }
        for plugin in default_synthetic_plugins():
            with self.subTest(plugin=plugin.name):
                conformance.assert_conformant(plugin, sample_payload=samples[plugin.name])

    def test_synthetic_policy_knowledge_plugin_conforms_to_retrieval_contract(self) -> None:
        template = TemplateBundle.load(TEMPLATE_ROOT)
        conformance = PolicyKnowledgePluginConformance(template)
        plugin = SyntheticPolicyKnowledgePlugin.from_template(template)
        conformance.assert_conformant(
            plugin,
            sample_request={
                "query": "outpatient noncovered deductible limit",
                "top_k": 2,
                "filters": {"product_id": "SYN-MED-001"},
            },
        )


def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _read_first_jsonl(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.loads(next(line for line in file if line.strip()))


if __name__ == "__main__":
    unittest.main()
