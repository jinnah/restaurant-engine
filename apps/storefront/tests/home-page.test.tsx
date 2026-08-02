import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, test, vi } from 'vitest';

import HomePage from '../app/page';
import {
  getPublicAvailability,
  getPublicMenu,
  getPublishedStorefront,
} from '../lib/server/storefront-data';
import {
  heroSection,
  hoursDataFixture,
  hoursSection,
  menuSection,
  publicMenuFixture,
  storefrontFixture,
  storySection,
} from '@restaurant-engine/storefront-renderer/fixtures';
import type { PublicAvailability } from '@restaurant-engine/api-client';

vi.mock('../lib/server/storefront-data', () => ({
  getPublishedStorefront: vi.fn(),
  getPublicMenu: vi.fn(),
  getPublicAvailability: vi.fn(),
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
const mockAvailability = vi.mocked(getPublicAvailability);

/** The availability projection shape over the hours-data fixture. */
function availabilityFixture(): PublicAvailability {
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
    pickup: { enabled: true, asap_enabled: true, next_pickup_at: null },
  };
}

beforeEach(() => {
  mockStorefront.mockReset();
  mockMenu.mockReset();
  mockAvailability.mockReset();
  // Every render of the home page reads the availability projection
  // (M5D): the JSON-LD models hours whether or not an hours section is
  // composed. Individual tests override where the projection matters.
  mockAvailability.mockResolvedValue({
    kind: 'ok',
    data: availabilityFixture(),
  });
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
    // The availability projection is always read (JSON-LD models hours).
    expect(mockAvailability).toHaveBeenCalledTimes(1);
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

  test('an hours section composes the availability projection', async () => {
    mockStorefront.mockResolvedValue({
      kind: 'ok',
      data: storefrontFixture([hoursSection()]),
    });
    render(await HomePage());
    expect(mockAvailability).toHaveBeenCalledTimes(1);
    expect(screen.getByText('Open now')).toBeInTheDocument();
    // The fixture's closing instant formatted in the TENANT zone.
    expect(screen.getByText(/closes 9:00 PM/)).toBeInTheDocument();
    expect(screen.getByText('5:00 PM – 2:00 AM')).toBeInTheDocument();
    expect(screen.getByText('December 25, 2026')).toBeInTheDocument();
  });

  test('the neutral backend 404 becomes the framework not-found', async () => {
    mockStorefront.mockResolvedValue({ kind: 'not-found' });
    await expect(HomePage()).rejects.toBe(NOT_FOUND);
  });

  test('an unavailable backend throws to the generic error boundary', async () => {
    mockStorefront.mockResolvedValue({ kind: 'unavailable' });
    await expect(HomePage()).rejects.toThrow(/unavailable/);
  });

  test('an unavailable availability projection is the generic error too', async () => {
    // The third read is load-bearing (JSON-LD hours): its failure is the
    // same generic error experience as the other two, never a partial
    // page silently missing the schedule.
    mockStorefront.mockResolvedValue({
      kind: 'ok',
      data: storefrontFixture([hoursSection()]),
    });
    mockAvailability.mockResolvedValue({ kind: 'unavailable' });
    await expect(HomePage()).rejects.toThrow(/unavailable/);
  });
});
