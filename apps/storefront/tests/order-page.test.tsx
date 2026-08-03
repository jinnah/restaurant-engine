// The checkout route's server shell (M6C, ADR-026): the D10 gate — a
// storefront without ordering has no /order page, answered with the one
// neutral 404 — and the tenant facts the island receives. The island
// itself is stubbed; its behavior has its own suite.

import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, test, vi } from 'vitest';

import OrderPage from '../app/order/page';
import {
  getPublicAvailability,
  getPublishedStorefront,
} from '../lib/server/storefront-data';
import {
  hoursDataFixture,
  storefrontFixture,
} from '@restaurant-engine/storefront-renderer/fixtures';
import type { PublicAvailability } from '@restaurant-engine/api-client';

vi.mock('../lib/server/storefront-data', () => ({
  getPublishedStorefront: vi.fn(),
  getPublicAvailability: vi.fn(),
}));

vi.mock('../components/ordering/CheckoutForm', () => ({
  CheckoutForm: (props: {
    currency: string;
    timezone: string;
    asapEnabled: boolean;
  }) => (
    <div data-testid="checkout-island">
      {props.currency}|{props.timezone}|{String(props.asapEnabled)}
    </div>
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

function availabilityFixture(
  orderingEnabled: boolean,
  asapEnabled = true,
): PublicAvailability {
  const data = hoursDataFixture();
  return {
    business: {
      name: 'Corner Kitchen',
      slug: 'corner-kitchen',
      timezone: data.timezone,
      currency: 'USD',
    },
    is_open_now: data.is_open_now,
    closes_at: data.closes_at,
    next_opens_at: data.next_opens_at,
    weekly: data.weekly,
    exceptions: data.exceptions,
    pickup: {
      enabled: true,
      asap_enabled: asapEnabled,
      next_pickup_at: null,
      ordering_enabled: orderingEnabled,
      ordering_paused: false,
      pause_note: null,
      pause_resumes_at: null,
    },
  };
}

beforeEach(() => {
  mockStorefront.mockReset();
  mockAvailability.mockReset();
  mockStorefront.mockResolvedValue({
    kind: 'ok',
    data: storefrontFixture([]),
  });
});

describe('the /order page', () => {
  test('renders checkout with the tenant facts when the gate is on', async () => {
    mockAvailability.mockResolvedValue({
      kind: 'ok',
      data: availabilityFixture(true),
    });
    render(await OrderPage());
    expect(screen.getByTestId('checkout-island').textContent).toBe(
      'USD|America/New_York|true',
    );
  });

  test('ordering off is the one neutral 404 (D10)', async () => {
    mockAvailability.mockResolvedValue({
      kind: 'ok',
      data: availabilityFixture(false),
    });
    await expect(OrderPage()).rejects.toBe(NOT_FOUND);
  });

  test('no published storefront: the same neutral 404 before anything else', async () => {
    mockStorefront.mockResolvedValue({ kind: 'not-found' });
    await expect(OrderPage()).rejects.toBe(NOT_FOUND);
  });

  test('an unavailable backend throws to the error boundary', async () => {
    mockAvailability.mockResolvedValue({ kind: 'unavailable' });
    await expect(OrderPage()).rejects.toThrow(/unavailable/);
  });

  test('asap disabled reaches the island as a fact, not a default', async () => {
    mockAvailability.mockResolvedValue({
      kind: 'ok',
      data: availabilityFixture(true, false),
    });
    render(await OrderPage());
    expect(screen.getByTestId('checkout-island').textContent).toBe(
      'USD|America/New_York|false',
    );
  });
});
