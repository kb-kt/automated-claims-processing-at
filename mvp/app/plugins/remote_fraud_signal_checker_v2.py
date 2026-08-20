from __future__ import annotations

from ai_agent_template.developer_kit.plugins.remote_fraud_signal_checker_v2 import (
    RemoteFraudSignalCheckerV2Plugin as _TemplateRemoteFraudSignalCheckerV2Plugin,
)


class RemoteFraudSignalCheckerV2Plugin(_TemplateRemoteFraudSignalCheckerV2Plugin):
    owner = "mvp-fraud-check"
    source_system = "automated_claims_processing_mvp"
