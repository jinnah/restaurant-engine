# ADR-024: M4G Curated Storefront Design and Motion

- **Status:** Accepted (architecture); delivery records filled per slice
  — **M4G-A delivered (2026-07-31); M4G-B, M4G-C, and M4G-D not
  started**, each still requiring its own explicit authorization
- **Date:** 2026-07-30
- **Deciders:** Product owner, principal architect

## Context

Milestone 4 is complete (ADR-023 delivery record; docs/08 Milestone 4
close-out): the composition model, administrative API, public
projection, server-rendered storefront, workspace UI, and end-to-end
verification are all delivered. What Milestone 4 deliberately did not
deliver is visual differentiation: exactly one design variant exists
(`classic`), the tenant styling surface is one arbitrary accent hex,
typography is a single system stack, no logo slot exists, and every
storefront shares one structure — differentiated only by content,
imagery, section ordering/visibility, and accent. ADR-023 §7 recorded
M4G as the proposed next slice before M5 and bounded it; this ADR is
that slice's reconciliation and architecture, grounded in a fresh
inspection of the delivered seams.

What the delivered foundation already provides, requiring no rework:
the variant lives on every version row and is preserved by snapshots
and restore (ADR-020 §3/§4); reads fail closed on unregistered stored
values; the renderer's exhaustive variant dispatch cannot ship a new
enum member without its layout arm (ADR-021 §5); preview and public
share one renderer (ADR-022 §2); the platform design-assignment API
exists (`platform_business_design_set`, M4B) — though no UI consumes
it; `schema_version` is stored per configuration precisely so a future
registry change is deliberate (ADR-020); the JavaScript budget counts
only `.js` files, so stylesheet-delivered presentation is outside the
numeric budget while the structural zero-client-JS rule and the
renderer's empty `'use client'` allowlist remain the binding motion
constraints; and the media pipeline is image-only (WebP renditions,
§10 authorization) — there is no video capability.

## Decision

### 1. Scope and product objective

M4G delivers **three production-ready curated variants** and a
**curated brand surface**, over the existing shared schemas, shared
renderer, shared preview/public components, and one deployment:

- **Classic** (existing) — warm, familiar, clear hierarchy, image-first
  static hero, minimal optional motion. Existing tenants and snapshots
  render unchanged.
- **Editorial** — premium typography scale, larger imagery, more
  spacious composition, the strongest scroll-linked storytelling,
  navigation/card/button chrome of its own.
- **Express** — compact and action-oriented: menu and primary action
  emphasized, denser spacing, minimal motion.

Variant names are product-facing and final unless review changes them.
The brand surface: **five approved accessible palettes**, **three
approved typography pairings**, **an optional tenant logo**, and
**controlled hero treatments** expressed as variant presentation — all
selected within registries, never free-form.

### 2. Ownership and governance (blueprint §12.3 applied)

- The **structural variant remains platform-assigned**: the existing
  M4B command is the only write path, and M4G builds the **first
  platform design-assignment UI** on the platform business detail page
  (the recorded ADR-016-style API-without-UI gap). Owners never submit
  a variant; the workspace continues to show it as read-only metadata.
- **Palette, typography pairing, and logo are tenant-controlled
  content** within platform-curated registries — the accent-token
  precedent, not the variant precedent. Owners **and managers** select
  them inside the saved draft: they live in the configuration's
  `theme`, are edited in the composer, travel through the existing
  full-document draft save, and are therefore versioned, published,
  archived, restored, and snapshot-preserved by the machinery that
  already exists, with no new endpoint.
- **Publication and restoration remain owner-only** (ADR-020 §7,
  ADR-022 §5). A manager may change palette, pairing, or logo in the
  draft; only an owner makes that draft public or restores an archived
  version. Staff hold no storefront capability at all. No capability,
  role, or lifecycle rule changes in M4G.

### 3. Registries and identifiers

