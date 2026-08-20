from __future__ import annotations

import argparse
from typing import Sequence

from ai_agent_template.developer_kit.claims_gateway.seed_loader import FraudContextSeedLoader

from ..core.settings import Settings
from .sqlite import SQLiteRepository


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load synthetic fraud context data into MVP SQLite.")
    parser.add_argument("--generated-dir", default=None, help="Path to data_generator/generated.")
    parser.add_argument("--split", action="append", choices=["dev", "eval"], default=None)
    args = parser.parse_args(argv)

    settings = Settings.load()
    repository = SQLiteRepository(
        db_path=settings.sqlite_path,
        schema_path=settings.mvp_root / "app" / "db" / "schema.sql",
        migrations_dir=settings.mvp_root / "app" / "db" / "migrations",
    )
    loader = FraudContextSeedLoader(repository)
    for split in args.split or ["dev", "eval"]:
        result = loader.load_generated(args.generated_dir or settings.fraud_generated_dir, split=split)
        print(f"{split}: {result['row_count']} rows loaded ({result['run_id']})")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
