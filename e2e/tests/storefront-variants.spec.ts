import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Browser, type Page } from '@playwright/test';
import { seedPublishedStorefront } from '../support/api';
import { expectPageClean, watchPage } from '../support/hygiene';
import { expectTargetGeometry } from '../support/layout';
import { specNamespace, storefrontOrigin } from '../support/namespace';
import { publicVisit, visitorContext } from '../support/publicApi';
import {
  expectAccentTextLegible,
  expectPaintedCanvas,
  expectPalette,
  expectTypePairing,
  readTenantTokens,
  type DesignVariantId,
  type PaletteId,
  type TypePairingId,
} from '../support/theme';
import { signIn } from '../support/ui';

/**
 * Per-variant browser and visual acceptance (M4G-D, ADR-024 §11/§12).
 *
 * One representative journey per variant, each proving the governance
 * split end to end: the platform assigns the structural variant, the
 * owner saves a draft carrying the tenant-controlled palette, pairing,
 * accent, and logo, previews the saved draft, publishes it, and an
 * anonymous visitor under the tenant host gets exactly that design.
 *
 * The palette × pairing selection is the small pairwise one §12 requires,
 * not the 15-cell product: the three journeys below take three distinct
 * palettes and all three pairings, and `storefront-theme-matrix.spec.ts`
 * takes the two remaining palettes. Every palette and every pairing is
 * therefore covered in a real browser, in five combinations.
 *
 * The axe boundary is ADR-023's, verbatim: WCAG 2.0/2.1 A and AA rules,
 * blocking at zero violations, no exclusions. A pass is engineering
 * evidence within that boundary — not WCAG certification, not complete
 * accessibility compliance, and not proof that no defect exists.
 */

const AXE_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'];

const CATEGORY = 'House specialties';
const ITEM = 'Clay-oven lamb shank';
const IMAGE_ALT = 'The dining room set for dinner service';
const HERO_SUBHEADING = 'A neighborhood kitchen with a wood-fired oven';
const STORY_BODY =
  'The kitchen has been in one family for three generations, and the ' +
  'oven at its center was built by hand before the first table was set.';

/** The ADR-023 capture subset, reused so evidence stays comparable. */
const CAPTURE_VIEWPORTS = [
  { width: 390, height: 844 },
  { width: 1280, height: 900 },
];

interface VariantCase {
  variant: DesignVariantId;
  palette: PaletteId;
  pairing: TypePairingId;
  accent: string;
  /** ADR-024 §9: the motion attribute the layout advertises, if any. */
  motion: string | null;
  heroHeading: string;
}

/**
 * The three journeys. Accents are chosen deliberately: `midnight` gets a
 * deep accent that CANNOT clear AA against a dark background unadjusted,
 * so the §5 `--accent-text` derivation is genuinely exercised in a real
 * browser rather than trivially satisfied.
 */
const CASES: VariantCase[] = [
  {
    variant: 'classic',
    palette: 'warm',
    pairing: 'humanist',
    accent: '#a34b2a',
    motion: null,
    heroHeading: 'Wood-fired cooking, all seasons',
  },
  {
    variant: 'editorial',
    palette: 'midnight',
    pairing: 'serif_display',
    accent: '#7a1f2b',
    motion: 'rich',
    heroHeading: 'A kitchen that keeps its own hours',
  },
  {
    variant: 'express',
    palette: 'ember',
    pairing: 'geometric',
    accent: '#8a3d12',
    motion: 'none',
    heroHeading: 'Order ahead, eat sooner',
  },
];

async function expectNoAxeViolations(page: Page, where: string): Promise<void> {
  const results = await new AxeBuilder({ page }).withTags(AXE_TAGS).analyze();
  const report = results.violations.map((violation) => ({
    rule: violation.id,
    impact: violation.impact,
    help: violation.help,
    targets: violation.nodes.map((node) => node.target),
  }));
  expect(
    report,
    `axe violations at ${where}:\n${JSON.stringify(report, null, 2)}`,
  ).toEqual([]);
}

