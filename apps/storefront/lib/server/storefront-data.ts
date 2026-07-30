// Server data access for the public storefront (ADR-021).
//
// The single boundary through which pages and metadata read the backend.
// Tenancy: the incoming request's Host is forwarded verbatim through the
// tenant transport; nothing here parses a slug, reads a query parameter,
// or accepts a tenant identifier — the backend is the only resolver
// (ADR-013). Every backend outcome collapses into three render states:
//
//   ok          → the typed payload;
//   not-found   → the backend's neutral 404 (unknown host, unpublished,
//                 suspended, … — indistinguishable by design), rendered as
//                 the one neutral storefront 404;
//   unavailable → timeout, network failure, or any non-404 error, rendered
//                 as the one generic server-error experience.
//
// `React.cache` memoizes per server request (per the React contract its
// store lives for exactly one request), so the page body and
// `generateMetadata` share one backend read instead of two. The cached
// functions take no arguments and re-derive the Host from the request
// context, so a memoized value structurally cannot be keyed across
// requests or tenants. The uncached loaders are exported for tests.

import { cache } from 'react';
import { headers } from 'next/headers';

import {
  createApiClient,
  type ApiResult,
  type PublicMenu,
} from '@restaurant-engine/api-client';

import type { PublicStorefront } from '../contract';
import { resolveApiOrigin } from './api-origin';
import { createTenantFetch } from './tenant-fetch';

export type StorefrontResult<T> =
  { kind: 'ok'; data: T } | { kind: 'not-found' } | { kind: 'unavailable' };

function toStorefrontResult<T>(result: ApiResult<T>): StorefrontResult<T> {
  if (result.ok) {
    return { kind: 'ok', data: result.data };
  }
  if (result.status === 404) {
    return { kind: 'not-found' };
  }
  return { kind: 'unavailable' };
}

function clientForHost(host: string) {
  return createApiClient({
    baseUrl: resolveApiOrigin(),
    fetch: createTenantFetch(host),
  });
}

async function requestHost(): Promise<string | null> {
  const requestHeaders = await headers();
  const host = requestHeaders.get('host');
  return host === null || host === '' ? null : host;
}

/** Uncached loader (exported for tests): one backend read for one host. */
export async function loadPublishedStorefront(
  host: string | null,
): Promise<StorefrontResult<PublicStorefront>> {
  if (host === null) {
    // Nothing could ever resolve without a Host; skip the backend and
    // fail closed to the same neutral not-found.
    return { kind: 'not-found' };
  }
  return toStorefrontResult(await clientForHost(host).public.getStorefront());
}

/** Uncached loader (exported for tests): the public menu for one host. */
export async function loadPublicMenu(
  host: string | null,
): Promise<StorefrontResult<PublicMenu>> {
  if (host === null) {
    return { kind: 'not-found' };
  }
  return toStorefrontResult(await clientForHost(host).public.getMenu());
}

export const getPublishedStorefront = cache(
  async (): Promise<StorefrontResult<PublicStorefront>> =>
    loadPublishedStorefront(await requestHost()),
);

export const getPublicMenu = cache(
  async (): Promise<StorefrontResult<PublicMenu>> =>
    loadPublicMenu(await requestHost()),
);

/** The incoming request Host, for canonical-URL construction (cached). */
export const getRequestHost = cache(requestHost);
