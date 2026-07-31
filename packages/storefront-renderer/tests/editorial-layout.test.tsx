import { render, screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';

import { SectionList } from '../src/sections/SectionList';
import { VariantLayout } from '../src/variants/registry';
import {
  heroSection,
  storefrontFixture,
  storySection,
  themeFixture,
  themeLogoFixture,
} from '../src/fixtures';

// The `editorial` layout arm (M4G-B, ADR-024 §1/§8). The accessibility
// floors are variant-independent by design, so they are asserted per
// variant: a variant may change chrome and tokens, never the landmarks,
// the heading hierarchy, or the logo ruling.

function renderEditorial(theme = themeFixture()) {
  const storefront = storefrontFixture([heroSection(), storySection()], {
    design_variant: 'editorial',
    theme,
  });
  return render(
    <VariantLayout storefront={storefront}>
      <SectionList sections={storefront.sections} />
    </VariantLayout>,
  );
}

describe('editorial layout', () => {
  test('dispatches to its own arm', () => {
    const { container } = renderEditorial();
    expect(container.firstElementChild).toHaveAttribute(
      'data-variant',
      'editorial',
    );
  });

  test('keeps the landmarks and the one fixed heading hierarchy', () => {
    renderEditorial();
    expect(screen.getByRole('banner')).toBeInTheDocument();
    expect(screen.getByRole('main')).toBeInTheDocument();
    expect(screen.getByRole('contentinfo')).toBeInTheDocument();
    expect(
      screen.getByRole('navigation', { name: 'Site' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { level: 1, name: 'Corner Kitchen' }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole('heading', { level: 2 })).toHaveLength(2);
    // White-label: no platform branding on a tenant page.
    expect(document.body.textContent).not.toMatch(/restaurant engine/i);
  });

  test('places the logo beside the name, which stays the single h1', () => {
    const { container } = renderEditorial(
      themeFixture({ logo: themeLogoFixture() }),
    );
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    const logo = container.querySelector('header img');
    expect(logo).not.toBeNull();
    expect(logo?.getAttribute('alt')).toBe('');
  });

  test('renders name-only chrome when no logo is set', () => {
    const { container } = renderEditorial();
    expect(container.querySelector('header img')).toBeNull();
    expect(
      screen.getByRole('heading', { level: 1, name: 'Corner Kitchen' }),
    ).toBeInTheDocument();
  });

  test('carries no theme style of its own', () => {
    // The palette, pairing, and accent tokens belong at the tenant-page
    // boundary (ADR-024 §5); a variant root must not re-declare them.
    const { container } = renderEditorial();
    expect(container.firstElementChild?.getAttribute('style')).toBeNull();
  });

  test('honours the inert preview link mode', () => {
    const storefront = storefrontFixture([heroSection()], {
      design_variant: 'editorial',
    });
    const { container } = render(
      <VariantLayout storefront={storefront} links="inert">
        <SectionList sections={storefront.sections} links="inert" />
      </VariantLayout>,
    );
    for (const anchor of container.querySelectorAll('a')) {
      expect(anchor.hasAttribute('href')).toBe(false);
    }
    expect(screen.queryByRole('link')).toBeNull();
  });

  test('renders an empty published configuration coherently', () => {
    const storefront = storefrontFixture([], {
      design_variant: 'editorial',
    });
    render(
      <VariantLayout storefront={storefront}>
        <SectionList sections={storefront.sections} />
      </VariantLayout>,
    );
    expect(screen.getByRole('main').textContent).toBe('');
    expect(screen.getByRole('link', { name: 'Menu' })).toHaveAttribute(
      'href',
      '/menu',
    );
  });
});
