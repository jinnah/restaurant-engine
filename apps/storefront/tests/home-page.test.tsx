import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, test, vi } from 'vitest';

import HomePage from '../app/page';
import {
  getPublicMenu,
  getPublishedStorefront,
} from '../lib/server/storefront-data';
import {
  heroSection,
  menuSection,
  publicMenuFixture,
  storefrontFixture,
  storySection,
} from '@restaurant-engine/storefront-renderer/fixtures';

vi.mock('../lib/server/storefront-data', () => ({
  getPublishedStorefront: vi.fn(),
  getPublicMenu: vi.fn(),
  getRequestHost: vi.fn(async () => 'corner-kitchen.example.com'),
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

describe('the home page', () => {
  test('renders the published composition through the variant layout', async () => {
    mockStorefront.mockResolvedValue({
      kind: 'ok',
      data: storefrontFixture([heroSection(), storySection()]),
    });
    render(await HomePage());
    expect(
      screen.getByRole('heading', { level: 1, name: 'Corner Kitchen' }),
    ).toBeInTheDocument();
    const sectionHeadings = screen.getAllByRole('heading', { level: 2 });
    expect(sectionHeadings.map((h) => h.textContent)).toEqual([
      'Neighborhood kitchen, open late',
      'Our story',
    ]);
    // No menu section published — the menu projection is never requested.
    expect(mockMenu).not.toHaveBeenCalled();
  });

  test('a menu section composes featured items from the public menu', async () => {
    mockStorefront.mockResolvedValue({
      kind: 'ok',
      data: storefrontFixture([menuSection()]),
    });
    mockMenu.mockResolvedValue({ kind: 'ok', data: publicMenuFixture() });
    render(await HomePage());
    expect(mockMenu).toHaveBeenCalledTimes(1);
    expect(screen.getByText('House roast chicken')).toBeInTheDocument();
    expect(screen.getByText('$12.50')).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: /view the full menu/i }),
    ).toHaveAttribute('href', '/menu');
  });

  test('the neutral backend 404 becomes the framework not-found', async () => {
    mockStorefront.mockResolvedValue({ kind: 'not-found' });
    await expect(HomePage()).rejects.toBe(NOT_FOUND);
  });

  test('an unavailable backend throws to the generic error boundary', async () => {
    mockStorefront.mockResolvedValue({ kind: 'unavailable' });
    await expect(HomePage()).rejects.toThrow(/unavailable/);
  });
});
