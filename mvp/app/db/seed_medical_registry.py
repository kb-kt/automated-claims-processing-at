from __future__ import annotations

import argparse
import json
from pathlib import Path

from .sqlite import SQLiteRepository
from ..core.settings import Settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load synthetic KCD/EDI registry data into MVP SQLite.")
    parser.add_argument("--generated-dir", default=None, help="Path to data_generator/generated")
    args = parser.parse_args(argv)

    settings = Settings.load()
    generated_dir = Path(args.generated_dir) if args.generated_dir else settings.mvp_root.parent / "data_generator" / "generated"
    files = {
        "medical_code_registry": generated_dir / "medical_code_registry.json",
        "edi_code_registry": generated_dir / "edi_code_registry.json",
        "diagnosis_treatment_rules": generated_dir / "diagnosis_treatment_rules.json",
        "insurer_medical_routing_rules": generated_dir / "insurer_medical_routing_rules.json",
    }
    required_files = {
        key: path for key, path in files.items() if key != "insurer_medical_routing_rules"
    }
    missing = [str(path) for path in required_files.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing medical registry source files: {missing}")

    repository = SQLiteRepository(
        db_path=settings.sqlite_path,
        schema_path=settings.mvp_root / "app" / "db" / "schema.sql",
        migrations_dir=settings.mvp_root / "app" / "db" / "migrations",
    )
    result = repository.seed_medical_registry(
        medical_code_registry=_read_json(files["medical_code_registry"]),
        edi_code_registry=_read_json(files["edi_code_registry"]),
        diagnosis_treatment_rules=_read_json(files["diagnosis_treatment_rules"]),
        insurer_medical_routing_rules=_read_json_optional(files["insurer_medical_routing_rules"]),
        source_files=[str(path) for path in files.values() if path.exists()],
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0


def _read_json(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _read_json_optional(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return _read_json(path)


if __name__ == "__main__":
    raise SystemExit(main())
