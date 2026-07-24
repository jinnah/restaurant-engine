// The menu overview read experience (M3E): the management view shows hidden
// entries, states are words rather than colours, and prices come from the
// Business's currency.

import { fireEvent, screen } from '@testing-library/react';
import { expect, test, vi } from 'vitest';
import {
  adminMenu,
  business,
  category,
  item,
  makeClient,
  ok,
  sessionView,
} from './support/mockClient';
import { renderApp } from './support/render';
import { thumbnailVariant } from '../src/menu/components/ItemRow';

const SHALIK = '5f0d2c9a-7f5e-4c1b-9a37-0b8a52a9c001';
const MENU = `/businesses/${SHALIK}/menu`;

function clientWith(
  categories: Parameters<typeof adminMenu>[0],
  currency = 'USD',
  overrides: Parameters<typeof makeClient>[0] = {},
) {
  return makeClient({
    auth: { getSession: vi.fn(async () => ok(sessionView())) },
    businesses: {
      get: vi.fn(async () => ok(business({ id: SHALIK, currency }))),
    },
    catalog: { getMenu: vi.fn(async () => ok(adminMenu(categories))) },
    ...overrides,
  });
}

test('categories and their items render in the order the server returned', async () => {
  renderApp(
    MENU,
    clientWith([
      category({
        id: 'c1',
        name: 'Starters',
        items: [
          item({ id: 'i1', name: 'Samosa', position: 0 }),
          item({ id: 'i2', name: 'Beguni', position: 1 }),
        ],
      }),
      category({ id: 'c2', name: 'Biryani', position: 1, items: [] }),
    ]),
  );

  expect(await screen.findByText('Starters')).toBeInTheDocument();
  const names = screen
    .getAllByRole('link')
    .map((link) => link.textContent)
    .filter((text) => text === 'Samosa' || text === 'Beguni');
  expect(names).toEqual(['Samosa', 'Beguni']);
  expect(screen.getByText('2 items')).toBeInTheDocument();
  expect(screen.getByText('0 items')).toBeInTheDocument();
});

test('an empty category says so rather than rendering a blank card', async () => {
  renderApp(MENU, clientWith([category({ items: [] })]));
  expect(await screen.findByText('No items yet.')).toBeInTheDocument();
});

test('an empty menu guides the owner to create the first category (item 1)', async () => {
  renderApp(MENU, clientWith([]));

  expect(
    await screen.findByText(
      /Create your first category before adding menu items/i,
    ),
  ).toBeInTheDocument();
  // The primary action is creating the first category; adding an item is
  // present but disabled, because a category must exist first.
  expect(
    screen.getByRole('button', { name: 'Add first category' }),
  ).toBeEnabled();
  const addItem = screen.getByRole('button', { name: 'Add menu item' });
  expect(addItem).toBeDisabled();
  // The reason is plain visible text, not a hover-only tooltip.
  expect(
    screen.getByText('Add a category before you can add items.'),
  ).toBeInTheDocument();
  // No dead-end "Add menu item" link on an empty menu.
  expect(screen.queryByRole('link', { name: 'Add menu item' })).toBeNull();
});

test('hidden categories and hidden items are shown — this is the management view', async () => {
  renderApp(
    MENU,
    clientWith([
      category({
        name: 'Seasonal',
        is_visible: false,
        items: [item({ name: 'Pitha', is_hidden: true })],
      }),
    ]),
  );

  expect(await screen.findByText('Seasonal')).toBeInTheDocument();
  expect(screen.getByText('Pitha')).toBeInTheDocument();
  expect(screen.getAllByText('Hidden')).toHaveLength(2); // category and item
});

test('sold out and hidden are separate states, each spelled out', async () => {
  renderApp(
    MENU,
    clientWith([
      category({
        items: [
          item({ id: 'a', name: 'Sold out only', is_available: false }),
          item({ id: 'b', name: 'Hidden only', is_hidden: true }),
        ],
      }),
    ]),
  );

  expect(await screen.findByText('Sold out')).toBeInTheDocument();
  expect(screen.getByText('Hidden')).toBeInTheDocument();
});

test('an ordinary item carries no chips at all', async () => {
  renderApp(MENU, clientWith([category({ items: [item({ name: 'Plain' })] })]));
  await screen.findByText('Plain');
  expect(screen.queryByText('Hidden')).toBeNull();
  expect(screen.queryByText('Sold out')).toBeNull();
  expect(screen.queryByText('Featured')).toBeNull();
});

test('dietary tags render with display labels', async () => {
  renderApp(
    MENU,
    clientWith([
      category({ items: [item({ dietary_tags: ['halal', 'vegan'] })] }),
    ]),
  );
  expect(await screen.findByText('Halal')).toBeInTheDocument();
  expect(screen.getByText('Vegan')).toBeInTheDocument();
});

test('prices use the business currency, not a hardcoded dollar sign', async () => {
  renderApp(
    MENU,
    clientWith([category({ items: [item({ price_minor: 1250 })] })], 'JPY'),
  );
  // JPY has no minor unit: 1250 is ¥1,250, never ¥12.50.
  expect(await screen.findByText(/1,250/)).toBeInTheDocument();
  expect(screen.queryByText(/12\.50/)).toBeNull();
});

test('the featured strip counts hidden featured items too', async () => {
  renderApp(
    MENU,
    clientWith([
      category({
        items: [
          item({ id: 'a', name: 'One', is_featured: true }),
          // A hidden featured item still counts toward the limit (ADR-017 R1).
          item({ id: 'b', name: 'Two', is_featured: true, is_hidden: true }),
          item({ id: 'c', name: 'Three' }),
        ],
      }),
    ]),
  );

  expect(await screen.findByText(/Featured items: 2/)).toBeInTheDocument();
});

