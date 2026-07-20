// Catalog facade behavior with an injected fetch — no network, no
// backend. Covers request shape (method/path/CSRF/body), success
// payloads, and envelope narrowing for the 404/409 catalog semantics.

import { describe, expect, it } from 'vitest';

import { createApiClient, type ErrorEnvelope } from '../src/index';

const BASE_URL = 'http://api.test';
const BID = '5f7d3f5e-3f3e-4b62-9a5e-3c7c2b1a0d9e';
const CID = '0a860cbe-4d55-4f6a-9d3f-2b6a7e1c9d10';
const IID = '9b7e6a5d-1c2b-4a3f-8e9d-0f1a2b3c4d5e';

const CATEGORY = {
  id: CID,
  name: 'Curries',
  description: null,
  position: 0,
  is_visible: true,
  created_at: '2026-07-19T00:00:00Z',
  updated_at: '2026-07-19T00:00:00Z',
};

const ITEM = {
  id: IID,
  category_id: CID,
  name: 'Chicken Biryani',
  description: null,
  price_minor: 1450,
  position: 0,
  is_available: true,
  is_hidden: false,
  is_featured: false,
  dietary_tags: ['halal'],
  created_at: '2026-07-19T00:00:00Z',
  updated_at: '2026-07-19T00:00:00Z',
};

const MENU = { categories: [{ ...CATEGORY, items: [ITEM] }] };

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

describe('catalog facade', () => {
  it('getMenu issues a GET to the aggregate menu path', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(jsonResponse(200, MENU), requests);

    const result = await client.catalog.getMenu(BID);

    expect(requests[0]?.method).toBe('GET');
    expect(requests[0]?.url).toBe(
      `${BASE_URL}/api/v1/businesses/${BID}/catalog/menu`,
    );
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.categories[0]?.items[0]?.price_minor).toBe(1450);
    }
  });

  it('createCategory posts the body with the CSRF header', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(jsonResponse(201, CATEGORY), requests);

    const result = await client.catalog.createCategory(
      BID,
      { name: 'Curries' },
      'csrf-token',
    );

    expect(requests[0]?.method).toBe('POST');
    expect(requests[0]?.url).toBe(
      `${BASE_URL}/api/v1/businesses/${BID}/catalog/categories`,
    );
    expect(requests[0]?.headers.get('X-CSRF-Token')).toBe('csrf-token');
    expect(await requests[0]?.json()).toEqual({ name: 'Curries' });
    expect(result.ok).toBe(true);
  });

  it('updateCategory PATCHes the category path', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(jsonResponse(200, CATEGORY), requests);

    await client.catalog.updateCategory(
      BID,
      CID,
      { is_visible: false },
      'csrf-token',
    );

    expect(requests[0]?.method).toBe('PATCH');
    expect(requests[0]?.url).toBe(
      `${BASE_URL}/api/v1/businesses/${BID}/catalog/categories/${CID}`,
    );
    expect(requests[0]?.headers.get('X-CSRF-Token')).toBe('csrf-token');
  });

  it('deleteCategory narrows the non-empty 409 envelope', async () => {
    const client = clientCapturing(jsonResponse(409, envelope('conflict')));

    const result = await client.catalog.deleteCategory(BID, CID, 'csrf-token');

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(409);
      expect(result.envelope?.error.code).toBe('conflict');
    }
  });

  it('reorderCategories posts the full id set and returns the menu', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(jsonResponse(200, MENU), requests);

    const result = await client.catalog.reorderCategories(
      BID,
      { ordered_category_ids: [CID] },
      'csrf-token',
    );

    expect(requests[0]?.url).toBe(
      `${BASE_URL}/api/v1/businesses/${BID}/catalog/categories/reorder`,
    );
    expect(await requests[0]?.json()).toEqual({
      ordered_category_ids: [CID],
    });
    expect(result.ok).toBe(true);
  });

  it('createItem posts under the category path', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(jsonResponse(201, ITEM), requests);

    const result = await client.catalog.createItem(
      BID,
      CID,
      { name: 'Chicken Biryani', price_minor: 1450, dietary_tags: ['halal'] },
      'csrf-token',
    );

    expect(requests[0]?.url).toBe(
      `${BASE_URL}/api/v1/businesses/${BID}/catalog/categories/${CID}/items`,
    );
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.dietary_tags).toEqual(['halal']);
    }
  });

  it('getItem narrows the cross-tenant 404 envelope', async () => {
    const client = clientCapturing(jsonResponse(404, envelope('not_found')));

    const result = await client.catalog.getItem(BID, IID);

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(404);
      expect(result.envelope?.error.code).toBe('not_found');
    }
  });

  it('updateItem PATCHes the item path with the body', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(jsonResponse(200, ITEM), requests);

    await client.catalog.updateItem(
      BID,
      IID,
      { price_minor: 1550 },
      'csrf-token',
    );

    expect(requests[0]?.method).toBe('PATCH');
    expect(requests[0]?.url).toBe(
      `${BASE_URL}/api/v1/businesses/${BID}/catalog/items/${IID}`,
    );
    expect(await requests[0]?.json()).toEqual({ price_minor: 1550 });
  });

  it('deleteItem sends DELETE with the CSRF header', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(
      jsonResponse(200, { status: 'deleted' }),
      requests,
    );

    const result = await client.catalog.deleteItem(BID, IID, 'csrf-token');

    expect(requests[0]?.method).toBe('DELETE');
    expect(requests[0]?.headers.get('X-CSRF-Token')).toBe('csrf-token');
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.status).toBe('deleted');
    }
  });

  it('reorderItems posts category and ordered ids', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(jsonResponse(200, MENU), requests);

    await client.catalog.reorderItems(
      BID,
      { category_id: CID, ordered_item_ids: [IID] },
      'csrf-token',
    );

    expect(requests[0]?.url).toBe(
      `${BASE_URL}/api/v1/businesses/${BID}/catalog/items/reorder`,
    );
    expect(await requests[0]?.json()).toEqual({
      category_id: CID,
      ordered_item_ids: [IID],
    });
  });

  it('setItemAvailability posts the availability command', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(
      jsonResponse(200, { ...ITEM, is_available: false }),
      requests,
    );

    const result = await client.catalog.setItemAvailability(
      BID,
      IID,
      { is_available: false },
      'csrf-token',
    );

    expect(requests[0]?.url).toBe(
      `${BASE_URL}/api/v1/businesses/${BID}/catalog/items/${IID}/availability`,
    );
    expect(await requests[0]?.json()).toEqual({ is_available: false });
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.is_available).toBe(false);
    }
  });

  it('network failure resolves to the null-status failure result', async () => {
    const client = createApiClient({
      baseUrl: BASE_URL,
      fetch: () => Promise.reject(new Error('boom')),
    });

    const result = await client.catalog.getMenu(BID);

    expect(result).toEqual({ ok: false, status: null, envelope: null });
  });
});
