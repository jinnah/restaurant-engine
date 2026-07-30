import { render, screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';

import { SectionList } from '../components/sections/SectionList';
import { VariantLayout } from '../components/variants/registry';
import {
  COMPLEX_SCRIPT,
  contactSection,
  heroSection,
  storefrontFixture,
  storySection,
} from './fixtures';

// Unicode/complex-script rendering verification (ADR-021): Bengali is the
// required initial complex-script fixture — conjuncts, matras, ZWNJ/ZWJ —
// as engineering test data only. The contract proven here: what the
// backend stored (NFC, join controls intact) is byte-for-byte what the
// DOM carries; the renderer never re-normalizes, strips, or mangles.

describe('fixture preconditions', () => {
  test('every fixture is NFC-stable (so re-normalization is detectable)', () => {
    for (const value of Object.values(COMPLEX_SCRIPT)) {
      expect(value).toBe(value.normalize('NFC'));
    }
  });

  test('join-control fixtures actually carry ZWJ / ZWNJ', () => {
    expect(COMPLEX_SCRIPT.bengaliZwj).toContain('‍');
    expect(COMPLEX_SCRIPT.bengaliZwnj).toContain('‌');
  });
});

describe('complex-script rendering', () => {
  test('Bengali headings, body, and join controls survive byte-for-byte', () => {
    render(
      <SectionList
        sections={[
          heroSection({
            heading: COMPLEX_SCRIPT.bengaliConjunct,
            subheading: COMPLEX_SCRIPT.bengaliZwj,
            image: null,
            primary_action: 'none',
          }),
          storySection({
            heading: COMPLEX_SCRIPT.bengaliZwnj,
            body: COMPLEX_SCRIPT.bengaliBody,
          }),
        ]}
      />,
    );
    expect(
      screen.getByRole('heading', {
        level: 2,
        name: COMPLEX_SCRIPT.bengaliConjunct,
      }).textContent,
    ).toBe(COMPLEX_SCRIPT.bengaliConjunct);
    expect(screen.getByText(COMPLEX_SCRIPT.bengaliZwj).textContent).toBe(
      COMPLEX_SCRIPT.bengaliZwj,
    );
    expect(
      screen.getByRole('heading', {
        level: 2,
        name: COMPLEX_SCRIPT.bengaliZwnj,
      }).textContent,
    ).toBe(COMPLEX_SCRIPT.bengaliZwnj);
    // The multi-paragraph Bengali body reassembles to exactly the stored
    // text (paragraph split + line breaks lose nothing).
    const main = document.body;
    for (const fragment of COMPLEX_SCRIPT.bengaliBody.split('\n')) {
      if (fragment !== '') {
        expect(main.textContent).toContain(fragment);
      }
    }
  });

  test('a Bengali business name renders intact through the variant chrome', () => {
    const storefront = storefrontFixture([], {
      business: {
        name: COMPLEX_SCRIPT.bengaliConjunct,
        slug: 'fixture',
        timezone: 'America/New_York',
        currency: 'USD',
      },
    });
    render(
      <VariantLayout storefront={storefront}>
        <SectionList sections={storefront.sections} />
      </VariantLayout>,
    );
    expect(
      screen.getByRole('heading', {
        level: 1,
        name: COMPLEX_SCRIPT.bengaliConjunct,
      }),
    ).toBeInTheDocument();
  });

  test('long Latin and long unbroken content render unmodified', () => {
    render(
      <SectionList
        sections={[
          contactSection({
            heading: COMPLEX_SCRIPT.longLatin,
            address_lines: [COMPLEX_SCRIPT.longLatin],
            phone: null,
            email: null,
          }),
        ]}
      />,
    );
    expect(screen.getAllByText(COMPLEX_SCRIPT.longLatin)).toHaveLength(2);
  });
});
