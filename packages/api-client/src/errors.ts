// Public error types for the ADR-008 envelope contract.
//
// Every type here is an alias of the generated OpenAPI types — never a
// handwritten duplicate of a backend schema. If the backend contract
// changes, these aliases change with the next regeneration.

import type { components } from './generated/schema';

export type ErrorEnvelope = components['schemas']['ErrorEnvelope'];
export type ErrorDetail = components['schemas']['ErrorDetail'];
export type ErrorCode = components['schemas']['ErrorCode'];
export type FieldError = components['schemas']['FieldError'];

/**
 * Narrow an unknown error payload to the ADR-008 envelope shape.
 *
 * Validates the runtime types of every required field, not just key
 * presence, so a malformed body (e.g. `code: null`, `message: 42`) is
 * rejected rather than surfacing as a typed envelope. `code` is checked as
 * a string, deliberately not against the generated union: the registry is
 * append-only (ADR-008), and a newer backend code must still narrow on an
 * older client.
 */
export function isErrorEnvelope(value: unknown): value is ErrorEnvelope {
  if (!isPlainObject(value) || !('error' in value)) {
    return false;
  }
  const detail = value.error;
  if (!isPlainObject(detail)) {
    return false;
  }
  return (
    typeof detail['code'] === 'string' &&
    typeof detail['message'] === 'string' &&
    (detail['correlation_id'] === null ||
      typeof detail['correlation_id'] === 'string') &&
    Array.isArray(detail['field_errors']) &&
    detail['field_errors'].every(isFieldError) &&
    (detail['details'] === undefined ||
      detail['details'] === null ||
      isPlainObject(detail['details']))
  );
}

function isFieldError(value: unknown): value is FieldError {
  return (
    isPlainObject(value) &&
    typeof value['field'] === 'string' &&
    typeof value['code'] === 'string' &&
    typeof value['message'] === 'string'
  );
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
