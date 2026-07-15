# ADR-008: Error envelope and request-correlation contract

- **Status:** Accepted
- **Date:** 2026-07-14
- **Deciders:** Product owner, principal architect

## Context

Blueprint §10.4 requires a consistent error envelope with a machine-readable
code, human message, field errors, and correlation ID, and §16.1 requires the
correlation ID in structured logs. This contract must exist before the first
product endpoint and before the generated TypeScript client (Milestone 1C),
because every consumer will bind to it.

## Decision

Every error response — HTTP errors, request-validation failures, and
unhandled exceptions — uses one envelope (`app/core/errors.py`):

```json
{
  "error": {
    "code": "validation_error",
    "message": "Request validation failed.",
    "field_errors": [
      { "field": "body.name", "code": "missing", "message": "Field required" }
    ],
    "correlation_id": "...",
    "details": null
  }
}
```

- `code` comes from an **append-only snake_case registry** seeded with
  `validation_error`, `not_found`, `method_not_allowed`, `http_error`,
  `internal_error`, and `dependency_unavailable`. Codes are never renamed or
  reused.
- `field_errors` is an empty list when not applicable; `field` is the
  dot-joined request location (for example `body.name`, `path.item_id`).
- `details` is an optional structured-context object (null when absent) for
  codes that carry machine-readable information. First use: `/health/ready`
  returns 503 with `dependency_unavailable` and
  `details.checks` (for example `{"checks": {"database": "down"}}`) — the
  not-ready state is an error and uses this envelope, not a bespoke body.
- Unhandled exceptions return an opaque message and are logged with the
  stack trace; internals never reach the response.

Correlation IDs (`app/core/correlation.py`): a syntactically safe inbound
`X-Request-ID` (max 64 chars, `[A-Za-z0-9._-]`) is honored so a future
reverse proxy can correlate its logs; anything else is replaced with a
generated UUID. The ID is bound to logging contextvars, echoed on every
response header, and included in every error envelope.

## Alternatives considered

- **FastAPI default error bodies (`{"detail": ...}`):** rejected — shape
  varies by error source, has no code registry or correlation ID, and would
  leak into the generated client as an untyped contract.
- **RFC 9457 problem+json:** viable standard, but its extension-member model
  adds ceremony without adding information over the blueprint's stated
  contract; revisit if external API consumers ever need it.
- **Always generating the request ID (ignoring inbound):** rejected — breaks
  edge/proxy correlation; strict input validation removes the injection risk.

## Consequences

Every future endpoint inherits the contract with no per-router work. The
envelope is a **permanent public contract**: changes are additive only, and
the generated client (M1C) types it once for all consumers. New error codes
must be added to the registry deliberately, in reviewed changes.

## Security and operations impact

No stack traces, exception types, or internals in responses; inbound header
values are allowlist-validated before entering logs; the correlation ID links
user reports, access logs, and error logs without exposing anything secret.

## Reconsideration triggers

An external-consumer requirement for RFC 9457; field-error granularity
proving insufficient for complex admin forms; a gateway imposing its own
correlation header semantics.
