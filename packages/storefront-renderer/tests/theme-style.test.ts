// @vitest-environment node

// `themeStyle` is the ONE place a stored theme becomes CSS custom
// properties (ADR-024 §5). It is applied to the element carrying
// `tenantPageClass` — public <body> and the preview container — so these
// assertions cover both surfaces at once.

import { describe, expect, test } from 'vitest';

import { themeFixture } from '../src/fixtures';
import { paletteTokens } from '../src/theme/palettes';
import { themeStyle } from '../src/theme/theme-style';
import { typePairingTokens } from '../src/theme/type-pairings';

function style(theme: Parameters<typeof themeStyle>[0]) {
  return themeStyle(theme) as unknown as Record<string, string>;
}

describe('themeStyle', () => {
  test('the delivered defaults reproduce the delivered presentation', () => {
    const tokens = style(themeFixture());
    const warm = paletteTokens('warm');
    const humanist = typePairingTokens('humanist');
    expect(tokens['--color-bg']).toBe(warm.bg);
    expect(tokens['--color-surface']).toBe(warm.surface);
    expect(tokens['--color-text']).toBe(warm.text);
    expect(tokens['--color-muted']).toBe(warm.muted);
    expect(tokens['--color-border']).toBe(warm.border);
    expect(tokens['--accent']).toBe('#a34b2a');
    expect(tokens['--accent-contrast']).toBe('#ffffff');
    expect(tokens['--font-body']).toBe(humanist.body);
    expect(tokens['--font-heading']).toBe(humanist.heading);
    expect(tokens['--type-scale']).toBe('1');
    expect(tokens['--heading-weight']).toBe('bold');
    expect(tokens['--heading-tracking']).toBe('normal');
  });

  test('a selected palette replaces every colour token', () => {
    const tokens = style(themeFixture({ palette: 'midnight' }));
    const midnight = paletteTokens('midnight');
    expect(tokens['--color-bg']).toBe(midnight.bg);
    expect(tokens['--color-surface']).toBe(midnight.surface);
    expect(tokens['--color-text']).toBe(midnight.text);
    expect(tokens['--color-muted']).toBe(midnight.muted);
    expect(tokens['--color-border']).toBe(midnight.border);
  });

  test('a selected pairing replaces the typography tokens', () => {
    const tokens = style(themeFixture({ type_pairing: 'serif_display' }));
    const serif = typePairingTokens('serif_display');
    expect(tokens['--font-heading']).toBe(serif.heading);
    expect(tokens['--font-body']).toBe(serif.body);
    expect(tokens['--type-scale']).toBe(serif.scale);
  });

  test('the accent is grandfathered and only overrides the accent token', () => {
    // ADR-024 §5: the tenant accent never participates in the palette's
    // five colours, whichever palette is selected.
    const tokens = style(themeFixture({ accent: '#112244', palette: 'slate' }));
    const slate = paletteTokens('slate');
    expect(tokens['--accent']).toBe('#112244');
    expect(tokens['--accent-contrast']).toBe('#ffffff');
    expect(tokens['--color-bg']).toBe(slate.bg);
  });

  test('an invalid runtime accent falls closed to the platform default', () => {
    const tokens = style(themeFixture({ accent: 'expression(alert(1))' }));
    expect(tokens['--accent']).toBe('#a34b2a');
  });
});