Two new code-owned, append-only `StrEnum` registries beside
`DesignVariant` (backend `storefront` domain), published in the OpenAPI
document as closed enums so the generated client and composer consume
them without mirroring:

**`PaletteId` — five permanent values, final:**

| Value      | Character                                                       |
| ---------- | --------------------------------------------------------------- |
| `warm`     | The delivered neutral scheme, reproduced byte-for-byte; default |
| `ember`    | Deeper warm neutrals with a heavier surface contrast            |
| `slate`    | Cool grey neutrals                                              |
| `olive`    | Muted green-leaning neutrals                                    |
| `midnight` | Dark scheme: dark background, light text                        |

**`TypePairingId` — three permanent values, final:**

| Value           | Character                                                           |
| --------------- | ------------------------------------------------------------------- |
| `humanist`      | The delivered universal system stack throughout; default            |
| `serif_display` | System serif headings over the humanist body stack                  |
| `geometric`     | Tighter geometric-leaning system sans headings, wider heading scale |

These identifiers are permanent contract values, fixed here rather than
deferred: they enter the OpenAPI enum, stored configurations, and
published snapshots, so renaming one later would be a contract and data
concern, not an editorial one.

Two naming corrections were made against repository evidence rather
than taste. The earlier draft's `editorial-serif` is now
`serif_display`, because (a) **no hyphenated enum value exists anywhere
in the backend domains** — multi-word registry values are snake_case
(`view_menu`, `online_ordering`), and a hyphen would be the sole
exception; and (b) sharing the `editorial` root with the
`DesignVariant` member of the same domain would imply a coupling that
does not exist — variant and pairing are independent axes chosen by
different actors (platform versus owner/manager), and a name that
suggests otherwise would mislead every later reader. `serif_display`
names the typographic fact instead. Every other proposed identifier is
retained.

The renderer mirrors each registry with an exhaustive map pinned by
tests — the `assertNever` discipline — so a registry entry cannot ship
without its rendering tokens, and stored-value drift throws rather than
renders wrong.

### 4. Theme extension and schema evolution

`Theme` gains three **optional fields with defaults**:

```json
{
  "accent": "#a34b2a",
  "palette": "warm",
  "type_pairing": "humanist",
  "logo": null
}
```

`logo`, when present, is `{"media_id": "<uuid>"}` — a distinct
`ThemeLogo` model carrying **no `alt_text` field**, because §7 rules
the logo permanently decorative; publishing a field whose value can
never affect rendering would invite owners to write alt text the
product then ignores.

**Ruling: `schema_version` stays `1`.** Additive fields with defaults
keep every stored configuration valid: `extra="forbid"` rejects unknown
keys on submission but missing keys parse to defaults, so every
pre-M4G row reads as `palette: warm`, `type_pairing: humanist`,
`logo: null` — exactly its current appearance. This is the deliberate
decision ADR-020 reserved for the first schema change: **no schema v2,
no migration, no backfill, and no adoption workflow** — nothing rewrites
a stored configuration, and nothing asks an owner to accept a new
schema. The `Literal[1]` and its stored `schema_version` column are
untouched. A future _incompatible_ change still requires the version
bump and an explicit migrate-or-reject decision. The composition
contract (deterministic validation, byte-stable round-trip) is
preserved — the canonical dump simply gains the new keys.

### 5. Palette mechanics and compatibility

A palette is a platform-authored set of the existing `.tenantPage`
custom properties (`--color-bg`, `--color-surface`, `--color-text`,
`--color-muted`, `--color-border`) — the variables every variant and
section stylesheet already consumes. The variant layout applies the
palette's values exactly where it applies the accent pair today; no
selector structure changes.

- **Every palette ships with property-tested contrast**: each
  text-on-background combination the stylesheets use must meet WCAG AA
  (4.5:1 body, 3:1 large text) in build-time tests, because palettes
  are platform code, not tenant input.
