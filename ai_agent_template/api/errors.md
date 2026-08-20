# API Error Codes

Public and internal HTTP APIs use one canonical error envelope:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Claim payload does not match the input schema.",
    "details": ["claim.claimed_amount must be greater than or equal to 0"],
    "retryable": false,
    "request_id": "REQ-01H..."
  }
}
```

Canonical API codes include:

```text
VALIDATION_ERROR
SCHEMA_VERSION_UNSUPPORTED
NOT_FOUND
CONFLICT
AUTHENTICATION_REQUIRED
ACCESS_FORBIDDEN
INVALID_DOCUMENT_UPLOAD
DOCUMENT_TOO_LARGE
DEPENDENCY_ERROR
INTERNAL_ERROR
```

`request_id` is returned on failures and in the `X-Request-ID` response header.
Unexpected exception text, filesystem paths, document content, claim payloads, and
secrets must not be returned to callers. The server records the exception with the
same request ID. `retryable` describes whether retrying the same operation may
succeed; it does not authorize an automatic claim decision.

Workflow, model, and tool failures retain domain-specific codes such as
`POLICY_DOCUMENT_NOT_FOUND`, `MODEL_PROVIDER_ERROR`, `TOOL_TIMEOUT`, and
`REMOTE_HTTP_ERROR`. They are stored in the tool failure envelope and converted to
an API error only when the API operation itself cannot complete. Safety-critical
tool failures continue to route the claim to `human_review`.

Error response schema: `schemas/api_error.schema.json`
