from __future__ import annotations

import argparse
import json
from pathlib import Path

from .document_extraction import check_document_vlm_conformance
from .model_provider import load_model_provider_config, load_model_provider_from_config


def main() -> int:
    parser = argparse.ArgumentParser(description="Run document_vlm provider conformance check.")
    parser.add_argument("--config", required=True, help="Model config YAML path.")
    parser.add_argument("--provider", default="document_vlm", help="Provider name in model config.")
    parser.add_argument("--sample-document", help="Optional synthetic PDF path to attach to the probe.")
    args = parser.parse_args()

    provider_config = load_model_provider_config(args.config, args.provider)
    missing = [
        key
        for key in ("base_url", "api_key", "model_id")
        if not str(provider_config.get(key) or "").strip()
    ]
    if missing:
        print(
            json.dumps(
                {
                    "conformant": False,
                    "reason": "not_configured",
                    "missing": missing,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    provider = load_model_provider_from_config(args.config, provider_name=args.provider)
    sample = Path(args.sample_document).resolve() if args.sample_document else None
    result = check_document_vlm_conformance(provider, sample_document=sample)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("conformant") else 2


if __name__ == "__main__":
    raise SystemExit(main())
