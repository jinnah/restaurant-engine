// Hours administration facade (M5A, ADR-025).
//
// Business-scoped operations over the hours domain: the complete
// operating configuration in one read (timezone, weekly schedule,
// windowed exceptions, effective fulfillment settings), the full-week
// replacement PUT, the per-date exception upsert/delete (empty intervals
// = closed all day; DELETE = the exception is gone and the weekly
// schedule resumes), the full-document fulfillment PUT, and the member
// availability preview (`at` optional — an aware instant, so a DST
// weekend or a holiday can be checked before it happens). The platform
// timezone command (ruling D2) lives on the platform facade group.

import type { Client } from 'openapi-fetch';

import type { components, paths } from './generated/schema';
import { toResult, type ApiResult } from './result';

export type HoursSettings = components['schemas']['HoursSettings'];
export type HoursInterval = components['schemas']['HoursInterval'];
export type WeeklyIntervalIn = components['schemas']['WeeklyIntervalIn'];
export type WeeklyIntervalOut = components['schemas']['WeeklyIntervalOut'];
export type WeeklyScheduleSet = components['schemas']['WeeklyScheduleSet'];
export type ScheduleExceptionSet =
  components['schemas']['ScheduleExceptionSet'];
export type ScheduleExceptionOut =
  components['schemas']['ScheduleExceptionOut'];
export type FulfillmentSet = components['schemas']['FulfillmentSet'];
export type FulfillmentOut = components['schemas']['FulfillmentOut'];
// M7A (ADR-027 D8): pause/resume — its own command, never a
// fulfillment-document field.
export type OrderingPauseSet = components['schemas']['OrderingPauseSet'];
export type AvailabilityPreview = components['schemas']['AvailabilityPreview'];
export type HoursDeletedResponse =
  components['schemas']['HoursDeletedResponse'];

const CSRF_HEADER = 'X-CSRF-Token';

export interface HoursApi {
  /** The complete operating configuration in one read. */
  get(businessId: string): Promise<ApiResult<HoursSettings>>;
  /**
   * The computed availability facts at `at` (default: now). `at` must be
   * a timezone-aware ISO instant; a naive value is a 422.
   */
  preview(
    businessId: string,
    params?: { at?: string },
  ): Promise<ApiResult<AvailabilityPreview>>;
  /** Replace the whole weekly schedule (idempotent full replacement). */
  setWeekly(
    businessId: string,
    body: WeeklyScheduleSet,
    csrfToken: string,
  ): Promise<ApiResult<HoursSettings>>;
  /**
   * Create or replace one date's override. Empty intervals = closed all
   * day; the date is an ISO `YYYY-MM-DD` local calendar date.
   */
  setException(
    businessId: string,
    exceptionDate: string,
    body: ScheduleExceptionSet,
    csrfToken: string,
  ): Promise<ApiResult<HoursSettings>>;
  /** Remove one date's override; the weekly schedule resumes. */
  deleteException(
    businessId: string,
    exceptionDate: string,
    csrfToken: string,
  ): Promise<ApiResult<HoursDeletedResponse>>;
  /** Write the complete fulfillment policy (full-document command). */
  setFulfillment(
    businessId: string,
    body: FulfillmentSet,
    csrfToken: string,
  ): Promise<ApiResult<HoursSettings>>;
  /** Pause or resume ordering (M7A, ADR-027 D8) — its own command. */
  setOrderingPause(
    businessId: string,
    body: OrderingPauseSet,
    csrfToken: string,
  ): Promise<ApiResult<HoursSettings>>;
}

export function createHoursApi(client: Client<paths>): HoursApi {
  const csrf = (csrfToken: string) => ({ [CSRF_HEADER]: csrfToken });
  const path = (businessId: string) => ({
    params: { path: { business_id: businessId } },
  });
  const datePath = (businessId: string, exceptionDate: string) => ({
    params: {
      path: { business_id: businessId, exception_date: exceptionDate },
    },
  });

  return {
    async get(businessId) {
      try {
        const { data, error, response } = await client.GET(
          '/api/v1/businesses/{business_id}/hours',
          path(businessId),
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async preview(businessId, params) {
      try {
        const { data, error, response } = await client.GET(
          '/api/v1/businesses/{business_id}/hours/preview',
          {
            params: {
              path: { business_id: businessId },
              query: { at: params?.at },
            },
          },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async setWeekly(businessId, body, csrfToken) {
      try {
        const { data, error, response } = await client.PUT(
          '/api/v1/businesses/{business_id}/hours/weekly',
          { ...path(businessId), body, headers: csrf(csrfToken) },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async setException(businessId, exceptionDate, body, csrfToken) {
      try {
        const { data, error, response } = await client.PUT(
          '/api/v1/businesses/{business_id}/hours/exceptions/{exception_date}',
          {
            ...datePath(businessId, exceptionDate),
            body,
            headers: csrf(csrfToken),
          },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async deleteException(businessId, exceptionDate, csrfToken) {
      try {
        const { data, error, response } = await client.DELETE(
          '/api/v1/businesses/{business_id}/hours/exceptions/{exception_date}',
          { ...datePath(businessId, exceptionDate), headers: csrf(csrfToken) },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async setFulfillment(businessId, body, csrfToken) {
      try {
        const { data, error, response } = await client.PUT(
          '/api/v1/businesses/{business_id}/hours/fulfillment',
          { ...path(businessId), body, headers: csrf(csrfToken) },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },

    async setOrderingPause(businessId, body, csrfToken) {
      try {
        const { data, error, response } = await client.PUT(
          '/api/v1/businesses/{business_id}/hours/pause',
          { ...path(businessId), body, headers: csrf(csrfToken) },
        );
        return toResult(data, error, response);
      } catch {
        return { ok: false, status: null, envelope: null };
      }
    },
  };
}
