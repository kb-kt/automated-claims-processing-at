from __future__ import annotations

import argparse
import json
from pathlib import Path

from ai_agent_template.developer_kit.sdk.claim_agent_sdk.official_registry_importer import (
    RegistrySourceMetadata,
    load_insurer_medical_routing_rules,
    load_official_edi_rows,
    load_official_kcd_rows,
)

from ..core.settings import Settings
from .sqlite import SQLiteRepository


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import approved KCD/EDI/routing rule files into Starter Kit SQLite.")
    parser.add_argument("--kcd-file", required=True)
    parser.add_argument("--edi-file", required=True)
    parser.add_argument("--routing-rules-file", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--effective-from", required=True)
    parser.add_argument("--effective-to", default=None)
    parser.add_argument("--kcd-source-url", default="")
    parser.add_argument("--edi-source-url", default="")
    parser.add_argument("--license-note", default="")
    args = parser.parse_args(argv)

    settings = Settings.load()
    repository = SQLiteRepository(
        db_path=settings.sqlite_path,
        schema_path=settings.template_root / "db" / "schema.sql",
        migrations_dir=settings.template_root / "db" / "migrations",
    )
    kcd_path = Path(args.kcd_file)
    edi_path = Path(args.edi_file)
    routing_path = Path(args.routing_rules_file)
    result = repository.seed_medical_registry(
        medical_code_registry=load_official_kcd_rows(
            kcd_path,
            RegistrySourceMetadata(
                version=args.version,
                effective_from=args.effective_from,
                effective_to=args.effective_to,
                source_file=str(kcd_path),
                source_url=args.kcd_source_url,
                license_note=args.license_note,
            ),
        ),
        edi_code_registry=load_official_edi_rows(
            edi_path,
            RegistrySourceMetadata(
                version=args.version,
                effective_from=args.effective_from,
                effective_to=args.effective_to,
                source_file=str(edi_path),
                source_url=args.edi_source_url,
                license_note=args.license_note,
            ),
        ),
        diagnosis_treatment_rules=[],
        insurer_medical_routing_rules=load_insurer_medical_routing_rules(routing_path),
        source_files=[str(kcd_path), str(edi_path), str(routing_path)],
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
