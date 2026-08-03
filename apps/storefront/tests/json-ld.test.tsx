import { render } from '@testing-library/react';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, test } from 'vitest';

import { JsonLd } from '../components/JsonLd';
import { safeJsonLdSerialize } from '../lib/json-ld';
import { restaurantJsonLd } from '../lib/restaurant-json-ld';
import {
  contactSection,
  hoursDataFixture,
  storefrontFixture,
} from '@restaurant-engine/storefront-renderer/fixtures';
import type { PublicAvailability } from '@restaurant-engine/api-client';

describe('safeJsonLdSerialize', () => {
  test('tenant text containing a script terminator cannot break out', () => {
    const hostile = { name: '</script><script>alert(1)</script>' };
    const serialized = safeJsonLdSerialize(hostile);
    expect(serialized).not.toContain('<');
    expect(serialized).not.toContain('>');
    expect(serialized).toContain('\\u003c/script\\u003e');
    // Round-trips to exactly the original value.
    expect(JSON.parse(serialized)).toEqual(hostile);
  });

  test('escapes ampersands and JS line separators', () => {
    const value = {
      name: `Fish & Chips${String.fromCharCode(0x2028)}Shop${String.fromCharCode(0x2029)}`,
    };
    const serialized = safeJsonLdSerialize(value);
    expect(serialized).not.toContain('&');
    expect(serialized).not.toContain(String.fromCharCode(0x2028));
    expect(serialized).not.toContain(String.fromCharCode(0x2029));
    expect(JSON.parse(serialized)).toEqual(value);
  });
});

describe('JsonLd component', () => {
  test('embeds exactly the serialized JSON with no markup characters', () => {
    const { container } = render(
      <JsonLd data={{ '@type': 'Restaurant', name: '</script>' }} />,
    );
    const script = container.querySelector(
      'script[type="application/ld+json"]',
    );
    expect(script).not.toBeNull();
    expect(script?.innerHTML).not.toContain('<');
    expect(JSON.parse(script?.innerHTML ?? '')).toEqual({
      '@type': 'Restaurant',
      name: '</script>',
    });
  });
});

/** The availability projection over the renderer's hours fixture. */
function availabilityFixture(
  overrides: Partial<PublicAvailability> = {},
): PublicAvailability {
  const data = hoursDataFixture();
  return {
    business: {
      name: 'Corner Kitchen',
      slug: 'corner-kitchen',
      timezone: data.timezone,
      currency: 'USD',
    },
    is_open_now: data.is_open_now,
    closes_at: data.closes_at,
    next_opens_at: data.next_opens_at,
    weekly: data.weekly,
    exceptions: data.exceptions,
    pickup: {
      enabled: true,
      asap_enabled: true,
      next_pickup_at: null,
      ordering_enabled: false,
      ordering_paused: false,
      pause_note: null,
      pause_resumes_at: null,
    },
    ...overrides,
  };
}

