// Hours facade behavior with an injected fetch — no network, no backend.
// Covers request shape (method/path/CSRF/body/query), success payloads
// including the defaults-projected fulfillment (`is_configured: false`),
// the per-date exception path parameter, envelope pass-through for the
// service-level 422 window rejection, and the platform timezone command
// (M5A, ADR-025).

import { describe, expect, it } from 'vitest';

import {
  createApiClient,
  type ErrorEnvelope,
  type HoursSettings,
} from '../src/index';

const BASE_URL = 'http://api.test';
const BID = '5f7d3f5e-3f3e-4b62-9a5e-3c7c2b1a0d9e';

const WEEKLY = [{ day_of_week: 0, opens_minute: 660, closes_minute: 1260 }];

const SETTINGS: HoursSettings = {
  timezone: 'America/New_York',
  weekly: WEEKLY,
  exceptions: [
    { exception_date: '2026-08-20', intervals: [], note: 'Closed for Eid' },
  ],
  fulfillment: {
    pickup_enabled: false,
    asap_enabled: true,
    lead_time_minutes: 20,
    slot_interval_minutes: 15,
    last_order_before_close_minutes: 30,
    max_days_ahead: 0,
    // M6A (ADR-026 D3): null = unlimited, the registry default.
    max_orders_per_slot: null,
    // M7A (ADR-027 D8): unpaused, the registry default.
    ordering_paused: false,
    pause_note: null,
    pause_resume_at: null,
    is_configured: false,
  },
};

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function envelope(
  code: ErrorEnvelope['error']['code'],
  details: Record<string, unknown> | null = null,
): ErrorEnvelope {
  return {
    error: {
      code,
      message: 'irrelevant',
      field_errors: [],
      correlation_id: 'c',
      details,
    },
  };
}

function clientCapturing(response: Response, requests: Request[] = []) {
  return createApiClient({
    baseUrl: BASE_URL,
    fetch: (input: Request) => {
      requests.push(input);
      return Promise.resolve(response);
    },
  });
}

