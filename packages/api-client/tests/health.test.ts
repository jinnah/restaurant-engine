// Facade behavior with an injected fetch — no network, no backend process.
// Covers: typed success payloads, the ADR-008 error envelope on 503,
// non-JSON failure bodies, and network failure.

import { describe, expect, it } from 'vitest';

import { createApiClient, type ErrorEnvelope } from '../src/index';

const BASE_URL = 'http://api.test';

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function clientReturning(response: Response, seenUrls: string[] = []) {
  return createApiClient({
    baseUrl: BASE_URL,
    fetch: (input: Request) => {
      seenUrls.push(input.url);
      return Promise.resolve(response);
    },
  });
}

describe('getLiveness', () => {
  it('returns the typed payload and calls the expected path', async () => {
    const seenUrls: string[] = [];
    const client = clientReturning(
      jsonResponse(200, { status: 'alive' }),
      seenUrls,
    );

    const result = await client.getLiveness();

    expect(seenUrls).toEqual([`${BASE_URL}/health/live`]);
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.status).toBe(200);
      expect(result.data.status).toBe('alive');
    }
  });

  it('reports a network failure as a null-status failure', async () => {
    const client = createApiClient({
      baseUrl: BASE_URL,
      fetch: () => Promise.reject(new Error('connection refused')),
    });

    const result = await client.getLiveness();

    expect(result).toEqual({ ok: false, status: null, envelope: null });
  });
});

describe('getReadiness', () => {
  it('returns the typed payload when the API is ready', async () => {
    const client = clientReturning(
      jsonResponse(200, {
        status: 'ready',
        checks: { database: { status: 'up' } },
      }),
    );

    const result = await client.getReadiness();

    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.status).toBe('ready');
      expect(result.data.checks['database']?.status).toBe('up');
    }
  });

  it('preserves the ADR-008 envelope on 503', async () => {
    const envelope: ErrorEnvelope = {
      error: {
        code: 'dependency_unavailable',
        message: 'Service dependencies are unavailable.',
        field_errors: [],
        correlation_id: 'test-correlation-id',
        details: { checks: { database: 'down' } },
      },
    };
    const client = clientReturning(jsonResponse(503, envelope));

    const result = await client.getReadiness();

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(503);
      expect(result.envelope).not.toBeNull();
      expect(result.envelope?.error.code).toBe('dependency_unavailable');
      expect(result.envelope?.error.correlation_id).toBe('test-correlation-id');
      expect(result.envelope?.error.details).toEqual({
        checks: { database: 'down' },
      });
    }
  });

  it.each([
    [
      'code is null',
      { code: null, message: 'm', field_errors: [], correlation_id: 'c' },
    ],
    [
      'message is a number',
      {
        code: 'http_error',
        message: 42,
        field_errors: [],
        correlation_id: 'c',
      },
    ],
    [
      'correlation_id is a number',
      { code: 'http_error', message: 'm', field_errors: [], correlation_id: 7 },
    ],
    [
      'field_errors is not an array',
      {
        code: 'http_error',
        message: 'm',
        field_errors: 'nope',
        correlation_id: 'c',
      },
    ],
    [
      'field_errors entry is malformed',
      {
        code: 'http_error',
        message: 'm',
        field_errors: [{ field: 'f' }],
        correlation_id: 'c',
      },
    ],
    [
      'details is a primitive',
      {
        code: 'http_error',
        message: 'm',
        field_errors: [],
        correlation_id: 'c',
        details: 'oops',
      },
    ],
    ['detail is missing entirely', undefined],
  ])(
    'rejects a malformed JSON envelope (%s) as envelope: null',
    async (_label, detail) => {
      const body =
        detail === undefined ? { unexpected: true } : { error: detail };
      const client = clientReturning(jsonResponse(503, body));

      const result = await client.getReadiness();

      expect(result.ok).toBe(false);
      if (!result.ok) {
        expect(result.status).toBe(503);
        expect(result.envelope).toBeNull();
      }
    },
  );

  it('reports a non-JSON error body as a failure without an envelope', async () => {
    const client = clientReturning(
      new Response('<html>Bad Gateway</html>', {
        status: 502,
        headers: { 'Content-Type': 'text/html' },
      }),
    );

    const result = await client.getReadiness();

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.envelope).toBeNull();
    }
  });
});
