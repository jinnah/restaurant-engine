// Public surface of @restaurant-engine/api-client.
//
// Applications import ONLY from this module — the package `exports` map
// exposes nothing else, so `src/generated/*` (and openapi-fetch itself)
// stay replaceable implementation details (ADR-009).

export { createApiClient } from './facade';
export type { ApiClient } from './facade';
export type { ApiClientOptions } from './client';
export type { ApiResult } from './result';
export type { LivenessResponse, ReadinessResponse } from './health';
export type {
  AuthApi,
  LoginRequest,
  LogoutResponse,
  MembershipSummary,
  SessionResponse,
  SessionView,
  UserSummary,
} from './auth';
export type {
  BusinessCreate,
  BusinessPage,
  BusinessSummary,
  PlatformApi,
} from './platform';
export type { BusinessesApi } from './businesses';
export { isErrorEnvelope } from './errors';
export type {
  ErrorCode,
  ErrorDetail,
  ErrorEnvelope,
  FieldError,
} from './errors';
