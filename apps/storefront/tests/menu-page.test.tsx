import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, test, vi } from 'vitest';

import MenuPage from '../app/menu/page';
import { menuSectionData } from '../lib/server/page-data';
import {
  getPublicMenu,
  getPublishedStorefront,
} from '../lib/server/storefront-data';
import {
  menuItemFixture,
  publicMenuFixture,
  storefrontFixture,
} from './fixtures';

vi.mock('../lib/server/storefront-data', () => ({
  getPublishedStorefront: vi.fn(),
  getPublicMenu: vi.fn(),
}));

const NOT_FOUND = new Error('NEXT_NOT_FOUND_SENTINEL');
vi.mock('next/navigation', () => ({
  notFound: () => {
    throw NOT_FOUND;
  },
}));

const mockStorefront = vi.mocked(getPublishedStorefront);
const mockMenu = vi.mocked(getPublicMenu);

beforeEach(() => {
  mockStorefront.mockReset();
  mockMenu.mockReset();
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
