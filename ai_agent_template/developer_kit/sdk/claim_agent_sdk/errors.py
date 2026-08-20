class AgentSdkError(Exception):
    """Base SDK error."""


class TemplateError(AgentSdkError):
    """Raised when a template artifact is missing or malformed."""


class SchemaValidationError(AgentSdkError):
    """Raised when a payload does not match a JSON schema."""

    def __init__(self, message: str, errors: list[str] | None = None):
        super().__init__(message)
        self.errors = errors or [message]


class PluginError(AgentSdkError):
    """Raised when a plugin cannot be loaded, validated, or executed."""


class EvaluationError(AgentSdkError):
    """Raised when evaluation inputs or outputs are invalid."""


class SafetyValidationError(AgentSdkError):
    """Raised when runtime data contains evaluation-only answer labels."""

    def __init__(self, message: str, findings: list[str] | None = None):
        super().__init__(message)
        self.findings = findings or [message]


class StartupValidationError(AgentSdkError):
    """Raised when a runtime configuration is unsafe or incomplete."""

    def __init__(self, message: str, errors: list[str] | None = None):
        super().__init__(message)
        self.errors = errors or [message]


class SecurityValidationError(AgentSdkError):
    """Raised when authentication or authorization configuration is invalid."""