/**
 * ADR-024 §7, refereed structurally rather than by eye: the logo is
 * present, carries a literal empty `alt`, contributes no accessible name,
 * and sits beside the business name — which remains the one visible `h1`.
 */
async function expectDecorativeLogo(
  page: Page,
  businessName: string,
  where: string,
): Promise<void> {
  const logo = page.locator('header img');
  await expect(logo, `logo present at ${where}`).toHaveCount(1);
  // Present AND empty: a missing attribute would be an unlabelled image.
  const alt = await logo.getAttribute('alt');
  expect(alt, `logo alt attribute at ${where}`).toBe('');
  await expect(
    logo,
    `decorative logo must expose no accessible name at ${where}`,
  ).toHaveAccessibleName('');
  // Real bytes, and a reserved box (intrinsic dimensions, no CLS).
  const delivered = await logo.evaluate((el) => {
    const img = el as HTMLImageElement;
    return {
      naturalWidth: img.naturalWidth,
      width: img.getAttribute('width'),
      height: img.getAttribute('height'),
    };
  });
  expect(delivered.naturalWidth, `logo bytes at ${where}`).toBeGreaterThan(0);
  expect(delivered.width, `logo intrinsic width at ${where}`).not.toBeNull();
  expect(delivered.height, `logo intrinsic height at ${where}`).not.toBeNull();

  await expect(page.locator('h1'), `single h1 at ${where}`).toHaveCount(1);
  await expect(
    page.getByRole('heading', { name: businessName, level: 1 }),
  ).toBeVisible();
}

/** The four landmark regions every variant commits to (ADR-021 §10). */
async function expectLandmarks(page: Page, where: string): Promise<void> {
  await expect(page.getByRole('banner'), `banner at ${where}`).toBeVisible();
  await expect(
    page.getByRole('navigation', { name: 'Site' }),
    `site nav at ${where}`,
  ).toBeVisible();
  await expect(page.locator('main'), `main at ${where}`).toHaveCount(1);
  await expect(
    page.getByRole('contentinfo'),
    `contentinfo at ${where}`,
  ).toBeVisible();
}

/**
 * The largest duration in a computed CSS time list, in seconds.
 *
 * The value is compared numerically rather than as a string because a
 * browser may serialise the same duration either way — Chromium reports
 * the floor's `0.01ms` as `1e-05s` — and a string comparison would be
 * asserting a serialisation format instead of the collapse itself.
 */
function maxDurationSeconds(value: string): number {
  return Math.max(
    ...value.split(',').map((part) => {
      const text = part.trim();
      const number = Number.parseFloat(text);
      return text.endsWith('ms') ? number / 1000 : number;
    }),
  );
}

/** Anything at or below this is collapsed, not animated. */
const COLLAPSED_SECONDS = 0.001;

/**
 * ADR-024 §9 in a real browser, which is precisely what jsdom could not
 * prove. Under `prefers-reduced-motion: reduce` the delivered floor must
 * both collapse the duration and DETACH the scroll timeline, so nothing
 * is left mid-progress; and the content must be fully visible either way,
 * because every keyframe terminates at the unenhanced state.
 */
