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
    DEFAULT_PRODUCT_CATALOG_PATH,
    DEFAULT_PRODUCT_PATH,
    GENERATED_DIR,
)
from .fraud_artifacts import build_fraud_artifacts
from .medical_artifacts import build_medical_artifacts
from .product_catalog import (
    build_policies,
    load_catalog_products,
    recover_products_from_csv,
    validate_product_policy_relationships,
    validate_products,
    write_policies,
    write_product_catalog,
)
from .product_loader import load_product
from .report import build_report
from .validators import (
    merge_validation_results,
    validate_dataset,
    validate_fraud_artifacts,
    validate_generated_dir,
    validate_medical_artifacts,
)
from .writer import ensure_writable_output, read_text, write_json, write_jsonl, write_text


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0].startswith("-"):
        argv = ["generate", *argv]

    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "validate":
        return _handle_validate(args)
    if args.command == "import-products":
        return _handle_import_products(args)
    return _handle_generate(args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate synthetic insurance claims data.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="generate synthetic claims and labels")
    generate.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    generate.add_argument("--product", default=str(DEFAULT_PRODUCT_PATH))
    generate.add_argument("--product-catalog", default=str(DEFAULT_PRODUCT_CATALOG_PATH))
    generate.add_argument("--policy-doc", default=str(DEFAULT_POLICY_DOC_PATH))
    generate.add_argument("--evaluation-cases", default=str(DEFAULT_EVALUATION_CASES_PATH))
    generate.add_argument("--output", default=str(GENERATED_DIR))
    generate.add_argument("--dev-count", type=int)
    generate.add_argument("--eval-count", type=int)
    generate.add_argument("--seed", type=int)
    generate.add_argument("--overwrite", action="store_true")
    generate.add_argument("--report-only", action="store_true")
    generate.add_argument("--policies-per-product", type=int, default=3)

    validate = subparsers.add_parser("validate", help="validate generated files")
    validate.add_argument("--input", default=str(GENERATED_DIR))

    import_products = subparsers.add_parser(
        "import-products",
        help="recover a legacy products CSV and write a normalized product catalog",
    )
    import_products.add_argument("--source", required=True)
    import_products.add_argument("--catalog-output", default=str(DEFAULT_PRODUCT_CATALOG_PATH.parent))
    import_products.add_argument("--generated-output", default=str(GENERATED_DIR))
    import_products.add_argument("--include-product", default=str(DEFAULT_PRODUCT_PATH))
    import_products.add_argument("--policies-per-product", type=int, default=3)
    return parser


