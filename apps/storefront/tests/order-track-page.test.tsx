// The tracking route's server shell (M6C, ADR-026): gated only on the
// published storefront chrome — deliberately NOT on the ordering
// entitlement (D10 as amended: an order already placed stays trackable
// after revocation, and this page never reads availability at all). The
// island is stubbed; the token must reach it verbatim.

import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, test, vi } from 'vitest';

import TrackPage from '../app/order/track/[token]/page';
import {
  getPublicAvailability,
  getPublishedStorefront,
} from '../lib/server/storefront-data';
import { storefrontFixture } from '@restaurant-engine/storefront-renderer/fixtures';

vi.mock('../lib/server/storefront-data', () => ({
  getPublishedStorefront: vi.fn(),
  getPublicAvailability: vi.fn(),
}));

vi.mock('../components/ordering/OrderTracker', () => ({
  OrderTracker: (props: { token: string }) => (
    <div data-testid="tracker-island">{props.token}</div>
  ),
}));

const NOT_FOUND = new Error('NEXT_NOT_FOUND_SENTINEL');
vi.mock('next/navigation', () => ({
  notFound: () => {
    throw NOT_FOUND;
  },
}));

const mockStorefront = vi.mocked(getPublishedStorefront);
const mockAvailability = vi.mocked(getPublicAvailability);

beforeEach(() => {
  mockStorefront.mockReset();
  mockAvailability.mockReset();
});

describe('the /order/track/[token] page', () => {
  test('renders the tracker island with the path token', async () => {
    mockStorefront.mockResolvedValue({
      kind: 'ok',
      data: storefrontFixture([]),
    });
    render(await TrackPage({ params: Promise.resolve({ token: 'tok-123' }) }));
    expect(screen.getByTestId('tracker-island').textContent).toBe('tok-123');
    // The D10 amendment made structural: this shell never reads the
    // availability projection, so no entitlement fact can gate it.
    expect(mockAvailability).not.toHaveBeenCalled();
  });

  test('no published storefront: the one neutral 404', async () => {
    mockStorefront.mockResolvedValue({ kind: 'not-found' });
    await expect(
      TrackPage({ params: Promise.resolve({ token: 'tok-123' }) }),
    ).rejects.toBe(NOT_FOUND);
  });
});