- **The accent survives unchanged and grandfathered**: `accent` remains
  the arbitrary tenant hex it is today and **overrides only the accent
  token** — it never participates in a palette's five color tokens. No
  stored accent is rewritten, migrated, or rejected, and the delivered
  guard (`accentForeground`: black or white over an accent background,
  property-tested across the sRGB cube) is unchanged.

**Required correction — accent-as-text needs a palette-aware token.**
The delivered stylesheets use the raw tenant accent as _text_ in three
places (`base.module.css` link color, `classic.module.css` nav link,
`menu.module.css` badge) and as the focus-ring color; `accentForeground`
solves only the opposite direction (text _on_ an accent background, the
call-to-action). With one light palette this is a latent gap — a
pathological light accent already contrasts poorly on `#faf8f5`. Adding
`midnight` would make it acute, because a dark accent on a dark
background is unreadable. M4G therefore introduces one derived token,
`--accent-text`, computed by a pure helper beside `accentForeground`:
the tenant accent when it already clears 4.5:1 against the palette's
background/surface, otherwise the accent adjusted along its own hue
until it does, falling back to the palette's `--color-text` when it
cannot — property-tested across the sRGB cube for **every** palette,
exactly as the existing guard is.

`--accent-text` is **derived at render time** from the stored accent
and that version's palette, exactly as `accentForeground` is today, and
is **never persisted**: the stored configuration keeps precisely the
accent the owner chose, and changing palette re-derives the token on
the next render rather than rewriting anything. `--accent` remains the
token for **decorative fills**; text, focus indicators, and other
contrast-required uses read `--accent-text`.

**Legacy compatibility, precisely:**

- A configuration without the new fields defaults to `palette: warm`,
  `type_pairing: humanist`, `logo: null`.
- The `warm` palette reproduces the delivered five renderer color
  tokens **byte-for-byte** (`--color-bg: #faf8f5`, `--color-surface:
#ffffff`, `--color-text: #241f1c`, `--color-muted: #5f574f`,
  `--color-border: #e0dad2`), and `humanist` reproduces the delivered
  font stack and heading scale.
- The existing accent continues to override only the accent token.
- Existing drafts, published versions, archives, ordinary saves, and
  restores therefore keep their current rendered appearance; nothing
  about the composition, publication, or restore paths changes.
- No migration and no backfill are added; the Alembic head stays
  `a41d9c7e5b30`.

**One bounded qualification to the appearance guarantee**, stated
plainly rather than buried: for a stored accent that already meets the
4.5:1 floor against `warm` — which includes the platform default
`#a34b2a` (≈5.5:1) and every accent in the development and UAT data —
`--accent-text` returns the accent unchanged and rendering is identical.
Only an accent that _fails_ the floor renders differently, and only by
becoming legible. That is a deliberate accessibility floor, not a
redesign, and it is the sole appearance change M4G makes to an
untouched configuration.

### 6. Typography pairings — system stacks only

**Ruling: M4G ships no webfont.** Each pairing is a curated pair of
system font stacks (heading stack + body stack) plus a bounded scale
(heading sizes, weights, letter-spacing) delivered as custom
properties. Every stack ends in the same complex-script fallbacks the
current stack carries (Bengali among them), preserving the ADR-021 §9
Unicode posture, zero network cost, zero CLS, zero licensing or
subsetting surface, and no supply-chain change. Self-hosted webfonts
are a **recorded future decision** with their own performance,
licensing, subsetting (complex scripts included), and CLS analysis —
not part of M4G.

### 7. Tenant logo

An optional image in `theme.logo`, staged and claimed exactly like
section media (ADR-020 §10: selection stages the media reference; the
claim happens at draft save; nothing is public until publication).

**Accessibility, ruled now — not deferred:**

- **The restaurant name remains the visible, semantic `h1` in every
  variant.** No variant may replace it with an image, hide it visually,
  or demote it; the logo is placed adjacent to it.
- **The logo is decorative: `alt=""`, always.** A logo beside the name
  would otherwise produce a duplicate accessible name for the same
  fact, which is exactly the redundancy screen-reader users report as
  noise. This is why `ThemeLogo` carries no `alt_text` field (§4).
