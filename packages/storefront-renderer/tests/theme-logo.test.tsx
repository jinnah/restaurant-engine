import { render, screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';

import { SectionList } from '../src/sections/SectionList';
import { ThemeLogo } from '../src/theme/ThemeLogo';
import { VariantLayout } from '../src/variants/registry';
import {
  heroSection,
  storefrontFixture,
  themeFixture,
  themeLogoFixture,
} from '../src/fixtures';

// ADR-024 §7 rules the logo permanently decorative and the business name
// permanently the visible semantic h1. Those are accessibility
// invariants, so they are asserted directly rather than left to review.

function renderWithLogo(logo = themeLogoFixture()) {
  const storefront = storefrontFixture([heroSection()], {
    theme: themeFixture({ logo }),
  });
  return render(
    <VariantLayout storefront={storefront}>
      <SectionList sections={storefront.sections} />
    </VariantLayout>,
  );
}

describe('the theme logo component', () => {
  test('always emits an explicit empty alt, never omits the attribute', () => {
    const { container } = render(<ThemeLogo logo={themeLogoFixture()} />);
    const image = container.querySelector('img');
    expect(image).not.toBeNull();
    // Present AND empty: a missing attribute would announce an
    // unlabelled image, which is a defect, not a decorative image.
    expect(image?.hasAttribute('alt')).toBe(true);
    expect(image?.getAttribute('alt')).toBe('');
  });

  test('reserves the box with the delivered intrinsic dimensions', () => {
    const { container } = render(
      <ThemeLogo logo={themeLogoFixture({ width: 480, height: 160 })} />,
    );
    const image = container.querySelector('img');
    expect(image?.getAttribute('width')).toBe('480');
    expect(image?.getAttribute('height')).toBe('160');
  });

  test('builds a responsive srcset from the delivered renditions', () => {
    const { container } = render(<ThemeLogo logo={themeLogoFixture()} />);
    const srcset = container.querySelector('img')?.getAttribute('srcset');
    expect(srcset).toContain('w320');
    expect(srcset).toContain('320w');
    expect(srcset).toContain('480w');
  });

  test('carries no accessible name, so it cannot duplicate the h1', () => {
    render(<ThemeLogo logo={themeLogoFixture()} />);
    expect(screen.queryByRole('img')).toBeNull();
  });
});

describe('logo chrome in the variant layouts', () => {
  test('the business name stays the single visible h1 beside the logo', () => {
    renderWithLogo();
    const headings = screen.getAllByRole('heading', { level: 1 });
    expect(headings).toHaveLength(1);
    expect(headings[0]).toHaveTextContent('Corner Kitchen');
    // The logo is present, and it has not replaced or demoted the name.
    expect(document.querySelectorAll('img[alt=""]').length).toBeGreaterThan(0);
  });

  test('a null logo renders usable name-only chrome', () => {
    const storefront = storefrontFixture([heroSection()], {
      theme: themeFixture({ logo: null }),
    });
    const { container } = render(
      <VariantLayout storefront={storefront}>
        <SectionList sections={storefront.sections} />
      </VariantLayout>,
    );
    expect(
      screen.getByRole('heading', { level: 1, name: 'Corner Kitchen' }),
    ).toBeInTheDocument();
    // No empty frame is fabricated where the logo would be.
    const header = container.querySelector('header');
    expect(header?.querySelector('img')).toBeNull();
  });

  test('failed logo media leaves the chrome usable', () => {
    // The renderer cannot observe a load failure, and does not need to:
    // the name is always present as text and the image conveys nothing on
    // its own, so a broken reference costs nothing informational.
    renderWithLogo(themeLogoFixture({ url: '/api/v1/public/media/gone/w640' }));
    expect(
      screen.getByRole('heading', { level: 1, name: 'Corner Kitchen' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('navigation', { name: 'Site' }),
    ).toBeInTheDocument();
  });

  test('public and inert preview render the same logo markup', () => {
    const storefront = storefrontFixture([], {
      theme: themeFixture({ logo: themeLogoFixture() }),
    });
    const active = render(
      <VariantLayout storefront={storefront}>{null}</VariantLayout>,
    );
    const activeLogo = active.container.querySelector('header img')?.outerHTML;
    active.unmount();
    const inert = render(
      <VariantLayout storefront={storefront} links="inert">
        {null}
      </VariantLayout>,
    );
    const inertLogo = inert.container.querySelector('header img')?.outerHTML;
    expect(activeLogo).toBe(inertLogo);
  });
});
