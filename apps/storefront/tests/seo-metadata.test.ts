// @vitest-environment node

// Published-data-only metadata and the per-host robots/sitemap routes
// (ADR-021). The data boundary is mocked; what is under test is exactly
// what these surfaces claim — and, more importantly, what they never
// claim (no tenant facts on ineligible hosts, no draft anything).

import { beforeEach, describe, expect, test, vi } from 'vitest';

import { GET as robotsGet } from '../app/robots.txt/route';
import { GET as sitemapGet } from '../app/sitemap.xml/route';
import { storefrontMetadata } from '../lib/server/page-metadata';
import {
  getPublishedStorefront,
  getRequestHost,
} from '../lib/server/storefront-data';
import {
  heroSection,
  storefrontFixture,
} from '@restaurant-engine/storefront-renderer/fixtures';

vi.mock('../lib/server/storefront-data', () => ({
  getPublishedStorefront: vi.fn(),
  getPublicMenu: vi.fn(),
  getRequestHost: vi.fn(),
}));

const mockStorefront = vi.mocked(getPublishedStorefront);
const mockHost = vi.mocked(getRequestHost);

beforeEach(() => {
  mockStorefront.mockReset();
  mockHost.mockReset();
  mockHost.mockResolvedValue('corner-kitchen.example.com');
});

describe('storefrontMetadata', () => {
  test('home metadata derives from published data and the canonical origin', async () => {
    mockStorefront.mockResolvedValue({
      kind: 'ok',
      data: storefrontFixture([heroSection()]),
    });
    const metadata = await storefrontMetadata('home');
    expect(metadata.title).toBe('Corner Kitchen');
    expect(metadata.description).toBe('Family recipes, cooked to order');
    expect(metadata.metadataBase).toBeInstanceOf(URL);
    expect(String(metadata.metadataBase)).toBe(
      'https://corner-kitchen.example.com/',
    );
    expect(metadata.alternates?.canonical).toBe('/');
    expect(metadata.openGraph).toMatchObject({
      title: 'Corner Kitchen',
      siteName: 'Corner Kitchen',
      type: 'website',
    });
    const images = metadata.openGraph?.images as { url: string }[];
    expect(images[0]?.url).toBe(
      '/api/v1/public/media/00000000-0000-0000-0000-00000000aaaa/w1280',
    );
  });

  test('menu metadata is titled from the business with its own canonical', async () => {
    mockStorefront.mockResolvedValue({
      kind: 'ok',
      data: storefrontFixture([]),
    });
    const metadata = await storefrontMetadata('menu');
    expect(metadata.title).toBe('Menu — Corner Kitchen');
    expect(metadata.alternates?.canonical).toBe('/menu');
    expect(metadata.description).toBeUndefined();
  });

  test('a hero without a subheading yields no description (never fabricated)', async () => {
    mockStorefront.mockResolvedValue({
      kind: 'ok',
      data: storefrontFixture([heroSection({ subheading: null })]),
    });
    const metadata = await storefrontMetadata('home');
    expect(metadata.description).toBeUndefined();
  });

  test('ineligible and failed reads produce empty metadata — no tenant facts', async () => {
    mockStorefront.mockResolvedValue({ kind: 'not-found' });
    expect(await storefrontMetadata('home')).toEqual({});
    mockStorefront.mockResolvedValue({ kind: 'unavailable' });
    expect(await storefrontMetadata('home')).toEqual({});
  });
});

describe('robots.txt', () => {
  test('a published host allows indexing and advertises its sitemap', async () => {
    mockStorefront.mockResolvedValue({
      kind: 'ok',
      data: storefrontFixture([]),
    });
    const response = await robotsGet();
    expect(response.status).toBe(200);
    expect(response.headers.get('cache-control')).toBe('no-store');
    expect(await response.text()).toBe(
      'User-agent: *\nAllow: /\n\nSitemap: https://corner-kitchen.example.com/sitemap.xml\n',
    );
  });

  test('an unresolved host disallows everything, neutrally', async () => {
    mockStorefront.mockResolvedValue({ kind: 'not-found' });
    const response = await robotsGet();
    expect(response.status).toBe(200);
    expect(await response.text()).toBe('User-agent: *\nDisallow: /\n');
  });

  test('a backend outage answers 503 so crawlers retry', async () => {
    mockStorefront.mockResolvedValue({ kind: 'unavailable' });
    const response = await robotsGet();
    expect(response.status).toBe(503);
  });
});

describe('sitemap.xml', () => {
  test('lists exactly the routes that exist, absolute on the canonical origin', async () => {
    mockStorefront.mockResolvedValue({
      kind: 'ok',
      data: storefrontFixture([]),
    });
    const response = await sitemapGet();
    expect(response.status).toBe(200);
    const body = await response.text();
    expect(body).toContain(
      '<url><loc>https://corner-kitchen.example.com/</loc></url>',
    );
    expect(body).toContain(
      '<url><loc>https://corner-kitchen.example.com/menu</loc></url>',
    );
    // Only routes that exist (ADR-020 §1): no /order, /about, /contact.
    expect(body).not.toMatch(/\/order|\/about|\/contact/);
    expect((body.match(/<url>/g) ?? []).length).toBe(2);
  });

  test('an unresolved host has no sitemap: neutral 404', async () => {
    mockStorefront.mockResolvedValue({ kind: 'not-found' });
    const response = await sitemapGet();
    expect(response.status).toBe(404);
    expect(response.headers.get('cache-control')).toBe('no-store');
  });

  test('a backend outage answers 503', async () => {
    mockStorefront.mockResolvedValue({ kind: 'unavailable' });
    expect((await sitemapGet()).status).toBe(503);
  });
});