- **Missing or failed logo media falls back cleanly to the name.** An
  absent reference renders today's name-only chrome. A reference the
  viewer's browser fails to load costs nothing informational, because
  the name is always present as text and the image conveys nothing on
  its own; intrinsic dimensions from the delivered renditions reserve
  the box so the header does not shift (no CLS).
- The per-variant axe gate and the landmark/heading assertions
  (single `h1`, ADR-023 §4) cover this in a real browser for every
  variant.

**Required backend extension — the §10 predicate and claim path grow a
third leg**: an active same-business asset is publicly deliverable when
the public catalog references it, an enabled section of the current
published version references it, **or the published version's theme
references it**; the draft-save claim walks `theme.logo` exactly as it
walks section image references, and the authenticated preview includes
a pending logo like pending section media. This is a deliberate,
tested widening of ADR-020 §10; ADR-020 carries a dated amendment
pointing here, so the widened predicate is discoverable from the
governing decision it changes.

### 8. Variant and renderer structure

Editorial and Express are **layout arms plus variant-scoped
stylesheets** in `packages/storefront-renderer/src/variants/`, joining
`classic` behind the existing exhaustive dispatch. Structural rules:

- **Section renderers stay shared** — one component per section type,
  no per-variant forks. Variant-specific card, button, spacing, and
  section presentation is expressed through (a) the variant's own
  chrome, (b) custom-property tokens the variant root sets (spacing
  scale, radius, type scale), and (c) variant-root-scoped CSS. A
  variant that genuinely cannot express its presentation this way is a
  stop-and-report, not a fork.
- The backend `DesignVariant` enum gains `editorial` and `express` in
  the same change that ships their renderer arms (the registry's
  stated rule), widening the OpenAPI enum — a contract change with
  client regeneration, byte-checked; the operation count stays 66
  (schema-only change; no new endpoint).
- Preview parity is inherited: the workspace preview renders whatever
  variant the draft row carries through the same dispatch, inert-link
  mode unchanged.

### 9. Motion — CSS scroll-driven animation only

**Ruling: M4G motion is pure CSS.** Scroll-linked storytelling uses CSS
scroll-driven animations (`animation-timeline: view()`/`scroll()`)
authored inside `@supports` guards, so:

- **No client JavaScript is introduced**: the structural
  zero-client-JS budget, the error-boundary-only `'use client'`
  allowlist, and the renderer package's empty-allowlist scan all stand
  unamended; the numeric first-load JS ceiling (502,201 bytes,
  ADR-021) is untouched because motion ships in stylesheets the budget
  deliberately does not count.
- **Progressive enhancement is structural**: browsers without
  scroll-timeline support skip the `@supports` block and render the
  complete static presentation — authored so the _final_ (fully
  visible) state is the unenhanced state; content never depends on
  animation to appear. No scroll hijacking, no forced timelines, and
  no delayed menu access are possible by construction — scroll
  position remains native.
- **Reduced motion is already enforced**: the delivered
  `.tenantPage` `prefers-reduced-motion` floor zeroes all animation
  machinery, which includes scroll-driven animations; a pin test keeps
  the floor, and the M4G acceptance adds a real-browser reduced-motion
  check per variant.
- Restraint bounds are design review criteria: reveals and subtle
  transform/opacity shifts only; no motion on the menu listing's
  purchasable content; Editorial carries the strongest treatment,
  Classic and Express minimal.

**The optional 4–5-second hero loop is NOT in M4G.** The media domain
is image-only; even an administrator-prepared loop needs a delivery,
validation, poster, and fallback design the current pipeline does not
have. It remains the ADR-023 §7 recorded candidate, requiring its own
investigation and authorization, and the three variants must be
complete and attractive without it — which this design guarantees by
never depending on it.

### 10. Publication stability and retirement

