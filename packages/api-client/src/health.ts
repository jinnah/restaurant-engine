// Health facade methods (M1C).
//
// Kept flat on the client (`client.getLiveness()`) — they predate the
// domain-grouped facade shape introduced with auth (M2A) and are part of
// the M1C surface.

import type { Client } from 'openapi-fetch';

import type { components, paths } from './generated/schema';
import { toResult, type ApiResult } from './result';

export type LivenessResponse = components['schemas']['LivenessResponse'];
export type ReadinessResponse = components['schemas']['ReadinessResponse'];

export interface HealthMethods {
  getLiveness(): Promise<ApiResult<LivenessResponse>>;
  getReadiness(): Promise<ApiResult<ReadinessResponse>>;
}

export function createHealthMethods(client: Client<paths>): HealthMethods {
  return {
    async getLiveness(): Promise<ApiResult<LivenessResponse>> {
      try {
        const { data, error, response } = await client.GET('/health/live');
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async getReadiness(): Promise<ApiResult<ReadinessResponse>> {
      try {
        const { data, error, response } = await client.GET('/health/ready');
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },
  };
}
