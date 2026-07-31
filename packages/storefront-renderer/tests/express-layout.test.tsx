import { render, screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';

import { SectionList } from '../src/sections/SectionList';
import { VariantLayout } from '../src/variants/registry';
import {
  heroSection,
  menuSection,
  storefrontFixture,
  themeFixture,
  themeLogoFixture,
} from '../src/fixtures';

// The `express` layout arm (M4G-B, ADR-024 §1/§8): compact and
// action-oriented, and the one variant that ships zero motion (§9).

function renderExpress(theme = themeFixture()) {
  const storefront = storefrontFixture([heroSection(), menuSection()], {
    design_variant: 'express',
    theme,
  });
  return render(
    <VariantLayout storefront={storefront}>
      <SectionList sections={storefront.sections} />
    </VariantLayout>,
  );
}

describe('express layout', () => {
  test('dispatches to its own arm', () => {
    const { container } = renderExpress();
    expect(container.firstElementChild).toHaveAttribute(
      'data-variant',
      'express',
    );
    // The motion marker records the ruled treatment for the policy suite.
    expect(container.firstElementChild).toHaveAttribute('data-motion', 'none');
  });

  test('keeps the landmarks and the one fixed heading hierarchy', () => {
    renderExpress();
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
    expect(document.body.textContent).not.toMatch(/restaurant engine/i);
  });

  test('places the logo beside the name, which stays the single h1', () => {
    const { container } = renderExpress(
      themeFixture({ logo: themeLogoFixture() }),
    );
    expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    expect(container.querySelector('header img')?.getAttribute('alt')).toBe('');
  });

  test('renders name-only chrome when no logo is set', () => {
    const { container } = renderExpress();
    expect(container.querySelector('header img')).toBeNull();
  });

  test('carries no theme style of its own', () => {
    const { container } = renderExpress();
    expect(container.firstElementChild?.getAttribute('style')).toBeNull();
  });

  test('honours the inert preview link mode', () => {
    const storefront = storefrontFixture([heroSection()], {
      design_variant: 'express',
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
    const storefront = storefrontFixture([], { design_variant: 'express' });
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