def _handle_generate(args: argparse.Namespace) -> int:
    config_path = resolve_path(args.config, DEFAULT_CONFIG_PATH)
    product_path = resolve_path(args.product, DEFAULT_PRODUCT_PATH)
    product_catalog_path = resolve_path(args.product_catalog, DEFAULT_PRODUCT_CATALOG_PATH)
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
    catalog_products = load_catalog_products(product_catalog_path)
    catalog_by_id = {str(item["product_id"]): item for item in catalog_products}
    catalog_by_id[product.product_id] = product.raw
    catalog_products = list(catalog_by_id.values())

    generator = ClaimGenerator(config, product)
    dev_claims = generator.generate("dev", config.dev_count)
    eval_claims = generator.generate("eval", config.eval_count)
    if not args.report_only:
        _ensure_safe_overwrite_target(output_dir, args.overwrite)
        ensure_writable_output(output_dir, overwrite=args.overwrite)
    fraud_bundle = build_fraud_artifacts(
        config=config,
        product=product,
        dev_claims=dev_claims,
        eval_claims=eval_claims,
        output_dir=output_dir,
        write_documents=not args.report_only,
    )
    dev_claims = fraud_bundle.dev_claims
    eval_claims = fraud_bundle.eval_claims
    medical_bundle = build_medical_artifacts(
        config=config,
        product=product,
        dev_claims=dev_claims,
        eval_claims=eval_claims,
        document_metadata_dev=fraud_bundle.document_metadata_dev,
        document_metadata_eval=fraud_bundle.document_metadata_eval,
    )
    dev_labels = [adjudicate(product, claim) for claim in dev_claims]
    eval_labels = [adjudicate(product, claim) for claim in eval_claims]
    policies = build_policies(
        catalog_products,
        dev_claims + eval_claims,
        policies_per_product=args.policies_per_product,
    )
    validation = merge_validation_results(
        validate_dataset(dev_claims + eval_claims, dev_labels + eval_labels),
        validate_products(catalog_products),
        validate_product_policy_relationships(
            catalog_products,
            policies,
            dev_claims + eval_claims,
        ),
        validate_fraud_artifacts(
            output_dir,
            dev_claims=dev_claims,
            eval_claims=eval_claims,
            historical_claims=fraud_bundle.historical_claims,
            fraud_labels_dev=fraud_bundle.fraud_labels_dev,
            fraud_labels_eval=fraud_bundle.fraud_labels_eval,
            document_metadata_dev=fraud_bundle.document_metadata_dev,
            document_metadata_eval=fraud_bundle.document_metadata_eval,
            validate_files=not args.report_only,
        ),
        validate_medical_artifacts(
            dev_claims=dev_claims,
            eval_claims=eval_claims,
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
        ),
    )
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
    report["fraud_generation"] = fraud_bundle.report
    report["medical_generation"] = medical_bundle.report

    if args.report_only:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if validation.ok else 1

    write_json(output_dir / "products.json", product.raw)
    write_product_catalog(catalog_products, output_dir / "products")
    write_policies(output_dir / "policies.jsonl", policies)
    write_text(output_dir / "policy_documents.md", read_text(policy_doc_path))
    write_json(output_dir / "insureds.json", fraud_bundle.insureds)
    write_json(output_dir / "providers.json", fraud_bundle.providers)
    write_jsonl(output_dir / "claims_dev.jsonl", dev_claims)
    write_jsonl(output_dir / "labels_dev.jsonl", dev_labels)
    write_jsonl(output_dir / "claims_eval.jsonl", eval_claims)
    write_jsonl(output_dir / "labels_eval.jsonl", eval_labels)
    write_jsonl(output_dir / "historical_claims.jsonl", fraud_bundle.historical_claims)
    write_jsonl(output_dir / "document_metadata_dev.jsonl", fraud_bundle.document_metadata_dev)
    write_jsonl(output_dir / "document_metadata_eval.jsonl", fraud_bundle.document_metadata_eval)
    write_jsonl(output_dir / "claim_document_links_dev.jsonl", fraud_bundle.claim_document_links_dev)
    write_jsonl(output_dir / "claim_document_links_eval.jsonl", fraud_bundle.claim_document_links_eval)
    write_jsonl(output_dir / "fraud_labels_dev.jsonl", fraud_bundle.fraud_labels_dev)
    write_jsonl(output_dir / "fraud_labels_eval.jsonl", fraud_bundle.fraud_labels_eval)
    write_jsonl(output_dir / "fraud_context_seed_dev.jsonl", fraud_bundle.fraud_context_seed_dev)
    write_jsonl(output_dir / "fraud_context_seed_eval.jsonl", fraud_bundle.fraud_context_seed_eval)
    write_json(output_dir / "medical_code_registry.json", medical_bundle.medical_code_registry)
    write_json(output_dir / "edi_code_registry.json", medical_bundle.edi_code_registry)
    write_json(output_dir / "diagnosis_treatment_rules.json", medical_bundle.diagnosis_treatment_rules)
    write_json(output_dir / "insurer_medical_routing_rules.json", medical_bundle.insurer_medical_routing_rules)
    write_jsonl(output_dir / "medical_labels_dev.jsonl", medical_bundle.medical_labels_dev)
    write_jsonl(output_dir / "medical_labels_eval.jsonl", medical_bundle.medical_labels_eval)
    write_jsonl(output_dir / "code_mapping_labels_dev.jsonl", medical_bundle.code_mapping_labels_dev)
    write_jsonl(output_dir / "code_mapping_labels_eval.jsonl", medical_bundle.code_mapping_labels_eval)
    write_jsonl(output_dir / "policy_coverage_labels_dev.jsonl", medical_bundle.policy_coverage_labels_dev)
    write_jsonl(output_dir / "policy_coverage_labels_eval.jsonl", medical_bundle.policy_coverage_labels_eval)
    write_jsonl(output_dir / "medical_document_metadata_dev.jsonl", medical_bundle.medical_document_metadata_dev)
    write_jsonl(output_dir / "medical_document_metadata_eval.jsonl", medical_bundle.medical_document_metadata_eval)
    write_jsonl(
        output_dir / "document_extraction_labels_dev.jsonl",
        _document_extraction_labels(medical_bundle.medical_document_metadata_dev),
    )
    write_jsonl(
        output_dir / "document_extraction_labels_eval.jsonl",
        _document_extraction_labels(medical_bundle.medical_document_metadata_eval),
    )
    write_jsonl(output_dir / "medical_context_seed_dev.jsonl", medical_bundle.medical_context_seed_dev)
    write_jsonl(output_dir / "medical_context_seed_eval.jsonl", medical_bundle.medical_context_seed_eval)
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