async function expectReducedMotionNeutralised(
  browser: Browser,
  url: string,
  where: string,
): Promise<void> {
  const context = await browser.newContext({ reducedMotion: 'reduce' });
  try {
    const page = await context.newPage();
    const problems = watchPage(page);
    const response = await publicVisit(page, url);
    expect(response.status(), `reduced-motion status at ${where}`).toBe(200);

    const machinery = await page.evaluate(() => {
      const sections = Array.from(
        document.querySelectorAll('main section'),
      ) as HTMLElement[];
      return sections.map((el) => {
        const style = getComputedStyle(el);
        return {
          animationDuration: style.animationDuration,
          animationTimeline: style.getPropertyValue('animation-timeline'),
          transitionDuration: style.transitionDuration,
          opacity: style.opacity,
        };
      });
    });
    expect(
      machinery.length,
      `sections present under reduced motion at ${where}`,
    ).toBeGreaterThan(0);
    for (const section of machinery) {
      // The floor's two halves (base.module.css): collapsed duration and
      // a timeline detached from scroll progress.
      expect(
        maxDurationSeconds(section.animationDuration),
        `animation-duration under reduced motion at ${where} (${section.animationDuration})`,
      ).toBeLessThanOrEqual(COLLAPSED_SECONDS);
      expect(
        section.animationTimeline,
        `animation-timeline under reduced motion at ${where}`,
      ).toBe('auto');
      expect(
        maxDurationSeconds(section.transitionDuration),
        `transition-duration under reduced motion at ${where} (${section.transitionDuration})`,
      ).toBeLessThanOrEqual(COLLAPSED_SECONDS);
      // Content never depends on animation to appear.
      expect(
        Number.parseFloat(section.opacity),
        `section opacity under reduced motion at ${where}`,
      ).toBe(1);
    }

    // Every section heading is readable without scrolling any timeline.
    await expect(page.getByRole('heading', { level: 2 }).first()).toBeVisible();
    expectPageClean(problems, `${where} (reduced motion)`);
  } finally {
    await context.close();
  }
}

