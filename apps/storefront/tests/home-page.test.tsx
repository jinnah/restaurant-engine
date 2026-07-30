import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, test, vi } from 'vitest';

import HomePage from '../app/page';
import { getPublishedStorefront } from '../lib/server/storefront-data';
import { heroSection, storefrontFixture, storySection } from './fixtures';

vi.mock('../lib/server/storefront-data', () => ({
  getPublishedStorefront: vi.fn(),
}));

const NOT_FOUND = new Error('NEXT_NOT_FOUND_SENTINEL');
vi.mock('next/navigation', () => ({
  notFound: () => {
    throw NOT_FOUND;
  },
}));

const mockData = vi.mocked(getPublishedStorefront);

beforeEach(() => {
  mockData.mockReset();
});

describe('the home page', () => {
  test('renders the published composition through the variant layout', async () => {
    mockData.mockResolvedValue({
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
  });

  test('the neutral backend 404 becomes the framework not-found', async () => {
    mockData.mockResolvedValue({ kind: 'not-found' });
    await expect(HomePage()).rejects.toBe(NOT_FOUND);
  });

  test('an unavailable backend throws to the generic error boundary', async () => {
    mockData.mockResolvedValue({ kind: 'unavailable' });
    await expect(HomePage()).rejects.toThrow(/unavailable/);
  });
});
