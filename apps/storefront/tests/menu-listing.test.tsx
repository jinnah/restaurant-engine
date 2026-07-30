import { render, screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';

import { MenuListing } from '../components/menu/MenuListing';
import { menuItemFixture, publicMenuFixture } from './fixtures';

describe('MenuListing', () => {
  test('renders categories and items in projection order with exact prices', () => {
    render(<MenuListing menu={publicMenuFixture()} />);
    const categories = screen
      .getAllByRole('heading', { level: 3 })
      .map((h) => h.textContent);
    expect(categories).toEqual(['Mains', 'Drinks']);
    expect(screen.getByText('House roast chicken')).toBeInTheDocument();
    // Money by identity: 1250 minor units is exactly $12.50.
    expect(screen.getByText('$12.50')).toBeInTheDocument();
    expect(screen.getByText('$9.95')).toBeInTheDocument();
    expect(screen.getByText('$5.00')).toBeInTheDocument();
    expect(screen.getByText('Hearty plates')).toBeInTheDocument();
  });

  test('sold-out items stay listed with the sold-out badge', () => {
    render(<MenuListing menu={publicMenuFixture()} />);
    expect(screen.getByText('Garden salad')).toBeInTheDocument();
    expect(screen.getByText('Sold out')).toBeInTheDocument();
  });

  test('featured and dietary badges render as neutral labels', () => {
    render(<MenuListing menu={publicMenuFixture()} />);
    expect(screen.getByText('Featured')).toBeInTheDocument();
    expect(screen.getByText('Halal')).toBeInTheDocument();
    expect(screen.getByText('Vegetarian')).toBeInTheDocument();
    expect(screen.getByText('Vegan')).toBeInTheDocument();
  });

  test('item images lazy-load with delivered alt text', () => {
    const { container } = render(<MenuListing menu={publicMenuFixture()} />);
    const images = container.querySelectorAll('img');
    expect(images).toHaveLength(1);
    expect(images[0]).toHaveAttribute('loading', 'lazy');
    expect(images[0]).toHaveAttribute('alt', 'A plated dish on a wooden table');
  });

  test('modifier groups are deliberately not rendered (M6 surface)', () => {
    const menu = publicMenuFixture({
      categories: [
        {
          id: 'c1',
          name: 'Mains',
          description: null,
          items: [
            menuItemFixture({
              modifier_groups: [
                {
                  id: 'g1',
                  name: 'Spice level',
                  min_select: 1,
                  max_select: 1,
                  options: [],
                },
              ],
            }),
          ],
        },
      ],
    });
    render(<MenuListing menu={menu} />);
    expect(screen.queryByText('Spice level')).not.toBeInTheDocument();
  });

  test('an empty menu renders the honest empty state', () => {
    render(
      <MenuListing
        menu={publicMenuFixture({ categories: [], featured_item_ids: [] })}
      />,
    );
    expect(
      screen.getByText(/no menu items are available right now/i),
    ).toBeInTheDocument();
  });
});