for (const testCase of CASES) {
  const key = `sf-var-${testCase.variant}`;
  const ns = specNamespace(key);

  test(`the ${testCase.variant} variant is assigned, previewed, published, and rendered with its curated theme`, async ({
    page,
    browser,
  }) => {
    test.setTimeout(420_000);

    const { businessId } = await seedPublishedStorefront(
      ns,
      {
        category: CATEGORY,
        item: ITEM,
        imageAlt: IMAGE_ALT,
        heroHeading: testCase.heroHeading,
        heroSubheading: HERO_SUBHEADING,
        storyBody: STORY_BODY,
      },
      {
        variant: testCase.variant,
        logo: true,
        theme: {
          accent: testCase.accent,
          palette: testCase.palette,
          typePairing: testCase.pairing,
        },
      },
    );

    // --- The saved-draft preview, through the authenticated workspace ---
    // ADR-022 §3: preview is the server projection of the SAVED draft
    // through the shared renderer. It must already carry the assigned
    // variant and the whole curated theme, before anything is public.
    const workspaceProblems = watchPage(page);
    await signIn(page, ns.ownerEmail, ns.ownerPassword);
    // Sign-in is another spec's subject, and the Control Center's
    // pre-authentication session probe legitimately answers 401 on the
    // way in. The preview navigation below is what this assertion is
    // about, so recording starts cleanly here.
    workspaceProblems.clear();
    await page.goto(`/businesses/${businessId}/storefront/preview`);
    await expect(
      page.getByRole('heading', { name: 'Storefront preview' }),
    ).toBeVisible();
    await expect(page.getByText(testCase.heroHeading)).toBeVisible();

    const previewTokens = await readTenantTokens(page);
    expect(previewTokens.variant, 'preview variant').toBe(testCase.variant);
    expect(previewTokens.motion, 'preview motion attribute').toBe(
      testCase.motion,
    );
    await expectPalette(page, testCase.palette, 'preview');
    expectPageClean(workspaceProblems, 'workspace preview');

    // --- The published public storefront, as an anonymous visitor ------
    const context = await visitorContext(browser);
    try {
      const visitor = await context.newPage();
      const problems = watchPage(visitor);

      const origin = storefrontOrigin(ns.slug);
      const home = await publicVisit(visitor, origin);
      expect(home.status(), 'published home status').toBe(200);
      // No unexpected redirect: the tenant host serves the tenant.
      expect(new URL(visitor.url()).origin, 'home origin').toBe(origin);

      // The structural variant the PLATFORM assigned is what renders.
      const tokens = await readTenantTokens(visitor);
      expect(tokens.variant, 'published variant').toBe(testCase.variant);
      expect(tokens.motion, 'published motion attribute').toBe(testCase.motion);

      // Preview and published agree on the design (ADR-022 §2 one
      // renderer): the same variant and the same painted palette.
      expect(tokens.variant, 'preview/published variant parity').toBe(
        previewTokens.variant,
      );
      expect(tokens.colorBg, 'preview/published palette parity').toBe(
        previewTokens.colorBg,
      );

      // The tenant-controlled theme reached the browser, including the
      // painted canvas — which only the public surface can prove.
      await expectPalette(visitor, testCase.palette, 'published /');
      await expectPaintedCanvas(visitor, testCase.palette, 'published /');
      await expectTypePairing(visitor, testCase.pairing, 'published /');
      expect(tokens.accent, 'stored accent is delivered unrewritten').toBe(
        testCase.accent,
      );
      await expectAccentTextLegible(visitor, testCase.palette, 'published /');

      // Structure, landmarks, and the §7 logo rules.
      await expectLandmarks(visitor, 'published /');
      await expectDecorativeLogo(visitor, ns.businessName, 'published /');
      await expect(visitor.getByText(STORY_BODY)).toBeVisible();

      // Keyboard reachability and a visible focus indicator that is not
      // merely declared: the outline must actually be painted.
      await visitor.locator('body').press('Tab');
      const navLink = visitor
        .getByRole('navigation', { name: 'Site' })
        .getByRole('link');
      await expect(navLink).toBeFocused();
      const focusRing = await navLink.evaluate((el) => {
        const style = getComputedStyle(el);
        return {
          outlineStyle: style.outlineStyle,
          outlineWidth: style.outlineWidth,
        };
      });
      expect(focusRing.outlineStyle, 'focus outline style').not.toBe('none');
      expect(
        Number.parseFloat(focusRing.outlineWidth),
        'focus outline width',
      ).toBeGreaterThanOrEqual(1);

      // ADR-024 §11: the 44px target floor, per variant, measured.
      await expectTargetGeometry(
        visitor,
        'nav[aria-label="Site"] a',
        `published / (${testCase.variant})`,
      );

      await expectNoAxeViolations(visitor, `published / (${testCase.variant})`);

      // Visual evidence at the ADR-023 capture geometries.
      for (const viewport of CAPTURE_VIEWPORTS) {
        await visitor.setViewportSize(viewport);
        await visitor.screenshot({
          path: `test-results/m4g-d-visual/${testCase.variant}-home-${String(viewport.width)}x${String(viewport.height)}.png`,
          fullPage: true,
        });
      }
      await visitor.setViewportSize({ width: 1280, height: 900 });

      // --- /menu, reached through the primary action ------------------
      await visitor
        .getByRole('link', { name: 'View menu', exact: true })
        .click();
      await expect(
        visitor.getByRole('heading', { name: 'Menu', level: 2 }),
      ).toBeVisible();
      await expect(
        visitor.getByRole('heading', { name: CATEGORY, level: 3 }),
      ).toBeVisible();
      await expect(visitor.getByText(ITEM).first()).toBeVisible();

      const menuTokens = await readTenantTokens(visitor);
      expect(menuTokens.variant, '/menu variant').toBe(testCase.variant);
      await expectPalette(visitor, testCase.palette, 'published /menu');
      await expect(visitor.locator('h1'), 'single h1 on /menu').toHaveCount(1);
      await expectNoAxeViolations(
        visitor,
        `published /menu (${testCase.variant})`,
      );

      for (const viewport of CAPTURE_VIEWPORTS) {
        await visitor.setViewportSize(viewport);
        await visitor.screenshot({
          path: `test-results/m4g-d-visual/${testCase.variant}-menu-${String(viewport.width)}x${String(viewport.height)}.png`,
          fullPage: true,
        });
      }

      expectPageClean(problems, `published ${testCase.variant}`);
    } finally {
      await context.close();
    }

    // --- Real-browser reduced motion (ADR-024 §9/§11) -----------------
    await expectReducedMotionNeutralised(
      browser,
      storefrontOrigin(ns.slug),
      testCase.variant,
    );
  });
}
