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

/** Narrow an unknown error payload to the ADR-008 envelope shape. */
export function isErrorEnvelope(value: unknown): value is ErrorEnvelope {
  if (typeof value !== 'object' || value === null || !('error' in value)) {
    return false;
  }
  const detail = (value as { error: unknown }).error;
  return (
    typeof detail === 'object' &&
    detail !== null &&
    'code' in detail &&
    'message' in detail &&
    'correlation_id' in detail
  );
}