test('the featured strip reads zero on an unfeatured menu', async () => {
  renderApp(MENU, clientWith([category({ items: [item()] })]));
  expect(await screen.findByText(/Featured items: 0/)).toBeInTheDocument();
});

test('the featured strip prints no ceiling the contract does not publish', async () => {
  renderApp(
    MENU,
    clientWith([
      category({ items: [item({ id: 'a', name: 'One', is_featured: true })] }),
    ]),
  );

  const strip = await screen.findByText(/Featured items:/);
  // A count limit cannot be expressed in JSON Schema, so no denominator here
  // could have come from the generated contract. The server states its
  // ceiling in a 409 and nowhere else.
  expect(strip).toHaveTextContent(/Featured items: 1\b/);
  expect(strip).not.toHaveTextContent(/of \d/);
});

test('filtering narrows items and announces the count', async () => {
  renderApp(
    MENU,
    clientWith([
      category({
        id: 'c1',
        name: 'Starters',
        items: [
          item({ id: 'i1', name: 'Samosa' }),
          item({ id: 'i2', name: 'Beguni' }),
        ],
      }),
    ]),
  );

  fireEvent.change(await screen.findByLabelText(/search menu items/i), {
    target: { value: 'sam' },
  });

  expect(screen.getByText('Samosa')).toBeInTheDocument();
  expect(screen.queryByText('Beguni')).toBeNull();
  expect(screen.getByText('1 item matches')).toBeInTheDocument();
});

test('a category with no filter matches says so instead of looking empty', async () => {
  renderApp(
    MENU,
    clientWith([
      category({ name: 'Starters', items: [item({ name: 'Samosa' })] }),
    ]),
  );
  fireEvent.change(await screen.findByLabelText(/search menu items/i), {
    target: { value: 'zzz' },
  });
  expect(
    screen.getByText('No matching items in this category.'),
  ).toBeInTheDocument();
  expect(screen.getByText('0 items match')).toBeInTheDocument();
});

test('an item without an image reserves the same box so rows do not reflow', async () => {
  const { view } = renderApp(
    MENU,
    clientWith([category({ items: [item({ image_media_id: null })] })]),
  );
  await screen.findByText('Samosa');
  expect(view.container.querySelector('img')).toBeNull();
});

test('an item image renders with explicit dimensions and its alt text', async () => {
  const listAssets = vi.fn(async () =>
    ok({
      items: [
        {
          id: 'asset-1',
          kind: 'image' as const,
          status: 'active' as const,
          pending_expires_at: null,
          original_filename: 'samosa.jpg',
          source_format: 'jpeg' as const,
          width: 2000,
          height: 1500,
          byte_size: 1000,
          variants: [
            {
              variant: 'w320' as const,
              width: 320,
              height: 240,
              byte_size: 10,
            },
          ],
          created_at: '2026-07-21T00:00:00Z',
          updated_at: '2026-07-21T00:00:00Z',
        },
      ],
      total: 1,
      limit: 100,
      offset: 0,
    }),
  );
  renderApp(
    MENU,
    clientWith(
      [
        category({
          items: [
            item({
              image_media_id: 'asset-1',
              image_alt_text: 'Fried samosas',
            }),
          ],
        }),
      ],
      'USD',
      { media: { listAssets } },
    ),
  );

  const image = await screen.findByAltText('Fried samosas');
  expect(image).toHaveAttribute('width', '56');
  expect(image).toHaveAttribute('height', '56');
  expect(image).toHaveAttribute('loading', 'lazy');
});

test('the media index is not requested when the menu has no images', async () => {
  const listAssets = vi.fn(async () =>
    ok({ items: [], total: 0, limit: 100, offset: 0 }),
  );
  renderApp(
    MENU,
    clientWith([category({ items: [item({ image_media_id: null })] })], 'USD', {
      media: { listAssets },
    }),
  );
  await screen.findByText('Samosa');
  expect(listAssets).not.toHaveBeenCalled();
});

test('thumbnail variant selection prefers the smallest adequate rendition', () => {
  const asset = {
    variants: [
      { variant: 'w320' as const, width: 320, height: 240, byte_size: 1 },
      { variant: 'w640' as const, width: 640, height: 480, byte_size: 2 },
    ],
  };
  // A 56px box at 2x needs 112px: w320 is the smallest that covers it.
  expect(thumbnailVariant(asset as never, 56)).toBe('w320');
  // Nothing wide enough, and an asset with no variants at all, both fall
  // back to the canonical — variants exist only when strictly narrower than
  // the canonical, so a small source image legitimately has none.
  expect(thumbnailVariant({ variants: [] } as never, 56)).toBe('canonical');
  expect(thumbnailVariant(undefined, 56)).toBe('canonical');
  expect(thumbnailVariant(asset as never, 2000)).toBe('canonical');
});

test('a closed business says the menu is read-only', async () => {
  renderApp(
    MENU,
    makeClient({
      auth: {
        getSession: vi.fn(async () =>
          ok(
            sessionView({
              memberships: [
                {
                  business_id: SHALIK,
                  business_slug: 'shalik',
                  business_name: 'Shalik',
                  role: 'owner',
                  business_status: 'closed',
                },
              ],
            }),
          ),
        ),
      },
      businesses: {
        get: vi.fn(async () => ok(business({ status: 'closed' }))),
      },
      catalog: { getMenu: vi.fn(async () => ok(adminMenu([category()]))) },
    }),
  );

  expect(
    await screen.findByText(/read-only because the business is closed/i),
  ).toBeInTheDocument();
});
