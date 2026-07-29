from .coverage_resolver_plugin import SyntheticCoverageResolverPlugin
from .decision_validator_plugin import SyntheticDecisionValidatorPlugin
from .document_checker_plugin import SyntheticDocumentCheckerPlugin
from .exclusion_checker_plugin import SyntheticExclusionCheckerPlugin
from .fraud_signal_checker_plugin import SyntheticFraudSignalCheckerPlugin
from .payable_calculator_plugin import SyntheticPayableCalculatorPlugin
from .policy_knowledge_plugin import SyntheticPolicyKnowledgePlugin
from .policy_search_plugin import SyntheticPolicySearchPlugin
from .risk_checker_plugin import SyntheticRiskCheckerPlugin

__all__ = [
    "SyntheticCoverageResolverPlugin",
    "SyntheticDecisionValidatorPlugin",
    "SyntheticDocumentCheckerPlugin",
    "SyntheticExclusionCheckerPlugin",
    "SyntheticFraudSignalCheckerPlugin",
    "SyntheticPayableCalculatorPlugin",
    "SyntheticPolicyKnowledgePlugin",
    "SyntheticPolicySearchPlugin",
    "SyntheticRiskCheckerPlugin",
    "default_synthetic_plugins",
]


def default_synthetic_plugins():
    return [
        SyntheticPolicySearchPlugin(),
        SyntheticCoverageResolverPlugin(),
        SyntheticDocumentCheckerPlugin(),
        SyntheticExclusionCheckerPlugin(),
        SyntheticPayableCalculatorPlugin(),
        SyntheticRiskCheckerPlugin(),
        SyntheticFraudSignalCheckerPlugin(),
        SyntheticDecisionValidatorPlugin(),
    ]
