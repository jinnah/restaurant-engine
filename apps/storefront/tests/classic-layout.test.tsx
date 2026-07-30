import { render, screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';

import { SectionList } from '../components/sections/SectionList';
import { VariantLayout } from '../components/variants/registry';
import type { PublicStorefront } from '../lib/contract';
import { heroSection, storefrontFixture, storySection } from './fixtures';

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

  test('applies the accent pair as CSS custom properties', () => {
    const { container } = renderClassic(
      storefrontFixture([], { theme: { accent: '#112244' } }),
    );
    const page = container.firstElementChild as HTMLElement;
    expect(page.style.getPropertyValue('--accent')).toBe('#112244');
    // Dark accent → white foreground, the computed accessibility floor.
    expect(page.style.getPropertyValue('--accent-contrast')).toBe('#ffffff');
  });

  test('an invalid runtime accent falls closed to the platform default', () => {
    const { container } = renderClassic(
      storefrontFixture([], { theme: { accent: 'expression(alert(1))' } }),
    );
    const page = container.firstElementChild as HTMLElement;
    expect(page.style.getPropertyValue('--accent')).toBe('#a34b2a');
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
