// Storefront facade behavior with an injected fetch — no network, no
// backend. Covers request shape (method/path/CSRF/body), success
// payloads including the draft:null first-use absence, and envelope
// narrowing for the 409 concurrency semantics (details carries the
// current lock_version).

import { describe, expect, it } from 'vitest';

import {
  createApiClient,
  type DraftPut,
  type ErrorEnvelope,
} from '../src/index';

const BASE_URL = 'http://api.test';
const BID = '5f7d3f5e-3f3e-4b62-9a5e-3c7c2b1a0d9e';
const VID = '0a860cbe-4d55-4f6a-9d3f-2b6a7e1c9d10';

// Annotated so `schema_version` stays the literal 1 the contract pins.
// The theme names every defaulted field because the generated type makes
// them required (M4G-A added palette and type_pairing); `logo` is genuinely
// optional and is omitted here.
const CONFIG: DraftPut['config'] = {
  schema_version: 1,
  theme: { accent: '#a34b2a', palette: 'warm', type_pairing: 'humanist' },
  sections: [],
};

const DRAFT = {
  config: CONFIG,
  design_variant: 'classic',
  lock_version: 3,
  schema_version: 1,
  source_version_id: null,
  created_at: '2026-07-28T00:00:00Z',
  updated_at: '2026-07-28T00:00:00Z',
};

const PUBLISHED = {
  id: VID,
  version_number: 2,
  design_variant: 'classic',
  schema_version: 1,
  published_at: '2026-07-28T00:00:00Z',
  published_by_user_id: '9b7e6a5d-1c2b-4a3f-8e9d-0f1a2b3c4d5e',
};

const VERSION_SUMMARY = {
  ...PUBLISHED,
  state: 'published',
  source_version_id: null,
  created_at: '2026-07-28T00:00:00Z',
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

describe('storefront facade', () => {
  it('get issues a GET to the overview path and surfaces first-use absence', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(
      jsonResponse(200, { draft: null, published: null }),
      requests,
    );

    const result = await client.storefront.get(BID);

    expect(requests[0]?.method).toBe('GET');
    expect(requests[0]?.url).toBe(
      `${BASE_URL}/api/v1/businesses/${BID}/storefront`,
    );
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.draft).toBeNull();
      expect(result.data.published).toBeNull();
    }
  });

  it('putDraft PUTs the full document with the CSRF header', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(jsonResponse(200, DRAFT), requests);

    const result = await client.storefront.putDraft(
      BID,
      { config: CONFIG, expected_lock_version: 2 },
      'csrf-token',
    );

    expect(requests[0]?.method).toBe('PUT');
    expect(requests[0]?.url).toBe(
      `${BASE_URL}/api/v1/businesses/${BID}/storefront/draft`,
    );
    expect(requests[0]?.headers.get('X-CSRF-Token')).toBe('csrf-token');
    expect(await requests[0]?.json()).toEqual({
      config: CONFIG,
      expected_lock_version: 2,
    });
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.lock_version).toBe(3);
    }
  });

  it('putDraft create intent omits expected_lock_version entirely', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(jsonResponse(200, DRAFT), requests);

    await client.storefront.putDraft(BID, { config: CONFIG }, 'csrf-token');

    // Omitted — not null-filled — so the server sees create intent.
    expect(await requests[0]?.json()).toEqual({ config: CONFIG });
  });

  it('putDraft narrows the stale-write 409 with the current lock version', async () => {
    const client = clientCapturing(
      jsonResponse(409, envelope('conflict', { lock_version: 5 })),
    );

    const result = await client.storefront.putDraft(
      BID,
      { config: CONFIG, expected_lock_version: 2 },
      'csrf-token',
    );

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(409);
      expect(result.envelope?.error.code).toBe('conflict');
      expect(result.envelope?.error.details).toEqual({ lock_version: 5 });
    }
  });

  it('publish POSTs the expected lock version', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(
      jsonResponse(200, { draft: DRAFT, published: PUBLISHED }),
      requests,
    );

    const result = await client.storefront.publish(
      BID,
      { expected_lock_version: 3 },
      'csrf-token',
    );

    expect(requests[0]?.method).toBe('POST');
    expect(requests[0]?.url).toBe(
      `${BASE_URL}/api/v1/businesses/${BID}/storefront/publish`,
    );
    expect(requests[0]?.headers.get('X-CSRF-Token')).toBe('csrf-token');
    expect(await requests[0]?.json()).toEqual({ expected_lock_version: 3 });
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.published?.version_number).toBe(2);
    }
  });

  it('listVersions issues a GET with pagination query parameters', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(
      jsonResponse(200, {
        items: [VERSION_SUMMARY],
        total: 1,
        limit: 10,
        offset: 0,
      }),
      requests,
    );

    const result = await client.storefront.listVersions(BID, {
      limit: 10,
      offset: 0,
    });

    expect(requests[0]?.method).toBe('GET');
    expect(requests[0]?.url).toBe(
      `${BASE_URL}/api/v1/businesses/${BID}/storefront/versions?limit=10&offset=0`,
    );
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.items[0]?.version_number).toBe(2);
    }
  });

  it('getVersion issues a GET to the version detail path', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(
      jsonResponse(200, { ...VERSION_SUMMARY, config: CONFIG }),
      requests,
    );

    const result = await client.storefront.getVersion(BID, VID);

    expect(requests[0]?.method).toBe('GET');
    expect(requests[0]?.url).toBe(
      `${BASE_URL}/api/v1/businesses/${BID}/storefront/versions/${VID}`,
    );
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.config).toEqual(CONFIG);
    }
  });

  it('restoreVersion POSTs to the restore path with the CSRF header', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(jsonResponse(200, DRAFT), requests);

    const result = await client.storefront.restoreVersion(
      BID,
      VID,
      { expected_lock_version: 0 },
      'csrf-token',
    );

    expect(requests[0]?.method).toBe('POST');
    expect(requests[0]?.url).toBe(
      `${BASE_URL}/api/v1/businesses/${BID}/storefront/versions/${VID}/restore`,
    );
    expect(requests[0]?.headers.get('X-CSRF-Token')).toBe('csrf-token');
    expect(await requests[0]?.json()).toEqual({ expected_lock_version: 0 });
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data.lock_version).toBe(3);
    }
  });

  it('restoreVersion narrows the archived-only 409 invalid_state', async () => {
    const client = clientCapturing(
      jsonResponse(409, envelope('invalid_state')),
    );

    const result = await client.storefront.restoreVersion(
      BID,
      VID,
      { expected_lock_version: 0 },
      'csrf-token',
    );

    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(409);
      expect(result.envelope?.error.code).toBe('invalid_state');
    }
  });

  it('surfaces a network failure as a null-status result', async () => {
    const client = createApiClient({
      baseUrl: BASE_URL,
      fetch: () => Promise.reject(new TypeError('network down')),
    });

    const result = await client.storefront.get(BID);

    expect(result).toEqual({ ok: false, status: null, envelope: null });
  });
});

