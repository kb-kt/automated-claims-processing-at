from __future__ import annotations

from typing import Any

from .base import SyntheticToolPlugin


class SyntheticFraudSignalCheckerPlugin(SyntheticToolPlugin):
    name = "fraud_signal_checker"
    contract_name = "fraud_signal_checker"

    def run(self, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        claim = payload.get("claim", {})
        history = payload.get("claim_history", {})
        signals = payload.get("signals", {})
        insured_profile = payload.get("insured_profile", {})
        reason_codes = []
        receipt_id = claim.get("receipt_id")
        receipt_hash = claim.get("receipt_hash")
        prior_receipt_ids = set(history.get("prior_receipt_ids", []))
        prior_receipt_hashes = set(history.get("prior_receipt_hashes", []))
        if (
            signals.get("suspected_duplicate_receipt")
            or (receipt_hash and receipt_hash in prior_receipt_hashes)
            or (receipt_id and receipt_id in prior_receipt_ids)
        ):
            reason_codes.append("DUPLICATE_RECEIPT_SUSPECTED")
        if signals.get("fraudulent_document"):
            reason_codes.append("FRAUD_SIGNAL")
        if int(history.get("same_insured_provider_claims_30d", 0)) >= 3 and insured_profile.get("insured_id"):
            reason_codes.append("SAME_INSURED_PROVIDER_REPEAT_SUSPECTED")
        if int(history.get("same_provider_claims_30d", 0)) >= 50 and claim.get("provider_id"):
            reason_codes.append("PROVIDER_PATTERN_ANOMALY_SUSPECTED")
        return self.ok(
            {
                "fraud_suspected": bool(reason_codes),
                "fraud_reason_codes": reason_codes,
            }
        )
