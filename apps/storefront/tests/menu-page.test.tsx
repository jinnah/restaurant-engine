import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, test, vi } from 'vitest';

import MenuPage from '../app/menu/page';
import { menuSectionData } from '../lib/server/page-data';
import {
  getPublicAvailability,
  getPublicMenu,
  getPublishedStorefront,
} from '../lib/server/storefront-data';
import {
  hoursDataFixture,
  menuItemFixture,
  publicMenuFixture,
  storefrontFixture,
} from '@restaurant-engine/storefront-renderer/fixtures';
import type { PublicAvailability } from '@restaurant-engine/api-client';

vi.mock('../lib/server/storefront-data', () => ({
  getPublishedStorefront: vi.fn(),
  getPublicMenu: vi.fn(),
  getPublicAvailability: vi.fn(),
}));

const NOT_FOUND = new Error('NEXT_NOT_FOUND_SENTINEL');
vi.mock('next/navigation', () => ({
  notFound: () => {
    throw NOT_FOUND;
  },
}));

const mockStorefront = vi.mocked(getPublishedStorefront);
const mockMenu = vi.mocked(getPublicMenu);
const mockAvailability = vi.mocked(getPublicAvailability);

/** The availability projection with the D12 gate in a chosen position. */
function availabilityFixture(orderingEnabled: boolean): PublicAvailability {
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
      asap_enabled: true,
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
  mockMenu.mockReset();
  mockAvailability.mockReset();
  // The M6C ordering gate rides the availability projection (D12);
  // individual tests flip it where the gate is the subject.
  mockAvailability.mockResolvedValue({
    kind: 'ok',
    data: availabilityFixture(false),
  });
});

describe('the menu page', () => {
  test('renders the complete menu under the tenant chrome', async () => {
    mockStorefront.mockResolvedValue({
      kind: 'ok',
      data: storefrontFixture([]),
    });
    mockMenu.mockResolvedValue({ kind: 'ok', data: publicMenuFixture() });
    render(await MenuPage());
    expect(
      screen.getByRole('heading', { level: 1, name: 'Corner Kitchen' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { level: 2, name: 'Menu' }),
    ).toBeInTheDocument();
    expect(
      screen.getAllByRole('heading', { level: 3 }).map((h) => h.textContent),
    ).toEqual(['Mains', 'Drinks']);
  });

  test('a business without a published storefront has no menu page', async () => {
    mockStorefront.mockResolvedValue({ kind: 'not-found' });
    await expect(MenuPage()).rejects.toBe(NOT_FOUND);
    // The gate fails before the menu is ever requested.
    expect(mockMenu).not.toHaveBeenCalled();
  });

  test('a menu that goes ineligible mid-request is the same neutral 404', async () => {
    mockStorefront.mockResolvedValue({
      kind: 'ok',
      data: storefrontFixture([]),
    });
    mockMenu.mockResolvedValue({ kind: 'not-found' });
    await expect(MenuPage()).rejects.toBe(NOT_FOUND);
  });

  test('an unavailable menu backend throws to the error boundary', async () => {
    mockStorefront.mockResolvedValue({
      kind: 'ok',
      data: storefrontFixture([]),
    });
    mockMenu.mockResolvedValue({ kind: 'unavailable' });
    await expect(MenuPage()).rejects.toThrow(/unavailable/);
  });

  test('ordering off renders no ordering affordance at all', async () => {
    mockStorefront.mockResolvedValue({
      kind: 'ok',
      data: storefrontFixture([]),
    });
    mockMenu.mockResolvedValue({ kind: 'ok', data: publicMenuFixture() });
    render(await MenuPage());
    expect(
      screen.queryByRole('button', { name: /add to order/i }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /view order/i })).toBeNull();
  });

  test('ordering on adds the affordance to orderable items only', async () => {
    mockStorefront.mockResolvedValue({
      kind: 'ok',
      data: storefrontFixture([]),
    });
    mockAvailability.mockResolvedValue({
      kind: 'ok',
      data: availabilityFixture(true),
    });
    const orderable = menuItemFixture();
    const notOrderable = menuItemFixture({
      id: '00000000-0000-0000-0000-00000000f102',
      name: 'Unsatisfiable special',
      is_orderable: false,
    });
    mockMenu.mockResolvedValue({
      kind: 'ok',
      data: publicMenuFixture({
        categories: [
          {
            id: 'c1',
            name: 'Mains',
            description: null,
            items: [orderable, notOrderable],
          },
        ],
        featured_item_ids: [],
      }),
    });
    render(await MenuPage());
    // Exactly one affordance: the orderable item's. `is_orderable`
    // finally renders — as the gate on the affordance (ADR-026).
    expect(
      screen.getAllByRole('button', { name: /add to order/i }),
    ).toHaveLength(1);
  });

  test('the availability read gates like every other backend read', async () => {
    mockStorefront.mockResolvedValue({
      kind: 'ok',
      data: storefrontFixture([]),
    });
    mockMenu.mockResolvedValue({ kind: 'ok', data: publicMenuFixture() });
    mockAvailability.mockResolvedValue({ kind: 'unavailable' });
    await expect(MenuPage()).rejects.toThrow(/unavailable/);
  });
});

describe('menuSectionData', () => {
  test('resolves featured items by id in the projection order', () => {
    const menu = publicMenuFixture({
      featured_item_ids: [
        '00000000-0000-0000-0000-000000000103',
        '00000000-0000-0000-0000-000000000101',
        'ffffffff-ffff-ffff-ffff-ffffffffffff',
      ],
    });
    const data = menuSectionData(menu);
    expect(data.currency).toBe('USD');
    expect(data.featured.map((item) => item.name)).toEqual([
      'Fresh lemonade',
      'House roast chicken',
    ]);
  });

  test('an unknown featured id degrades by omission', () => {
    const menu = publicMenuFixture({
      featured_item_ids: ['ffffffff-ffff-ffff-ffff-ffffffffffff'],
    });
    expect(menuSectionData(menu).featured).toEqual([]);
  });

  test('duplicate items across categories resolve to canonical entries', () => {
    const item = menuItemFixture();
    const menu = publicMenuFixture({
      categories: [{ id: 'c1', name: 'A', description: null, items: [item] }],
      featured_item_ids: [item.id],
    });
    expect(menuSectionData(menu).featured).toEqual([item]);
  });
});
