import { render } from '@testing-library/react';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, test } from 'vitest';

import { JsonLd } from '../components/JsonLd';
import { safeJsonLdSerialize } from '../lib/json-ld';
import { restaurantJsonLd } from '../lib/restaurant-json-ld';
import {
  contactSection,
  storefrontFixture,
} from '@restaurant-engine/storefront-renderer/fixtures';

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

describe('restaurantJsonLd', () => {
  test('carries only supported published facts', () => {
    const data = restaurantJsonLd(
      storefrontFixture([contactSection()]),
      'https://corner-kitchen.example.com',
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
    const data = restaurantJsonLd(storefrontFixture([]), null);
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
