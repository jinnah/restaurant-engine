// Modifier facade behavior with an injected fetch — no network, no
// backend. Covers request shape (method/path/CSRF/body), success
// payloads with computed satisfiability, and envelope narrowing.

import { describe, expect, it } from 'vitest';

import { createApiClient, type ErrorEnvelope } from '../src/index';

const BASE_URL = 'http://api.test';
const BID = '5f7d3f5e-3f3e-4b62-9a5e-3c7c2b1a0d9e';
const IID = '9b7e6a5d-1c2b-4a3f-8e9d-0f1a2b3c4d5e';
const GID = '0a860cbe-4d55-4f6a-9d3f-2b6a7e1c9d10';
const OID = '7c1d2e3f-4a5b-6c7d-8e9f-0a1b2c3d4e5f';

const OPTION = {
  id: OID,
  group_id: GID,
  name: 'Extra Chicken',
  price_delta_minor: 450,
  is_available: true,
  position: 0,
  created_at: '2026-07-20T00:00:00Z',
  updated_at: '2026-07-20T00:00:00Z',
};

const GROUP = {
  id: GID,
  item_id: IID,
  name: 'Add-ons',
  min_select: 0,
  max_select: null,
  position: 0,
  active_option_count: 1,
  is_satisfiable: true,
  options: [OPTION],
  created_at: '2026-07-20T00:00:00Z',
  updated_at: '2026-07-20T00:00:00Z',
};

const TREE = { item_id: IID, groups: [GROUP] };

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function envelope(code: ErrorEnvelope['error']['code']): ErrorEnvelope {
  return {
    error: {
      code,
      message: 'irrelevant',
      field_errors: [],
      correlation_id: 'c',
      details: null,
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

describe('modifier facade', () => {
  it('getModifierGroups issues a GET to the per-item tree path', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(jsonResponse(200, TREE), requests);

    const result = await client.catalog.getModifierGroups(BID, IID);

    expect(requests[0]?.method).toBe('GET');
    expect(requests[0]?.url).toBe(
      `${BASE_URL}/api/v1/businesses/${BID}/catalog/items/${IID}/modifier-groups`,
    );
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.groups[0]?.is_satisfiable).toBe(true);
      expect(result.data.groups[0]?.active_option_count).toBe(1);
    }
  });

  it('createModifierGroup posts with the CSRF header', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(jsonResponse(201, GROUP), requests);

    const result = await client.catalog.createModifierGroup(
      BID,
      IID,
      { name: 'Add-ons', min_select: 0, max_select: null },
      'csrf-token',
    );

    expect(requests[0]?.method).toBe('POST');
    expect(requests[0]?.url).toBe(
      `${BASE_URL}/api/v1/businesses/${BID}/catalog/items/${IID}/modifier-groups`,
    );
    expect(requests[0]?.headers.get('X-CSRF-Token')).toBe('csrf-token');
    expect(result.ok).toBe(true);
  });

  it('updateModifierGroup PATCHes with an explicit null maximum', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(jsonResponse(200, GROUP), requests);

    await client.catalog.updateModifierGroup(
      BID,
      GID,
      { max_select: null },
      'csrf-token',
    );

    expect(requests[0]?.method).toBe('PATCH');
    expect(requests[0]?.url).toBe(
      `${BASE_URL}/api/v1/businesses/${BID}/catalog/modifier-groups/${GID}`,
    );
    expect(await requests[0]?.json()).toEqual({ max_select: null });
  });

  it('deleteModifierGroup narrows the 409 conflict envelope', async () => {
    const client = clientCapturing(jsonResponse(409, envelope('conflict')));

    const result = await client.catalog.deleteModifierGroup(
      BID,
      GID,
      'csrf-token',
    );

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(409);
      expect(result.envelope?.error.code).toBe('conflict');
    }
  });

  it('reorderModifierGroups posts the full id set', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(jsonResponse(200, TREE), requests);

    await client.catalog.reorderModifierGroups(
      BID,
      IID,
      { ordered_group_ids: [GID] },
      'csrf-token',
    );

    expect(requests[0]?.url).toBe(
      `${BASE_URL}/api/v1/businesses/${BID}/catalog/items/${IID}/modifier-groups/reorder`,
    );
    expect(await requests[0]?.json()).toEqual({ ordered_group_ids: [GID] });
  });

  it('createModifierOption returns the recomputed parent group', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(jsonResponse(201, GROUP), requests);

    const result = await client.catalog.createModifierOption(
      BID,
      GID,
      { name: 'Extra Chicken', price_delta_minor: 450 },
      'csrf-token',
    );

    expect(requests[0]?.url).toBe(
      `${BASE_URL}/api/v1/businesses/${BID}/catalog/modifier-groups/${GID}/options`,
    );
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.options[0]?.price_delta_minor).toBe(450);
    }
  });

  it('updateModifierOption carries availability in the PATCH body', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(jsonResponse(200, GROUP), requests);

    await client.catalog.updateModifierOption(
      BID,
      OID,
      { is_available: false },
      'csrf-token',
    );

    expect(requests[0]?.method).toBe('PATCH');
    expect(requests[0]?.url).toBe(
      `${BASE_URL}/api/v1/businesses/${BID}/catalog/modifier-options/${OID}`,
    );
    expect(await requests[0]?.json()).toEqual({ is_available: false });
    expect(requests[0]?.headers.get('X-CSRF-Token')).toBe('csrf-token');
  });

  it('deleteModifierOption narrows the cross-tenant 404', async () => {
    const client = clientCapturing(jsonResponse(404, envelope('not_found')));

    const result = await client.catalog.deleteModifierOption(
      BID,
      OID,
      'csrf-token',
    );

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(404);
      expect(result.envelope?.error.code).toBe('not_found');
    }
  });

  it('reorderModifierOptions posts the full id set', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(jsonResponse(200, GROUP), requests);

    await client.catalog.reorderModifierOptions(
      BID,
      GID,
      { ordered_option_ids: [OID] },
      'csrf-token',
    );

    expect(requests[0]?.url).toBe(
      `${BASE_URL}/api/v1/businesses/${BID}/catalog/modifier-groups/${GID}/options/reorder`,
    );
    expect(await requests[0]?.json()).toEqual({ ordered_option_ids: [OID] });
  });

  it('network failure resolves to the null-status failure result', async () => {
    const client = createApiClient({
      baseUrl: BASE_URL,
      fetch: () => Promise.reject(new Error('boom')),
    });

    const result = await client.catalog.getModifierGroups(BID, IID);

    expect(result).toEqual({ ok: false, status: null, envelope: null });
  });
});
