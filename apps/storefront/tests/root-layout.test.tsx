// @vitest-environment node

// The root layout is where the tenant-page theme is applied (M4G-B,
// ADR-024 §5): `<body>` carries `tenantPageClass`, and the browser paints
// the canvas from `<body>`'s background, so the theme's custom properties
// must be set there rather than on a descendant.
//
// Two contracts matter and are asserted here rather than trusted:
//
//  1. the layout uses the NON-THROWING cached result, so the neutral 404
//     and the generic error document still render (a `notFound()` from
//     the layout would break both); and
//  2. exactly one loader call is made, and it is the same argument-less
//     `React.cache` loader the page body and `generateMetadata` already
//     call — deduplication, not a third backend request. The built-server
//     verification proves the request count on the wire.
//
// The element tree is inspected directly rather than rendered: `<html>`
// and `<body>` cannot be mounted inside a jsdom container without DOM
// nesting warnings, and the contract here is what the layout returns.

import type { ReactElement } from 'react';
import { beforeEach, describe, expect, test, vi } from 'vitest';

import RootLayout from '../app/layout';
import { getPublishedStorefront } from '../lib/server/storefront-data';
import {
  storefrontFixture,
  themeFixture,
} from '@restaurant-engine/storefront-renderer/fixtures';

vi.mock('../lib/server/storefront-data', () => ({
  getPublishedStorefront: vi.fn(),
}));

const mockStorefront = vi.mocked(getPublishedStorefront);

beforeEach(() => {
  mockStorefront.mockReset();
});

interface BodyProps {
  className?: string;
  style?: Record<string, string>;
}

async function renderBody(): Promise<BodyProps> {
  const html = (await RootLayout({ children: null })) as ReactElement<{
    children: ReactElement<BodyProps>;
  }>;
  return html.props.children.props;
}

describe('the root layout', () => {
  test('applies the whole theme to the tenant-page element', async () => {
    mockStorefront.mockResolvedValue({
      kind: 'ok',
      data: storefrontFixture([], {
        theme: themeFixture({
          accent: '#112244',
          palette: 'midnight',
          type_pairing: 'serif_display',
        }),
      }),
    });
    const body = await renderBody();
    expect(body.className).toBeTruthy();
    // The palette reaches the canvas-painting element itself.
    expect(body.style?.['--color-bg']).toBe('#14171c');
    expect(body.style?.['--color-text']).toBe('#f2f4f7');
    expect(body.style?.['--accent']).toBe('#112244');
    expect(body.style?.['--font-heading']).toContain('ui-serif');
  });

  test('the neutral not-found document renders unthemed', async () => {
    mockStorefront.mockResolvedValue({ kind: 'not-found' });
    const body = await renderBody();
    // No theme, no throw: the 404 is a platform page, not a tenant page,
    // and it must still render (ADR-021 §2).
    expect(body.style).toBeUndefined();
    expect(body.className).toBeTruthy();
  });

  test('the generic error document renders unthemed', async () => {
    mockStorefront.mockResolvedValue({ kind: 'unavailable' });
    const body = await renderBody();
    expect(body.style).toBeUndefined();
  });

  test('reads the shared cached loader exactly once per render', async () => {
    mockStorefront.mockResolvedValue({
      kind: 'ok',
      data: storefrontFixture([]),
    });
    await renderBody();
    expect(mockStorefront).toHaveBeenCalledTimes(1);
    // Argument-less: the host is re-derived inside the cached loader, so
    // a memoized value cannot be keyed across requests or tenants
    // (ADR-021 §3) and the page body's call deduplicates against this one.
    expect(mockStorefront).toHaveBeenCalledWith();
  });
});