def _handle_import_products(args: argparse.Namespace) -> int:
    source = ensure_under_base(resolve_path(args.source, BASE_DIR), "product CSV")
    catalog_output = ensure_under_base(
        resolve_path(args.catalog_output, DEFAULT_PRODUCT_CATALOG_PATH.parent),
        "catalog output",
    )
    generated_output = ensure_under_base(
        resolve_path(args.generated_output, GENERATED_DIR),
        "generated output",
    )
    include_product_path = ensure_under_base(
        resolve_path(args.include_product, DEFAULT_PRODUCT_PATH),
        "included product",
    )
    products = recover_products_from_csv(source)
    included = load_product(include_product_path).raw
    by_id = {str(item["product_id"]): item for item in products}
    by_id[str(included["product_id"])] = included
    products = list(by_id.values())
    write_product_catalog(products, catalog_output)
    write_product_catalog(products, generated_output / "products")
    claims = _read_jsonl_if_exists(generated_output / "claims_dev.jsonl")
    claims.extend(_read_jsonl_if_exists(generated_output / "claims_eval.jsonl"))
    policies = build_policies(
        products,
        claims,
        policies_per_product=args.policies_per_product,
    )
    relationship_validation = validate_product_policy_relationships(products, policies, claims)
    if not relationship_validation.ok:
        for error in relationship_validation.errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    write_policies(generated_output / "policies.jsonl", policies)
    print(
        f"Imported {len(products)} products and {len(policies)} policies; "
        f"validated {len(claims)} claim relationships"
    )
    return 0


def _read_jsonl_if_exists(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def _ensure_safe_overwrite_target(output_dir: Path, overwrite: bool) -> None:
    if not overwrite:
        return
    generated_root = GENERATED_DIR.resolve()
    resolved = output_dir.resolve()
    try:
        resolved.relative_to(generated_root)
    except ValueError as exc:
        raise ValueError(
            f"--overwrite may only clean paths under {generated_root}: {resolved}"
        ) from exc


def _document_extraction_labels(rows: list[dict]) -> list[dict]:
    return [
        {
            "claim_id": row.get("claim_id"),
            "document_id": row.get("document_id"),
            "document_type": row.get("document_type"),
            "expected_fields": row.get("extracted_fields", {}),
            "expected_field_statuses": row.get("field_statuses", {}),
            "source_file_path": row.get("source_file_path"),
            "synthetic": True,
        }
        for row in rows
    ]


if __name__ == "__main__":
    raise SystemExit(main())