describe('restaurantJsonLd', () => {
  test('carries only supported published facts', () => {
    const data = restaurantJsonLd(
      storefrontFixture([contactSection()]),
      'https://corner-kitchen.example.com',
      null,
    );
    expect(data).toEqual({
      '@context': 'https://schema.org',
      '@type': 'Restaurant',
      name: 'Corner Kitchen',
      url: 'https://corner-kitchen.example.com/',
      telephone: '(716) 555-0100',
      address: '12 Main Street, Buffalo, NY 14201',
    });
  });

  test('omits absent facts and never claims unmodeled ones', () => {
    const data = restaurantJsonLd(storefrontFixture([]), null, null);
    expect(data).toEqual({
      '@context': 'https://schema.org',
      '@type': 'Restaurant',
      name: 'Corner Kitchen',
    });
    for (const forbidden of [
      'openingHours',
      'openingHoursSpecification',
      'servesCuisine',
      'hasMenu',
      'aggregateRating',
      'priceRange',
      'acceptsReservations',
    ]) {
      expect(data).not.toHaveProperty(forbidden);
    }
  });

  test('models the weekly hours from the availability projection (M5D)', () => {
    // Blueprint §12.2: hours are modeled, not decorative text — one
    // OpeningHoursSpecification per stored interval, in the D1 order,
    // independent of whether an hours SECTION is composed (the fixture
    // composes none).
    const data = restaurantJsonLd(
      storefrontFixture([]),
      null,
      availabilityFixture({
        weekly: [
          { day_of_week: 0, opens_minute: 660, closes_minute: 1260 },
          // D1 overnight: Saturday 17:00 into Sunday 02:00 — schema.org's
          // own convention (closes earlier than opens spans the next day).
          { day_of_week: 5, opens_minute: 1020, closes_minute: 1560 },
          // Interval closing exactly at midnight: 00:00 is "earlier than
          // opens", the same next-day convention.
          { day_of_week: 6, opens_minute: 720, closes_minute: 1440 },
        ],
      }),
    );
    expect(data['openingHoursSpecification']).toEqual([
      {
        '@type': 'OpeningHoursSpecification',
        dayOfWeek: 'Monday',
        opens: '11:00',
        closes: '21:00',
      },
      {
        '@type': 'OpeningHoursSpecification',
        dayOfWeek: 'Saturday',
        opens: '17:00',
        closes: '02:00',
      },
      {
        '@type': 'OpeningHoursSpecification',
        dayOfWeek: 'Sunday',
        opens: '12:00',
        closes: '00:00',
      },
    ]);
  });

  test('a full 24-hour day is stated as 00:00–23:59, never opens=closes', () => {
    const data = restaurantJsonLd(
      storefrontFixture([]),
      null,
      availabilityFixture({
        weekly: [{ day_of_week: 2, opens_minute: 0, closes_minute: 1440 }],
      }),
    );
    expect(data['openingHoursSpecification']).toEqual([
      {
        '@type': 'OpeningHoursSpecification',
        dayOfWeek: 'Wednesday',
        opens: '00:00',
        closes: '23:59',
      },
    ]);
  });

  test('an empty schedule claims nothing at all', () => {
    // An empty array would pretend hours are modeled; the honest claim
    // for a business with no configured schedule is no claim.
    const data = restaurantJsonLd(
      storefrontFixture([]),
      null,
      availabilityFixture({ weekly: [] }),
    );
    expect(data).not.toHaveProperty('openingHoursSpecification');
  });

  test('exceptions are deliberately not claimed', () => {
    // Transient overrides in a crawler's index would rot; the weekly
    // schedule is the only structured-hours claim.
    const data = restaurantJsonLd(
      storefrontFixture([]),
      null,
      availabilityFixture(),
    );
    expect(JSON.stringify(data)).not.toContain('2026-12-25');
    expect(data).not.toHaveProperty('specialOpeningHoursSpecification');
  });
});

describe('the dangerouslySetInnerHTML boundary', () => {
  test('exactly one occurrence exists, inside the audited JsonLd component', () => {
    const root = join(__dirname, '..');
    const hits: string[] = [];
    const walk = (dir: string): void => {
      for (const entry of readdirSync(dir)) {
        if (entry === 'node_modules' || entry.startsWith('.')) continue;
        const path = join(dir, entry);
        if (statSync(path).isDirectory()) {
          walk(path);
        } else if (/\.(ts|tsx)$/.test(entry)) {
          const source = readFileSync(path, 'utf-8');
          if (
            source.includes('dangerouslySetInnerHTML={{') &&
            !path.includes('tests')
          ) {
            hits.push(path.slice(root.length + 1).replaceAll('\\', '/'));
          }
        }
      }
    };
    walk(join(root, 'app'));
    walk(join(root, 'components'));
    walk(join(root, 'lib'));
    expect(hits).toEqual(['components/JsonLd.tsx']);
  });
});
