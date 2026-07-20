// Media facade behavior with an injected fetch — no network, no backend.
// Covers the multipart upload request shape, list/get/delete via the typed
// client, the 413/409 envelope narrowing, and the opaque preview URL.

import { describe, expect, it } from 'vitest';

import { createApiClient, type ErrorEnvelope } from '../src/index';

const BASE_URL = 'http://api.test';
const BID = '5f7d3f5e-3f3e-4b62-9a5e-3c7c2b1a0d9e';
const AID = '9b7e6a5d-1c2b-4a3f-8e9d-0f1a2b3c4d5e';

const ASSET = {
  id: AID,
  kind: 'image',
  status: 'pending',
  pending_expires_at: '2026-07-22T00:00:00Z',
  original_filename: 'dish.jpg',
  source_format: 'jpeg',
  width: 1000,
  height: 800,
  byte_size: 12345,
  variants: [{ variant: 'w320', width: 320, height: 256, byte_size: 2000 }],
  created_at: '2026-07-20T00:00:00Z',
  updated_at: '2026-07-20T00:00:00Z',
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

function clientCapturing(response: Response, requests: Request[]) {
  return createApiClient({
    baseUrl: BASE_URL,
    fetch: (input: RequestInfo | URL, init?: RequestInit) => {
      requests.push(new Request(input as string, init));
      return Promise.resolve(response);
    },
  });
}

describe('media facade', () => {
  it('uploadAsset posts multipart form data with the CSRF token', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(jsonResponse(201, ASSET), requests);

    const file = new Blob([new Uint8Array([1, 2, 3])], { type: 'image/jpeg' });
    const result = await client.media.uploadAsset(
      BID,
      file,
      'dish.jpg',
      'csrf-token',
    );

    const request = requests[0];
    expect(request?.method).toBe('POST');
    expect(request?.url).toBe(`${BASE_URL}/api/v1/businesses/${BID}/media`);
    expect(request?.headers.get('X-CSRF-Token')).toBe('csrf-token');
    const contentType = request?.headers.get('Content-Type') ?? '';
    expect(contentType.startsWith('multipart/form-data')).toBe(true);
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.status).toBe('pending');
    }
  });

  it('uploadAsset narrows the 413 payload_too_large envelope', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(
      jsonResponse(413, envelope('payload_too_large')),
      requests,
    );

    const file = new Blob([new Uint8Array([1])], { type: 'image/jpeg' });
    const result = await client.media.uploadAsset(BID, file, 'big.jpg', 'csrf');

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(413);
      expect(result.envelope?.error.code).toBe('payload_too_large');
    }
  });

  it('listAssets sends limit/offset/status query params', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(
      jsonResponse(200, { items: [ASSET], total: 1, limit: 10, offset: 0 }),
      requests,
    );

    const result = await client.media.listAssets(BID, {
      limit: 10,
      offset: 0,
      status: 'pending',
    });

    const url = new URL(requests[0]?.url ?? '');
    expect(url.pathname).toBe(`/api/v1/businesses/${BID}/media`);
    expect(url.searchParams.get('limit')).toBe('10');
    expect(url.searchParams.get('status')).toBe('pending');
    expect(result.ok).toBe(true);
  });

  it('deleteAsset narrows the 409 conflict envelope for a referenced asset', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(
      jsonResponse(409, envelope('conflict')),
      requests,
    );

    const result = await client.media.deleteAsset(BID, AID, 'csrf');

    expect(requests[0]?.method).toBe('DELETE');
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(409);
      expect(result.envelope?.error.code).toBe('conflict');
    }
  });

  it('fileUrl builds the opaque preview URL from asset id and variant', () => {
    const client = createApiClient({ baseUrl: BASE_URL });
    expect(client.media.fileUrl(BID, AID, 'canonical')).toBe(
      `${BASE_URL}/api/v1/businesses/${BID}/media/${AID}/file/canonical`,
    );
    expect(client.media.fileUrl(BID, AID, 'w640')).toBe(
      `${BASE_URL}/api/v1/businesses/${BID}/media/${AID}/file/w640`,
    );
  });

  it('network failure resolves to the null-status failure result', async () => {
    const client = createApiClient({
      baseUrl: BASE_URL,
      fetch: () => Promise.reject(new Error('boom')),
    });

    const result = await client.media.getAsset(BID, AID);

    expect(result).toEqual({ ok: false, status: null, envelope: null });
  });
});
