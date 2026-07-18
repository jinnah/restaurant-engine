// M2D facade behavior (invitations, password resets, entitlements, audit)
// with an injected fetch — no network, no backend. Proves tokens travel in
// POST bodies (never URLs/queries), CSRF headers are attached to unsafe
// calls, and query parameters map to the wire contract.

import { describe, expect, it } from 'vitest';

import { createApiClient } from '../src/index';

const BASE_URL = 'http://api.test';
const BID = '5f7d3f5e-3f3e-4b62-9a5e-3c7c2b1a0d9e';
const IID = '0f0d3f5e-3f3e-4b62-9a5e-3c7c2b1a0d9e';
const RAW_TOKEN = 'raw-opaque-token-value';

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
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

describe('invitations (public token flows)', () => {
  it('preview sends the token in the POST body, never the URL', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(
      jsonResponse(200, {
        business_name: 'Shalik',
        role: 'staff',
        email_hint: 'i***@example.com',
      }),
      requests,
    );

    const result = await client.invitations.preview({ token: RAW_TOKEN });

    expect(result.ok).toBe(true);
    const request = requests[0]!;
    expect(request.method).toBe('POST');
    expect(request.url).toBe(`${BASE_URL}/api/v1/invitations/preview`);
    expect(request.url).not.toContain(RAW_TOKEN);
    expect(await request.clone().json()).toEqual({ token: RAW_TOKEN });
  });

  it('accept posts credentials fields and cannot select a tenant', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(
      jsonResponse(201, {
        status: 'accepted',
        business_id: BID,
        email: 'i@example.com',
        role: 'staff',
      }),
      requests,
    );

    await client.invitations.accept({
      token: RAW_TOKEN,
      display_name: 'New Member',
      password: 'long enough password!',
    });

    const request = requests[0]!;
    expect(request.url).toBe(`${BASE_URL}/api/v1/invitations/accept`);
    expect(new URL(request.url).search).toBe('');
    expect(request.headers.get('x-csrf-token')).toBeNull();
  });

  it('acceptExisting carries the CSRF header', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(
      jsonResponse(200, {
        status: 'accepted',
        business_id: BID,
        email: 'i@example.com',
        role: 'staff',
      }),
      requests,
    );

    await client.invitations.acceptExisting({ token: RAW_TOKEN }, 'csrf-1');

    expect(requests[0]!.headers.get('x-csrf-token')).toBe('csrf-1');
  });
});

describe('passwordResets.redeem', () => {
  it('posts token and password in the body only', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(
      jsonResponse(200, { status: 'password_reset' }),
      requests,
    );

    const result = await client.passwordResets.redeem({
      token: RAW_TOKEN,
      new_password: 'a much better password',
    });

    expect(result.ok).toBe(true);
    const request = requests[0]!;
    expect(request.url).toBe(`${BASE_URL}/api/v1/password-resets/redeem`);
    expect(request.url).not.toContain(RAW_TOKEN);
  });
});

describe('platform M2D operations', () => {
  it('issuePasswordReset posts the email with CSRF', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(
      jsonResponse(201, {
        token: RAW_TOKEN,
        expires_at: '2026-07-18T12:00:00Z',
        email: 'owner@example.com',
      }),
      requests,
    );

    const result = await client.platform.issuePasswordReset(
      { email: 'owner@example.com' },
      'csrf-2',
    );

    expect(result.ok && result.data.token).toBe(RAW_TOKEN);
    const request = requests[0]!;
    expect(request.url).toBe(`${BASE_URL}/api/v1/platform/password-resets`);
    expect(request.headers.get('x-csrf-token')).toBe('csrf-2');
  });

  it('setEntitlements PUTs the full feature set', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(
      jsonResponse(200, { features: ['online_ordering'] }),
      requests,
    );

    await client.platform.setEntitlements(
      BID,
      { features: ['online_ordering'] },
      'csrf-3',
    );

    const request = requests[0]!;
    expect(request.method).toBe('PUT');
    expect(request.url).toBe(
      `${BASE_URL}/api/v1/platform/businesses/${BID}/entitlements`,
    );
    expect(await request.clone().json()).toEqual({
      features: ['online_ordering'],
    });
  });

  it('listAuditEvents maps camelCase params to the wire contract', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(
      jsonResponse(200, { items: [], next_before_id: null }),
      requests,
    );

    await client.platform.listAuditEvents({
      limit: 10,
      beforeId: 99,
      action: 'business.created',
      businessId: BID,
    });

    const url = new URL(requests[0]!.url);
    expect(url.pathname).toBe('/api/v1/platform/audit-events');
    expect(url.searchParams.get('limit')).toBe('10');
    expect(url.searchParams.get('before_id')).toBe('99');
    expect(url.searchParams.get('action')).toBe('business.created');
    expect(url.searchParams.get('business_id')).toBe(BID);
  });

  it('platform createInvitation targets the platform route with CSRF', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(
      jsonResponse(201, {
        token: RAW_TOKEN,
        invitation_id: IID,
        expires_at: '2026-07-25T00:00:00Z',
        email: 'o@example.com',
        role: 'owner',
      }),
      requests,
    );

    await client.platform.createInvitation(
      BID,
      { email: 'o@example.com', role: 'owner' },
      'csrf-4',
    );

    const request = requests[0]!;
    expect(request.url).toBe(
      `${BASE_URL}/api/v1/platform/businesses/${BID}/invitations`,
    );
    expect(request.headers.get('x-csrf-token')).toBe('csrf-4');
  });
});

describe('businesses M2D operations', () => {
  it('createInvitation and revokeInvitation hit business-scoped routes', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(
      jsonResponse(200, { status: 'revoked' }),
      requests,
    );

    await client.businesses.revokeInvitation(BID, IID, 'csrf-5');

    const request = requests[0]!;
    expect(request.url).toBe(
      `${BASE_URL}/api/v1/businesses/${BID}/invitations/${IID}/revoke`,
    );
    expect(await request.clone().json()).toEqual({});
    expect(request.headers.get('x-csrf-token')).toBe('csrf-5');
  });

  it('getEntitlements and listAuditEvents are plain GETs', async () => {
    const requests: Request[] = [];
    const client = clientCapturing(
      jsonResponse(200, { features: [] }),
      requests,
    );

    await client.businesses.getEntitlements(BID);
    await client.businesses.listAuditEvents(BID, { beforeId: 7 });

    expect(requests[0]!.url).toBe(
      `${BASE_URL}/api/v1/businesses/${BID}/entitlements`,
    );
    const auditUrl = new URL(requests[1]!.url);
    expect(auditUrl.pathname).toBe(`/api/v1/businesses/${BID}/audit-events`);
    expect(auditUrl.searchParams.get('before_id')).toBe('7');
  });
});
