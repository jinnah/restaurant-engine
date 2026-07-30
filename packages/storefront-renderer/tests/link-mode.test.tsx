import { render, screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';

import { SectionList } from '../src/sections/SectionList';
import { VariantLayout } from '../src/variants/registry';
import {
  heroSection,
  menuSection,
  publicMenuFixture,
  storefrontFixture,
} from '../src/fixtures';

// The ADR-022 §3 preview link mode. In 'active' mode (the default — the
// public storefront passes nothing) the three in-site navigation elements
// are ordinary anchors. In 'inert' mode the same elements render with no
// href: no URL exists for any mouse, keyboard, auxiliary-click, or
// context-menu navigation path, and without an href the element exposes
// no link role, so assistive technology is never told an active link
// exists that cannot be followed.

function renderStorefront(links?: 'active' | 'inert') {
  const storefront = storefrontFixture([
    heroSection({ primary_action: 'view_menu' }),
    menuSection(),
  ]);
  const menu = publicMenuFixture();
  return render(
    <VariantLayout storefront={storefront} links={links}>
      <SectionList
        sections={storefront.sections}
        menuData={{ currency: menu.business.currency, featured: [] }}
        links={links}
      />
    </VariantLayout>,
  );
}

describe('link mode', () => {
  test('default and active modes render the three navigation anchors', () => {
    renderStorefront();
    const links = screen.getAllByRole('link');
    expect(links.map((link) => link.textContent)).toEqual([
      'Menu',
      'View menu',
      'View the full menu',
    ]);
    for (const link of links) {
      expect(link).toHaveAttribute('href', '/menu');
    }
  });

  test('inert mode renders no link roles and no hrefs anywhere', () => {
    const { container } = renderStorefront('inert');
    expect(screen.queryAllByRole('link')).toEqual([]);
    expect(container.querySelectorAll('[href]')).toHaveLength(0);
    // The visible presentation is unchanged: the same elements render the
    // same text through the same classes.
    expect(screen.getByText('View menu')).toBeInTheDocument();
    expect(screen.getByText('View the full menu')).toBeInTheDocument();
    expect(screen.getByText('Menu')).toBeInTheDocument();
  });

  test('inert markup differs from active markup only by href presence', () => {
    const active = renderStorefront().container.innerHTML;
    const inert = renderStorefront('inert').container.innerHTML;
    expect(active.replaceAll(' href="/menu"', '')).toBe(inert);
  });
});
