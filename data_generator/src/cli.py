from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from .adjudication_rules import adjudicate
from .claim_generator import ClaimGenerator
from .config import ensure_under_base, load_config, resolve_path
from .constants import (
    BASE_DIR,
    DEFAULT_CONFIG_PATH,
    DEFAULT_EVALUATION_CASES_PATH,
    DEFAULT_POLICY_DOC_PATH,
    DEFAULT_PRODUCT_PATH,
    GENERATED_DIR,
)
from .product_loader import load_product
from .report import build_report
from .validators import validate_dataset, validate_generated_dir
from .writer import ensure_writable_output, read_text, write_json, write_jsonl, write_text


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0].startswith("-"):
        argv = ["generate", *argv]

    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "validate":
        return _handle_validate(args)
    return _handle_generate(args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate synthetic insurance claims data.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="generate synthetic claims and labels")
    generate.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    generate.add_argument("--product", default=str(DEFAULT_PRODUCT_PATH))
    generate.add_argument("--policy-doc", default=str(DEFAULT_POLICY_DOC_PATH))
    generate.add_argument("--evaluation-cases", default=str(DEFAULT_EVALUATION_CASES_PATH))
    generate.add_argument("--output", default=str(GENERATED_DIR))
    generate.add_argument("--dev-count", type=int)
    generate.add_argument("--eval-count", type=int)
    generate.add_argument("--seed", type=int)
    generate.add_argument("--overwrite", action="store_true")
    generate.add_argument("--report-only", action="store_true")

    validate = subparsers.add_parser("validate", help="validate generated files")
    validate.add_argument("--input", default=str(GENERATED_DIR))
    return parser


def _handle_generate(args: argparse.Namespace) -> int:
    config_path = resolve_path(args.config, DEFAULT_CONFIG_PATH)
    product_path = resolve_path(args.product, DEFAULT_PRODUCT_PATH)
    policy_doc_path = resolve_path(args.policy_doc, DEFAULT_POLICY_DOC_PATH)
    evaluation_cases_path = resolve_path(args.evaluation_cases, DEFAULT_EVALUATION_CASES_PATH)
    output_dir = ensure_under_base(resolve_path(args.output, GENERATED_DIR), "output")

    config = load_config(
        config_path,
        dev_count=args.dev_count,
        eval_count=args.eval_count,
        seed=args.seed,
    )
    product = load_product(product_path)
    if product.product_id != config.product_id:
        raise ValueError(
            f"Config product_id {config.product_id} does not match product {product.product_id}"
        )

    generator = ClaimGenerator(config, product)
    dev_claims = generator.generate("dev", config.dev_count)
    eval_claims = generator.generate("eval", config.eval_count)
    dev_labels = [adjudicate(product, claim) for claim in dev_claims]
    eval_labels = [adjudicate(product, claim) for claim in eval_claims]
    validation = validate_dataset(dev_claims + eval_claims, dev_labels + eval_labels)
    report = build_report(
        config=config,
        product=product,
        output_dir=output_dir,
        dev_claims=dev_claims,
        eval_claims=eval_claims,
        dev_labels=dev_labels,
        eval_labels=eval_labels,
        validation=validation,
        config_path=config_path,
    )

    if args.report_only:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if validation.ok else 1

    ensure_writable_output(output_dir, overwrite=args.overwrite)
    write_json(output_dir / "products.json", product.raw)
    write_text(output_dir / "policy_documents.md", read_text(policy_doc_path))
    write_jsonl(output_dir / "claims_dev.jsonl", dev_claims)
    write_jsonl(output_dir / "labels_dev.jsonl", dev_labels)
    write_jsonl(output_dir / "claims_eval.jsonl", eval_claims)
    write_jsonl(output_dir / "labels_eval.jsonl", eval_labels)
    if evaluation_cases_path.exists():
        shutil.copyfile(evaluation_cases_path, output_dir / "evaluation_cases.jsonl")
    else:
        write_jsonl(output_dir / "evaluation_cases.jsonl", [])
    write_json(output_dir / "generation_report.json", report)

    if not validation.ok:
        for error in validation.errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Generated {len(dev_claims)} dev and {len(eval_claims)} eval claims at {output_dir}")
    return 0


def _handle_validate(args: argparse.Namespace) -> int:
    input_dir = ensure_under_base(resolve_path(args.input, GENERATED_DIR), "input")
    validation = validate_generated_dir(input_dir)
    if validation.ok:
        print("validation-ok")
        return 0
    for error in validation.errors:
        print(f"ERROR: {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
