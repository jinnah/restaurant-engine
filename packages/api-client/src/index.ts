// Public surface of @restaurant-engine/api-client.
//
// Applications import ONLY from this module — the package `exports` map
// exposes nothing else, so `src/generated/*` (and openapi-fetch itself)
// stay replaceable implementation details (ADR-009).

export { createApiClient } from './health';
export type {
  ApiClient,
  ApiResult,
  LivenessResponse,
  ReadinessResponse,
} from './health';
export type { ApiClientOptions } from './client';
export { isErrorEnvelope } from './errors';
export type {
  ErrorCode,
  ErrorDetail,
  ErrorEnvelope,
  FieldError,
} from './errors';