Palette and pairing tokens are stored inside the version row's
configuration, so published and archived versions render with the
tokens they were published with — the variant precedent extended to the
whole visual configuration. Unknown stored tokens fail closed exactly
like unknown variants (opaque 500, bounded log; never a silent
default). Retirement rule, recorded now for all three registries: they
are **append-only; retiring an entry removes it from the _assignable_
set (writes reject it) while rendering support is retained
indefinitely** — renderable ⊇ assignable — so historical versions and
restores keep working; deleting rendering support for a stored value
is a separate, migration-bearing decision no one has proposed.

### 11. Accessibility, performance, and security bars

- **Accessibility:** per-palette AA contrast property tests
  (build-time), including the `--accent-text` derivation across the
  sRGB cube for every palette (§5); per-variant zero-violation axe
  gates on published `/` and `/menu` (the ADR-023 boundary and
  non-certification language apply verbatim); per-variant responsive
  acceptance at the six ADR-023 viewports; real-browser reduced-motion
  verification; 44 px target and focus-visibility floors pinned per
  variant; the §7 single-`h1` and decorative-logo rules axe-refereed.
- **Performance:** the first-load JavaScript ceiling (502,201 bytes)
  and the zero-new-client-JS rule are **preserved and still enforced**
  — M4G adds no client JavaScript, so both gates apply unchanged.
  System-font typography adds no requests; the logo uses existing
  renditions with intrinsic dimensions (no CLS). **No CSS threshold is
  introduced**: inventing a blocking number before any measurement
  exists would be arbitrary. Instead **M4G-B must measure and report
  per-variant CSS weight** (delivered stylesheet bytes per public
  route, per variant) in its verification, and a threshold is
  reconsidered only if the measured growth warrants one — which would
  then be its own recorded decision, as the ADR-021 budget was.
- **Security/tenancy:** no new tenant-selection path, no new endpoint,
  no cookies or client JS; palettes/pairings are closed enums (no CSS
  injection surface — tenant input never reaches a stylesheet; the
  accent continues through the existing validated token path); logo
  delivery rides the §10-extended authorization and the existing
  public/authenticated media routes; the platform assignment UI sits
  behind the existing `platform.businesses.manage` capability and the
  API remains the authority.

### 12. Implementation decomposition (each slice separately authorized)

| Slice     | Scope                                                                                                                                                                                                                                                                                                           | Depends on                                             |
| --------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| **M4G-A** | Backend: `PaletteId`/`TypePairingId` registries, `Theme` extension (§4), §10 theme-logo predicate + claim + preview extension (§7), validation and isolation tests, contract regeneration (schema-only, 66 ops)                                                                                                 | —                                                      |
| **M4G-B** | Renderer: `editorial` + `express` variants (enum + layout arms + scoped styles), palette/pairing token application, the `--accent-text` derivation (§5), logo chrome, CSS scroll-driven motion, per-variant and per-palette suites, JS-budget re-proof, **per-variant CSS-weight measurement and report** (§11) | M4G-A                                                  |
| **M4G-C** | Control center: composer palette/pairing pickers and logo staging (media-primitive adapter), preview parity, the **platform design-assignment UI**, workspace and platform tests                                                                                                                                | M4G-A (UI parts consuming M4G-B variants land after B) |
| **M4G-D** | E2E and close-out: one representative browser journey per new variant, per-variant responsive/axe/reduced-motion acceptance, visual acceptance, docs close-out                                                                                                                                                  | M4G-A–C                                                |

Verification per slice follows the standing gates; M4G-D follows the
ADR-019/ADR-023 close-out pattern. Combinatorial control: shared
section renderers tested once; per-variant tests cover layout arms and
tokens; one journey per variant; axe per variant on the two public
routes; palette × pairing coverage is a small pairwise selection, never
the full product.

### 13. Non-goals