const PREVIEW = {
  business: {
    name: 'Shalik',
    slug: 'shalik',
    timezone: 'America/New_York',
    currency: 'USD',
  },
  design_variant: 'classic' as const,
  theme: { accent: '#a34b2a' },
  sections: [
    {
      id: 'hero-main',
      type: 'hero' as const,
      props: {
        heading: 'Draft hero',
        subheading: null,
        image: {
          alt_text: null,
          width: 1200,
          height: 800,
          url: `/api/v1/businesses/${BID}/media/33333333-3333-3333-3333-333333333333/file/canonical`,
          variants: [],
        },
        primary_action: 'none' as const,
      },
    },
  ],
};

describe('storefront.preview', () => {
  it('GETs the preview path without a CSRF header (a read)', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(jsonResponse(200, PREVIEW), requests);

    const result = await client.storefront.preview(BID);

    const url = new URL(requests[0]!.url);
    expect(url.pathname).toBe(`/api/v1/businesses/${BID}/storefront/preview`);
    expect(requests[0]?.method).toBe('GET');
    expect(requests[0]?.headers.get('X-CSRF-Token')).toBeNull();
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.data).toEqual(PREVIEW);
      // Preview media addresses the authenticated member route, never the
      // anonymous public delivery path.
      const hero = result.data.sections[0];
      if (hero?.type === 'hero') {
        expect(hero.props.image?.url).toMatch(
          new RegExp(`^/api/v1/businesses/${BID}/media/`),
        );
      }
    }
  });

  it('narrows the 404 for a business with no draft', async () => {
    const client = clientCapturing(jsonResponse(404, envelope('not_found')));
    const result = await client.storefront.preview(BID);
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(404);
      expect(result.envelope?.error.code).toBe('not_found');
    }
  });

  it('narrows the staff 403 envelope', async () => {
    const client = clientCapturing(
      jsonResponse(403, envelope('permission_denied')),
    );
    const result = await client.storefront.preview(BID);
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.status).toBe(403);
      expect(result.envelope?.error.code).toBe('permission_denied');
    }
  });

  it('surfaces a network failure as a null-status result', async () => {
    const client = createApiClient({
      baseUrl: BASE_URL,
      fetch: () => Promise.reject(new Error('offline')),
    });
    const result = await client.storefront.preview(BID);
    expect(result).toEqual({ ok: false, status: null, envelope: null });
  });
});
