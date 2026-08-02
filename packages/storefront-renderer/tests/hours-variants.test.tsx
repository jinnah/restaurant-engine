import { render, screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';

import { SectionList } from '../src/sections/SectionList';
import { VariantLayout } from '../src/variants/registry';
import type { DesignVariant } from '../src/contract';
import {
  heroSection,
  hoursDataFixture,
  hoursSection,
  storefrontFixture,
} from '../src/fixtures';

// The M4G-B ruling applied to M5D: the hours section lands in the same
// slice as its rendering under every variant arm, so the registry and the
// renderer cannot drift. One shared HoursSection renders under classic,
// editorial, and express chrome alike — variants express themselves only
// through chrome and tokens, never by forking a section renderer.

const VARIANTS: DesignVariant[] = ['classic', 'editorial', 'express'];

describe('hours section under every variant arm', () => {
  for (const variant of VARIANTS) {
    test(`${variant}: renders the schedule, status, and exceptions`, () => {
      const storefront = storefrontFixture([heroSection(), hoursSection()], {
        design_variant: variant,
      });
      render(
        <VariantLayout storefront={storefront}>
          <SectionList
            sections={storefront.sections}
            hoursData={hoursDataFixture()}
          />
        </VariantLayout>,
      );
      expect(
        screen.getByRole('heading', { level: 2, name: 'Opening hours' }),
      ).toBeInTheDocument();
      expect(screen.getByText('Open now')).toBeInTheDocument();
      expect(screen.getByText('Saturday')).toBeInTheDocument();
      expect(screen.getByText('5:00 PM – 2:00 AM')).toBeInTheDocument();
      expect(
        screen.getByRole('heading', { level: 3, name: 'Special hours' }),
      ).toBeInTheDocument();
      // The heading hierarchy holds in every variant: the business name
      // stays the single h1; the section contributes h2/h3 only.
      expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1);
    });
  }
});