No arbitrary tenant CSS/HTML/JS; no page builder; no theme
marketplace; no per-tenant deployments or source forks; no one-off
tenant modifications in shared components; no webfonts; no video or
customer video pipeline; no hero loop; no client-JS animation library;
no new preview surface; no M5 (hours) behavior; no change to
draft/preview/publication/restore semantics, tenant resolution, or
session/CSRF architecture.

## Alternatives considered

- **Owner-selectable variants** — rejected: blueprint §12.3 assigns
  structural variants to the platform; the governance split is a
  product asset, and the M4B command already encodes it.
- **Arbitrary palette colors (tenant-supplied hex per token)** —
  rejected: contrast becomes tenant-dependent and unverifiable at
  build time; curated palettes keep AA a platform guarantee. The
  accent remains the single arbitrary token, protected by its guard.
- **Webfont typography** — deferred (§6): performance, CLS, licensing,
  and complex-script subsetting costs exceed M4G's need; system stacks
  deliver real differentiation at zero cost.
- **JS-driven scroll animation (IntersectionObserver/scroll
  listeners)** — rejected for M4G: it would break the structural
  zero-client-JS budget and the renderer's server-component
  constraint, forcing an ADR-021 amendment for presentation the CSS
  path delivers.
- **A `business_type`/per-tenant styling table** — rejected: the
  configuration already versions the visual surface; a parallel store
  would break snapshot stability.
- **Bumping `schema_version` to 2** — rejected (§4): additive defaults
  keep every stored configuration valid; a bump would force a
  migrate-or-reject decision for zero benefit.
- **Silent fallback rendering for unknown stored tokens** — rejected:
  fail-closed is the delivered contract for variants; rendering a
  guessed palette would misrepresent a published version.

## Consequences

The OpenAPI document gains two enums and three `Theme` fields (contract
regeneration; operation count unchanged at 66). ADR-020 §10 is amended
by §7 above (theme-level media references authorize delivery). The
renderer package grows two variant directories and palette/pairing
token modules; `apps/storefront` and the workspace consume them without
structural change. The platform business detail page gains the first
design-assignment UI. Alembic head `a41d9c7e5b30` is expected to remain
unchanged (no migration in any slice). Existing tenants render
identically until a human changes something: default palette and
pairing reproduce today's presentation, and `classic` stays the
platform default variant.

## Security and operations impact

No new authentication, authorization, tenant-resolution, or caching
behavior. The §10 widening is the only authorization-adjacent change
and is tested with the same isolation matrix discipline as its M4C
predecessor (foreign, draft-only, archived-only, disabled-section, and
removed references still authorize nothing; theme references authorize
only the published version's logo). CSP posture is unchanged (CSS-only
motion; the accent custom-property inline style remains the one inline
style the M8 proxy must accommodate).

## Reconsideration triggers

Webfont typography (a future decision with subsetting and CLS
analysis); the hero loop (media-pipeline investigation); a fourth
variant or second palette family (registry growth is routine; a
_family_ restructuring is not); tenant-visible palette preview needs
beyond the existing draft preview; retirement of any registry entry
(first exercise of the §10 renderable ⊇ assignable rule); CSS weight
becoming measurable in field performance (would motivate a stylesheet
budget); M6 ordering (cart chrome must adopt variant tokens); the M8
reverse proxy (CSP interaction with scroll-driven animation is expected
to be none, but is verified there).

## Delivery record

### M4G-A — Backend theme foundation: delivered, 2026-07-31

**Delivered behavior.** The two registries of §3 ship as code-owned,
append-only `StrEnum`s with explicit named defaults, published as closed
OpenAPI enums: `PaletteId` (`warm`, `ember`, `slate`, `olive`,
`midnight`) and `TypePairingId` (`humanist`, `serif_display`,
`geometric`). They live in their own module rather than beside
`DesignVariant` in `variants.py`, because the §2 governance split is
load-bearing: the structural variant is platform-assigned, while palette
and pairing are tenant content. The §4 `Theme` extension is additive with
defaults — `palette`, `type_pairing`, and an optional `logo` whose
`ThemeLogo` carries `media_id` only — and **`schema_version` stays 1** as
ruled, with no schema v2, migration, backfill, or adoption workflow;
every configuration stored before M4G reads as `warm` / `humanist` /
`logo: null`, which is exactly its current appearance.