describe('hours facade', () => {
  it('get issues a GET to the hours path and surfaces the settings', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(jsonResponse(200, SETTINGS), requests);

    const result = await client.hours.get(BID);

    expect(requests[0]?.method).toBe('GET');
    expect(requests[0]?.url).toBe(`${BASE_URL}/api/v1/businesses/${BID}/hours`);
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.timezone).toBe('America/New_York');
      expect(result.data.fulfillment.is_configured).toBe(false);
    }
  });

  it('preview passes the aware instant as the at query parameter', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(
      jsonResponse(200, {
        at: '2026-03-08T06:30:00Z',
        timezone: 'America/New_York',
        is_open_now: true,
        closes_at: '2026-03-08T07:00:00Z',
        next_opens_at: null,
        next_pickup_at: null,
      }),
      requests,
    );

    const result = await client.hours.preview(BID, {
      at: '2026-03-08T06:30:00Z',
    });

    expect(requests[0]?.method).toBe('GET');
    const url = new URL(requests[0]?.url ?? '');
    expect(url.pathname).toBe(`/api/v1/businesses/${BID}/hours/preview`);
    expect(url.searchParams.get('at')).toBe('2026-03-08T06:30:00Z');
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.is_open_now).toBe(true);
      expect(result.data.closes_at).toBe('2026-03-08T07:00:00Z');
    }
  });

  it('preview omits the query when no instant is given', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(jsonResponse(200, {}), requests);

    await client.hours.preview(BID);

    const url = new URL(requests[0]?.url ?? '');
    expect(url.searchParams.has('at')).toBe(false);
  });

  it('setWeekly PUTs the full schedule with the CSRF header', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(jsonResponse(200, SETTINGS), requests);

    const result = await client.hours.setWeekly(
      BID,
      { intervals: WEEKLY },
      'csrf-token',
    );

    const request = requests[0];
    expect(request?.method).toBe('PUT');
    expect(request?.url).toBe(
      `${BASE_URL}/api/v1/businesses/${BID}/hours/weekly`,
    );
    expect(request?.headers.get('X-CSRF-Token')).toBe('csrf-token');
    expect(await request?.json()).toEqual({ intervals: WEEKLY });
    expect(result.ok).toBe(true);
  });

  it('setException PUTs the date-addressed override', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(jsonResponse(200, SETTINGS), requests);

    await client.hours.setException(
      BID,
      '2026-08-20',
      { intervals: [], note: 'Closed for Eid' },
      'csrf-token',
    );

    const request = requests[0];
    expect(request?.method).toBe('PUT');
    expect(request?.url).toBe(
      `${BASE_URL}/api/v1/businesses/${BID}/hours/exceptions/2026-08-20`,
    );
    expect(request?.headers.get('X-CSRF-Token')).toBe('csrf-token');
    expect(await request?.json()).toEqual({
      intervals: [],
      note: 'Closed for Eid',
    });
  });

  it('deleteException DELETEs the date-addressed override', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(
      jsonResponse(200, { status: 'deleted' }),
      requests,
    );

    const result = await client.hours.deleteException(
      BID,
      '2026-08-20',
      'csrf-token',
    );

    const request = requests[0];
    expect(request?.method).toBe('DELETE');
    expect(request?.url).toBe(
      `${BASE_URL}/api/v1/businesses/${BID}/hours/exceptions/2026-08-20`,
    );
    expect(request?.headers.get('X-CSRF-Token')).toBe('csrf-token');
    expect(result.ok).toBe(true);
  });

  it('setFulfillment PUTs the full document', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(jsonResponse(200, SETTINGS), requests);

    const body = {
      pickup_enabled: true,
      asap_enabled: true,
      lead_time_minutes: 25,
      slot_interval_minutes: 15,
      last_order_before_close_minutes: 30,
      max_days_ahead: 3,
    };
    await client.hours.setFulfillment(BID, body, 'csrf-token');

    const request = requests[0];
    expect(request?.method).toBe('PUT');
    expect(request?.url).toBe(
      `${BASE_URL}/api/v1/businesses/${BID}/hours/fulfillment`,
    );
    expect(await request?.json()).toEqual(body);
  });

  it('surfaces the service-level window rejection envelope', async () => {
    const client = clientCapturing(
      jsonResponse(
        422,
        envelope('validation_error', {
          window_start: '2026-07-02',
          window_end: '2028-02-02',
        }),
      ),
    );

    const result = await client.hours.setException(
      BID,
      '2030-01-01',
      { intervals: [] },
      'csrf-token',
    );

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(422);
      expect(result.envelope?.error.code).toBe('validation_error');
      expect(result.envelope?.error.details).toEqual({
        window_start: '2026-07-02',
        window_end: '2028-02-02',
      });
    }
  });

  it('reports a network failure as ok:false with no status', async () => {
    const client = createApiClient({
      baseUrl: BASE_URL,
      fetch: () => Promise.reject(new Error('offline')),
    });

    const result = await client.hours.get(BID);

    expect(result).toEqual({ ok: false, status: null, envelope: null });
  });
});

describe('platform timezone command', () => {
  it('setTimezone PUTs the zone with the CSRF header', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(
      jsonResponse(200, {
        id: BID,
        name: 'Demo Kitchen',
        slug: 'demo-kitchen',
        status: 'active',
        timezone: 'America/Chicago',
        currency: 'USD',
        created_at: '2026-07-01T00:00:00Z',
        updated_at: '2026-08-01T00:00:00Z',
      }),
      requests,
    );

    const result = await client.platform.setTimezone(
      BID,
      { timezone: 'America/Chicago' },
      'csrf-token',
    );

    const request = requests[0];
    expect(request?.method).toBe('PUT');
    expect(request?.url).toBe(
      `${BASE_URL}/api/v1/platform/businesses/${BID}/timezone`,
    );
    expect(request?.headers.get('X-CSRF-Token')).toBe('csrf-token');
    expect(await request?.json()).toEqual({ timezone: 'America/Chicago' });
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.timezone).toBe('America/Chicago');
    }
  });

  it('surfaces the closed-business invalid_state envelope', async () => {
    const client = clientCapturing(
      jsonResponse(409, envelope('invalid_state')),
    );

    const result = await client.platform.setTimezone(
      BID,
      { timezone: 'America/Chicago' },
      'csrf-token',
    );

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(409);
      expect(result.envelope?.error.code).toBe('invalid_state');
    }
  });
});
