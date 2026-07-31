import { render, screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';

import { SectionList } from '../src/sections/SectionList';
import { VariantLayout } from '../src/variants/registry';
import type { PublicStorefront } from '../src/contract';
import {
  heroSection,
  storefrontFixture,
  storySection,
  themeFixture,
} from '../src/fixtures';

function renderClassic(
  storefront = storefrontFixture([heroSection(), storySection()]),
) {
  return render(
    <VariantLayout storefront={storefront}>
      <SectionList sections={storefront.sections} />
    </VariantLayout>,
  );
}

describe('variant registry', () => {
  test('unregistered runtime drift throws to the error boundary, undisclosed', () => {
    const drifted = storefrontFixture([], {
      design_variant: 'cinematic',
    } as unknown as Partial<Omit<PublicStorefront, 'sections'>>);
    expect(() => renderClassic(drifted)).toThrow(/unhandled contract variant/);
  });
});

describe('classic layout', () => {
  test('tenant-branded chrome with landmarks and one fixed heading hierarchy', () => {
    renderClassic();
    expect(screen.getByRole('banner')).toBeInTheDocument();
    expect(screen.getByRole('main')).toBeInTheDocument();
    expect(screen.getByRole('contentinfo')).toBeInTheDocument();
    expect(
      screen.getByRole('navigation', { name: 'Site' }),
    ).toBeInTheDocument();
    // h1 is the business name; every section heading is h2 regardless of
    // section order.
    expect(
      screen.getByRole('heading', { level: 1, name: 'Corner Kitchen' }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole('heading', { level: 2 })).toHaveLength(2);
    // White-label: no platform branding anywhere on a tenant page.
    expect(document.body.textContent).not.toMatch(/restaurant engine/i);
  });

  test('theme tokens live at the tenant-page boundary, not the variant root', () => {
    // M4G-B (ADR-024 §5): `themeStyle()` is applied once, on the element
    // carrying `tenantPageClass` (the public <body> and the preview
    // container), so the painted browser canvas and every descendant read
    // one typed source. A layout arm no longer owns the accent pair;
    // theme-style.test.ts owns the token assertions.
    const { container } = renderClassic(
      storefrontFixture([], { theme: themeFixture({ accent: '#112244' }) }),
    );
    const page = container.firstElementChild as HTMLElement;
    expect(page.getAttribute('style')).toBeNull();
    expect(page).toHaveAttribute('data-variant', 'classic');
  });

  test('an empty published configuration renders coherent chrome', () => {
    renderClassic(storefrontFixture([]));
    expect(
      screen.getByRole('heading', { level: 1, name: 'Corner Kitchen' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('main')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Menu' })).toHaveAttribute(
      'href',
      '/menu',
    );
    // No fabricated tenant content: nothing but chrome inside main.
    expect(screen.getByRole('main').textContent).toBe('');
  });
});