The §7 media work landed in full. Media-reference collection moved up to
the document level, so the theme logo is validated and claimed on the
same validate-all-before-claim path as a section image, and the
completeness invariant now covers the whole canonical document rather
than sections alone. The §10 predicate gained its third leg — a published
version's `theme` authorizes its logo — and it is genuinely independent:
authorized even when every section is disabled, while
disabled-section-only, draft-only, archived-or-superseded-only, removed,
pending, and cross-business references still authorize nothing. The
authenticated preview includes a pending theme logo through the member
media route only. Unknown stored tokens fail closed exactly as
unregistered variants do (§10): the neutral 404 on the anonymous media
route, the opaque 500 with a bounded log on the projection, never a
silent default.

Two implementation decisions are recorded because a later reader will
meet them. **The projection carries a dedicated `PublicThemeLogo`**
rather than reusing the section-image descriptor: it omits `alt_text`
entirely, so the §7 decorative ruling is structural on both the stored
and projected sides and a renderer has no null value to pass through —
**M4G-B must therefore render the logo with an explicit `alt=""` and
never omit the attribute**. And the composer now carries the loaded
draft's whole theme through an edit, because the draft PUT is a
full-document replacement (ADR-020 D-5): without it, an unrelated
heading edit would reset palette, pairing, and logo to their defaults.
The carried value lives in form state rather than being read from the
cache at save time, so a stale-write conflict cannot silently merge
cached data (ADR-022 §6).

**Verification at delivery.** Backend **1132** tests (1070 at the
Milestone 4 head, +62 for M4G-A), ruff lint and format clean, mypy strict
clean across 181 source files; api-client **95**, storefront-renderer
**52**, storefront **66**, control-center **398** (389 + 9); Playwright
**13**; workspace typecheck, lint, and format clean; `contract:check`
byte-current at exactly **66 operations** with the `paths` object and
every operation id unchanged; both production builds green; the
first-load JavaScript budget unchanged at 456,547 bytes per route
locally (456,629 in CI, the recorded platform variance) against the
502,201-byte ceiling; the built-server verification green. The Alembic
head remains `a41d9c7e5b30`. Only disposable test infrastructure was
used; the preserved development and UAT databases were neither contacted
nor modified.

**Delivery evidence.** Implementation PR #32; implementation commit
`7b7e5ed6e46e0cede5f60e4ac463a4fda5c7bc0f`; merged to `main` as
`4b695077c8d2874ab7026352b39a67585aaee9c2` with ordered parents
`04bc09861dfcfb9c8d3a3327714763dda7c6d6bd` then
`7b7e5ed6e46e0cede5f60e4ac463a4fda5c7bc0f`, the merge tree equal to the
reviewed feature-head tree. Exact-head PR CI run `30601961380` and
exact-merge-SHA push CI run `30602476429` both completed successfully
with all five jobs (repository-contract, backend, frontend, contract,
e2e) green and zero artifacts.

**Boundary.** M4G-A shipped no renderer theme styling and no public
visual change — existing storefronts render exactly as before, because
the defaults reproduce the delivered presentation and no renderer reads
the new tokens yet. The `DesignVariant` enum deliberately did **not**
gain `editorial` or `express`: §8 binds those to the change that ships
their renderer arms. No `--accent-text` derivation, palette or pairing
stylesheet, logo chrome, or motion (M4G-B); no composer pickers, logo
staging workflow, or platform design-assignment UI (M4G-C); no per-variant
acceptance journeys (M4G-D); no new endpoint, capability, role, audit
event, lifecycle rule, database column, migration, dependency, or
lockfile change. **M4G-B, M4G-C, and M4G-D remain the boundary and are
not started**, and Milestone 5 has not begun.
