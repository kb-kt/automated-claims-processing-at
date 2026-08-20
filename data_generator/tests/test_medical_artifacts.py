import tempfile
import unittest
from pathlib import Path

from data_generator.src.adjudication_rules import adjudicate
from data_generator.src.claim_generator import ClaimGenerator
from data_generator.src.config import load_config
from data_generator.src.fraud_artifacts import build_fraud_artifacts
from data_generator.src.medical_artifacts import (
    MEDICAL_REVIEW_SCENARIOS,
    POLICY_COVERAGE_SCENARIOS,
    build_medical_artifacts,
)
from data_generator.src.product_loader import load_product
from data_generator.src.validators import validate_dataset, validate_medical_artifacts


BASE_DIR = Path(__file__).resolve().parents[1]


class MedicalArtifactGenerationTest(unittest.TestCase):
    def _build_bundle(self, seed: int = 112233):
        config = load_config(
            BASE_DIR / "samples" / "generation_config.sample.json",
            dev_count=0,
            eval_count=0,
            seed=seed,
        )
        product = load_product(BASE_DIR / "samples" / "products.json")
        output_context = tempfile.TemporaryDirectory(dir=BASE_DIR / "generated")
        output_dir = Path(output_context.name)
        generator = ClaimGenerator(config, product)
        fraud_bundle = build_fraud_artifacts(
            config=config,
            product=product,
            dev_claims=generator.generate("dev", config.dev_count),
            eval_claims=generator.generate("eval", config.eval_count),
            output_dir=output_dir,
            write_documents=True,
        )
        medical_bundle = build_medical_artifacts(
            config=config,
            product=product,
            dev_claims=fraud_bundle.dev_claims,
            eval_claims=fraud_bundle.eval_claims,
            document_metadata_dev=fraud_bundle.document_metadata_dev,
            document_metadata_eval=fraud_bundle.document_metadata_eval,
        )
        self.addCleanup(output_context.cleanup)
        return config, product, fraud_bundle, medical_bundle

    def test_all_required_medical_and_policy_scenarios_are_generated(self) -> None:
        _, _, _, bundle = self._build_bundle()

        self.assertTrue(
            set(MEDICAL_REVIEW_SCENARIOS).issubset(
                {label["medical_scenario"] for label in bundle.medical_labels_dev}
            )
        )
        self.assertTrue(
            set(MEDICAL_REVIEW_SCENARIOS).issubset(
                {label["medical_scenario"] for label in bundle.medical_labels_eval}
            )
        )
        self.assertTrue(
            set(POLICY_COVERAGE_SCENARIOS).issubset(
                {label["policy_coverage_scenario"] for label in bundle.policy_coverage_labels_dev}
            )
        )
        self.assertTrue(
            set(POLICY_COVERAGE_SCENARIOS).issubset(
                {label["policy_coverage_scenario"] for label in bundle.policy_coverage_labels_eval}
            )
        )

    def test_registries_labels_and_document_metadata_validate(self) -> None:
        _, _, fraud_bundle, medical_bundle = self._build_bundle()

        validation = validate_medical_artifacts(
            dev_claims=fraud_bundle.dev_claims,
            eval_claims=fraud_bundle.eval_claims,
            medical_code_registry=medical_bundle.medical_code_registry,
            edi_code_registry=medical_bundle.edi_code_registry,
            diagnosis_treatment_rules=medical_bundle.diagnosis_treatment_rules,
            insurer_medical_routing_rules=medical_bundle.insurer_medical_routing_rules,
            medical_labels_dev=medical_bundle.medical_labels_dev,
            medical_labels_eval=medical_bundle.medical_labels_eval,
            code_mapping_labels_dev=medical_bundle.code_mapping_labels_dev,
            code_mapping_labels_eval=medical_bundle.code_mapping_labels_eval,
            policy_coverage_labels_dev=medical_bundle.policy_coverage_labels_dev,
            policy_coverage_labels_eval=medical_bundle.policy_coverage_labels_eval,
            medical_document_metadata_dev=medical_bundle.medical_document_metadata_dev,
            medical_document_metadata_eval=medical_bundle.medical_document_metadata_eval,
        )
        self.assertEqual(validation.errors, [])

        self.assertGreater(len(medical_bundle.medical_code_registry), 0)
        self.assertGreater(len(medical_bundle.edi_code_registry), 0)
        self.assertGreater(len(medical_bundle.diagnosis_treatment_rules), 0)
        self.assertGreater(len(medical_bundle.insurer_medical_routing_rules), 0)
        self.assertTrue(
            any(
                row["extraction_mode"] == "vlm_required"
                for row in medical_bundle.medical_document_metadata_dev
            )
        )

    def test_runtime_claims_do_not_leak_medical_or_policy_labels(self) -> None:
        _, product, fraud_bundle, medical_bundle = self._build_bundle()
        labels = [
            *[adjudicate(product, claim) for claim in fraud_bundle.dev_claims],
            *[adjudicate(product, claim) for claim in fraud_bundle.eval_claims],
        ]
        validation = validate_dataset(fraud_bundle.dev_claims + fraud_bundle.eval_claims, labels)
        self.assertEqual(validation.errors, [])

        forbidden_tokens = [
            "expected_kcd_code",
            "expected_edi_code",
            "medical_scenario",
            "policy_coverage_scenario",
            "diagnosis_treatment_relationship",
        ]
        runtime_text = str(fraud_bundle.dev_claims + fraud_bundle.eval_claims)
        for token in forbidden_tokens:
            self.assertNotIn(token, runtime_text)

        label_text = str(
            medical_bundle.medical_labels_dev
            + medical_bundle.code_mapping_labels_dev
            + medical_bundle.policy_coverage_labels_dev
        )
        self.assertIn("expected_kcd_code", label_text)
        self.assertIn("policy_coverage_scenario", label_text)

    def test_runtime_claims_include_medical_evidence_without_label_keys(self) -> None:
        _, _, fraud_bundle, _ = self._build_bundle()

        for claim in fraud_bundle.dev_claims + fraud_bundle.eval_claims:
            with self.subTest(claim_id=claim["claim_id"]):
                evidence = claim.get("medical_evidence")
                self.assertIsInstance(evidence, dict)
                self.assertEqual(evidence["schema_version"], "1.0.0")
                self.assertTrue(evidence["code_mapping_candidates"]["kcd"])
                self.assertTrue(evidence["code_mapping_candidates"]["edi"])
                self.assertTrue(evidence["insurer_medical_routing_rules"])
                self.assertEqual(
                    evidence["insurer_medical_routing_rules"][0]["approval_status"],
                    "synthetic_insurer_approved",
                )
                serialized = str(evidence)
                self.assertNotIn("expected_kcd_code", serialized)
                self.assertNotIn("expected_edi_code", serialized)
                self.assertNotIn("medical_scenario", serialized)

    def test_same_seed_recreates_same_medical_artifacts(self) -> None:
        _, _, _, first = self._build_bundle(seed=445566)
        _, _, _, second = self._build_bundle(seed=445566)

        self.assertEqual(first.medical_code_registry, second.medical_code_registry)
        self.assertEqual(first.edi_code_registry, second.edi_code_registry)
        self.assertEqual(first.diagnosis_treatment_rules, second.diagnosis_treatment_rules)
        self.assertEqual(first.insurer_medical_routing_rules, second.insurer_medical_routing_rules)
        self.assertEqual(first.medical_labels_dev, second.medical_labels_dev)
        self.assertEqual(first.code_mapping_labels_eval, second.code_mapping_labels_eval)
        self.assertEqual(first.medical_document_metadata_dev, second.medical_document_metadata_dev)


if __name__ == "__main__":
    unittest.main()
