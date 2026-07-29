import unittest
from pathlib import Path

from data_generator.src.config import load_config
from data_generator.src.claim_generator import ClaimGenerator
from data_generator.src.product_loader import load_product


BASE_DIR = Path(__file__).resolve().parents[1]


class ReproducibilityTest(unittest.TestCase):
    def test_same_seed_generates_same_claims(self) -> None:
        config = load_config(
            BASE_DIR / "samples" / "generation_config.sample.json",
            dev_count=30,
            eval_count=0,
            seed=12345,
        )
        product = load_product(BASE_DIR / "samples" / "products.json")

        first = ClaimGenerator(config, product).generate("dev", 30)
        second = ClaimGenerator(config, product).generate("dev", 30)

        self.assertEqual(first, second)

    def test_different_seed_changes_claims(self) -> None:
        config_a = load_config(
            BASE_DIR / "samples" / "generation_config.sample.json",
            dev_count=30,
            eval_count=0,
            seed=111,
        )
        config_b = load_config(
            BASE_DIR / "samples" / "generation_config.sample.json",
            dev_count=30,
            eval_count=0,
            seed=222,
        )
        product = load_product(BASE_DIR / "samples" / "products.json")

        first = ClaimGenerator(config_a, product).generate("dev", 30)
        second = ClaimGenerator(config_b, product).generate("dev", 30)

        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
