import tempfile
import unittest
from pathlib import Path

from data_generator.src.adjudication_rules import adjudicate
from data_generator.src.claim_generator import ClaimGenerator
from data_generator.src.config import load_config
from data_generator.src.fraud_artifacts import (
    FRAUD_SCENARIOS,
    SUPPORTED_DOCUMENT_TYPES,
    build_fraud_artifacts,
    recalculate_claim_history,
)
from data_generator.src.pdf_documents import pdf_readability
from data_generator.src.product_loader import load_product
from data_generator.src.validators import validate_dataset, validate_fraud_artifacts


BASE_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BASE_DIR.parent


class FraudArtifactGenerationTest(unittest.TestCase):
    def _build_bundle(self, seed: int = 2468):
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
        bundle = build_fraud_artifacts(
            config=config,
            product=product,
            dev_claims=generator.generate("dev", config.dev_count),
            eval_claims=generator.generate("eval", config.eval_count),
            output_dir=output_dir,
            write_documents=True,
        )
        self.addCleanup(output_context.cleanup)
        return config, product, output_dir, bundle

    def test_all_required_fraud_scenarios_are_generated(self) -> None:
        _, _, _, bundle = self._build_bundle()

        self.assertEqual(
            {label["fraud_scenario"] for label in bundle.fraud_labels_dev},
            set(FRAUD_SCENARIOS),
        )
        self.assertEqual(
            {label["fraud_scenario"] for label in bundle.fraud_labels_eval},
            set(FRAUD_SCENARIOS),
        )

    def test_claim_history_is_recalculated_from_individual_history(self) -> None:
        _, _, _, bundle = self._build_bundle()
        history_by_claim_id: dict[str, list[dict]] = {}
        for historical in bundle.historical_claims:
            history_by_claim_id.setdefault(historical["history_for_claim_id"], []).append(historical)

        for claim in bundle.dev_claims + bundle.eval_claims:
            recalculated = recalculate_claim_history(
                claim,
                history_by_claim_id.get(claim["claim_id"], []),
            )
            self.assertEqual(claim["claim_history"], recalculated)

        claim_by_scenario = _claims_by_fraud_scenario(bundle.dev_claims, bundle.fraud_labels_dev)
        self.assertEqual(
            claim_by_scenario["normal_clean"]["claim_history"]["same_provider_claims_30d"],
            0,
        )
        self.assertEqual(
            claim_by_scenario["same_insured_provider_repeat_2_boundary"]["claim_history"][
                "same_insured_provider_claims_30d"
            ],
            2,
        )
        self.assertEqual(
            claim_by_scenario["same_insured_provider_repeat_3"]["claim_history"][
                "same_insured_provider_claims_30d"
            ],
            3,
        )
        self.assertEqual(
            claim_by_scenario["provider_volume_49_boundary"]["claim_history"]["same_provider_claims_30d"],
            49,
        )
        self.assertEqual(
            claim_by_scenario["provider_volume_50"]["claim_history"]["same_provider_claims_30d"],
            50,
        )

    def test_pdf_metadata_hashes_failures_and_document_types_are_valid(self) -> None:
        _, _, output_dir, bundle = self._build_bundle()

        validation = validate_fraud_artifacts(
            output_dir,
            dev_claims=bundle.dev_claims,
            eval_claims=bundle.eval_claims,
            historical_claims=bundle.historical_claims,
            fraud_labels_dev=bundle.fraud_labels_dev,
            fraud_labels_eval=bundle.fraud_labels_eval,
            document_metadata_dev=bundle.document_metadata_dev,
            document_metadata_eval=bundle.document_metadata_eval,
            validate_files=True,
        )
        self.assertEqual(validation.errors, [])

        document_types = {row["document_type"] for row in bundle.document_metadata_dev}
        self.assertTrue(SUPPORTED_DOCUMENT_TYPES.issubset(document_types))

        missing = _metadata_by_status(bundle.document_metadata_dev, "missing")[0]
        self.assertFalse((output_dir / missing["file_path"]).exists())

        corrupted = _metadata_by_status(bundle.document_metadata_dev, "corrupted")[0]
        self.assertFalse(pdf_readability(output_dir / corrupted["file_path"]))

        protected = _metadata_by_status(bundle.document_metadata_dev, "password_protected")[0]
        self.assertFalse(pdf_readability(output_dir / protected["file_path"]))

    def test_forgery_labels_match_structured_document_mismatches(self) -> None:
        _, _, _, bundle = self._build_bundle()
        labels = {label["fraud_scenario"]: label for label in bundle.fraud_labels_dev}
        claims = _claims_by_fraud_scenario(bundle.dev_claims, bundle.fraud_labels_dev)

        self.assertIn("DOCUMENT_AMOUNT_MISMATCH", labels["forged_amount"]["fraud_reason_codes"])
        self.assertIn("DOCUMENT_DATE_MISMATCH", labels["forged_date"]["fraud_reason_codes"])
        self.assertIn("DOCUMENT_PROVIDER_MISMATCH", labels["forged_provider"]["fraud_reason_codes"])

        by_claim_and_type = {
            (row["claim_id"], row["document_type"]): row
            for row in bundle.document_metadata_dev
        }
        forged_amount_doc = by_claim_and_type[(claims["forged_amount"]["claim_id"], "medical_receipt")]
        self.assertNotEqual(
            forged_amount_doc["structured_fields"]["claimed_amount"],
            claims["forged_amount"]["claim"]["claimed_amount"],
        )

        forged_date_doc = by_claim_and_type[(claims["forged_date"]["claim_id"], "medical_receipt")]
        self.assertNotEqual(
            forged_date_doc["structured_fields"]["treatment_start_date"],
            claims["forged_date"]["claim"]["treatment_start_date"],
        )

        forged_provider_doc = by_claim_and_type[(claims["forged_provider"]["claim_id"], "medical_receipt")]
        self.assertNotEqual(
            forged_provider_doc["structured_fields"]["provider_id"],
            claims["forged_provider"]["claim"]["provider_id"],
        )

    def test_altered_duplicate_has_historical_fingerprint_index(self) -> None:
        _, _, _, bundle = self._build_bundle()
        claims = _claims_by_fraud_scenario(bundle.dev_claims, bundle.fraud_labels_dev)
        altered_claim = claims["altered_duplicate_receipt"]
        current_receipt = next(
            row
            for row in bundle.document_metadata_dev
            if row["claim_id"] == altered_claim["claim_id"]
            and row["document_type"] == "medical_receipt"
        )
        historical = next(
            row
            for row in bundle.historical_claims
            if row.get("history_for_claim_id") == altered_claim["claim_id"]
        )
        historical_receipt = historical["document_fingerprints"][0]

        self.assertNotEqual(current_receipt["content_hash"], historical_receipt["content_hash"])
        self.assertEqual(current_receipt["text_fingerprint"], historical_receipt["text_fingerprint"])
        self.assertEqual(current_receipt["perceptual_hash"], historical_receipt["perceptual_hash"])
        self.assertNotIn("fraud_reason_codes", historical_receipt)

    def test_label_isolation_and_template_input_compatibility(self) -> None:
        _, product, output_dir, bundle = self._build_bundle()
        labels = [adjudicate(product, claim) for claim in bundle.dev_claims + bundle.eval_claims]

        dataset_validation = validate_dataset(bundle.dev_claims + bundle.eval_claims, labels)
        self.assertEqual(dataset_validation.errors, [])
        self.assertTrue(
            all(claim["scenario_type"] == "synthetic_documented_claim" for claim in bundle.dev_claims)
        )

        schema = _read_json(ROOT_DIR / "ai_agent_template" / "schemas" / "claim_review_input.schema.json")
        allowed_top_level_keys = set(schema["properties"])
        for claim in bundle.dev_claims + bundle.eval_claims:
            self.assertTrue(set(schema["required"]).issubset(claim))
            self.assertTrue(set(claim).issubset(allowed_top_level_keys))
            serialized = str(claim)
            self.assertNotIn("fraud_reason_codes", serialized)
            self.assertNotIn("expected_decision", serialized)

        fraud_validation = validate_fraud_artifacts(
            output_dir,
            dev_claims=bundle.dev_claims,
            eval_claims=bundle.eval_claims,
            historical_claims=bundle.historical_claims,
            fraud_labels_dev=bundle.fraud_labels_dev,
            fraud_labels_eval=bundle.fraud_labels_eval,
            document_metadata_dev=bundle.document_metadata_dev,
            document_metadata_eval=bundle.document_metadata_eval,
            validate_files=True,
        )
        self.assertEqual(fraud_validation.errors, [])

    def test_same_seed_recreates_same_runtime_and_metadata(self) -> None:
        _, _, _, first = self._build_bundle(seed=13579)
        _, _, _, second = self._build_bundle(seed=13579)

        self.assertEqual(first.dev_claims, second.dev_claims)
        self.assertEqual(first.eval_claims, second.eval_claims)
        self.assertEqual(first.historical_claims, second.historical_claims)
        self.assertEqual(first.fraud_labels_dev, second.fraud_labels_dev)
        self.assertEqual(first.fraud_labels_eval, second.fraud_labels_eval)
        self.assertEqual(first.document_metadata_dev, second.document_metadata_dev)
        self.assertEqual(first.document_metadata_eval, second.document_metadata_eval)


def _claims_by_fraud_scenario(claims: list[dict], labels: list[dict]) -> dict[str, dict]:
    claim_by_id = {claim["claim_id"]: claim for claim in claims}
    return {label["fraud_scenario"]: claim_by_id[label["claim_id"]] for label in labels}


def _metadata_by_status(rows: list[dict], status: str) -> list[dict]:
    return [row for row in rows if row.get("document_status") == status]


def _read_json(path: Path) -> dict:
    import json

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


if __name__ == "__main__":
    unittest.main()
