# ADR-023: M4F End-to-End Storefront Journeys and Milestone 4 Verification

- **Status:** Accepted (architecture); M4F implementation in review —
  **Milestone 4 is not complete** and may be marked complete only after
  the separately authorized close-out
- **Date:** 2026-07-30
- **Deciders:** Product owner, principal architect

## Context

M4F is the last slice of Milestone 4: mandatory end-to-end journeys 2
and 3, verification, and the close-out (`docs/08_ROADMAP.md`, ADR-020).
M4A–M4E delivered the composition model, the administrative API, the
public projection, the server-rendered storefront, and the workspace UI
— and each deferred the same obligations here: the complete browser
journeys (ADR-019 D2 recorded journeys 2 and 3 as only partially
satisfied while publication did not exist), the e2e-orchestrated
storefront server (recorded at M4D), browser-level accessibility
verification (ADR-021 §10, ADR-022 §10), and the cross-host
published-versus-draft proof.

This ADR records the approved M4F architecture (discovery report,
visual-differentiation addendum, and rulings R-1–R-6, 2026-07-30). Its
decisions are binding. It follows the ADR-016/ADR-019 precedent: the
E2E/close-out slice carries its own ADR.

## Decision

### 1. The orchestrated storefront server

The E2E lifecycle owner (`e2e/scripts/orchestrator.mjs`, ADR-016) gains
a third tracked child: the storefront **development server** — the
repository's `next dev` invocation resolved from `apps/storefront`'s own
dependency tree, exactly as Vite is resolved for the control center.

- **Order is fixed:** backend → storefront → control center. The
  backend gates the storefront (which reads it per request); the
  storefront gates the control center. Each child's readiness gates the
  next spawn, so a failure attributes to the child that failed.
- **Port 3100, bound explicitly to `127.0.0.1`** (`-p 3100 -H
127.0.0.1`). The port joins the preflight refusal list beside 8100
  and 5273; it collides with no known local service (dev storefront
  3000, UAT 8000/5173, PostgreSQL 5433).
- **`STOREFRONT_API_ORIGIN=http://127.0.0.1:8100`** is constructed by
  the orchestrator, never inherited: the variable's development default
  (`:8000`) is the preserved development backend and must be
  structurally unreachable from an E2E run — the same rule as
  `DATABASE_URL` and `MEDIA_STORAGE_ROOT`.
- **Answering readiness, storefront only.** A bare-loopback probe of
  the storefront legitimately answers the neutral 404 — `127.0.0.1`
  resolves no tenant by design (ADR-013) — so the storefront's
  readiness accepts an answering **200 or 404** through a separate
  poll. The backend and control center keep their strict-ok readiness
  unchanged, and the orchestrator's unit suite proves the answering
  poll never sees their URLs.
- **`next dev`, never `next build`/`next start`, and no proxy.** The
  E2E stack runs dev servers (the Vite precedent); production wire
  behavior — headers, statuses, Host forwarding, render cost, budget —
  is already owned by `pnpm storefront:verify` and
  `pnpm storefront:budget` against the built server in the frontend CI
  job. Dev mode also keeps the development `/api` forwarder active
  (ADR-021 §4), so the projection's relative media URLs resolve on the
  tenant origin with no additional topology.
- **Everything else is inherited unchanged:** tracked-process-tree
  shutdown (taskkill /T on Windows, process groups on POSIX; never a
  port or name sweep), single-shot cleanup shared by success, failure,
  timeout, and signal, the disposable database and media root, and the
  `pnpm e2e` entry point — so **CI needed no change**; the e2e job
  already runs the identical command.
- Playwright learns the rendered-storefront origin through
  `E2E_STOREFRONT_PORT`, mirroring `E2E_PUBLIC_PORT`;
  `support/namespace.ts` composes `http://{slug}.localhost:3100`. Every
  public visit remains a **browser navigation** (Chromium resolves
  `*.localhost` itself, RFC 6761; the OS resolver on Windows does not —
  the measured ADR-019 rule).

### 2. The functional storefront journey

One cohesive spec (`e2e/tests/storefront.spec.ts`) completes mandatory
journeys 2 and 3 and the full cross-host published-versus-draft
contract, entirely through the rendered UI and documented HTTP
(black-box, ADR-016):

owner reaches the workspace → composes a draft carrying **all five
registered section types** through the section dialogs (library imagery
staged and claimed at save, ADR-020 §10) → explicit Save Draft →
saved-draft preview through the shared renderer with structurally inert
links (ADR-022 §3) → the unpublished draft is **not** on the public
host → publish version 1 → a fresh anonymous visitor sees version 1
rendered under the tenant host (`/` and `/menu`, delivered media proven
by loaded image bytes, featured item composed from the live menu) → the
draft is edited and saved again and the public host **still** renders
version 1 → publishing version 2 archives version 1 → the public host
renders version 2 → history presents version 2 published and version 1
archived → archived version 1 is restored into the draft through the
Control Center → restoration publishes nothing (the host still renders
version 2) → the restored draft is explicitly published → the public
output again semantically matches version 1 → suspension hides the
published site behind the neutral 404 → reactivation restores exactly
the same published output. A second active-but-never-published business
proves the rendered surface separates hosts.

**The second publication is mandatory, not optional:** restoration
accepts archived sources only (ADR-020 D-4), and archived rows exist
only after a second publication — so any UI-driven restoration proof
structurally requires publishing twice.

Assertions are **semantic**: headings, landmarks, text, link targets,
image delivery, version/state labels. No full-page screenshot gates, no
pixel comparison, no renderer imports, no timing sleeps — state changes
are observed through fresh cookie-less visitor contexts (which also
defeat the public 60-second cache, ADR-020 §12). Prerequisites that are
not this journey's subject (active businesses, the photographed menu
item, featured status) are built through the established authenticated
API fixtures.

### 3. Responsive verification for `classic`

Mobile responsiveness is an explicit M4F acceptance requirement for the
production-renderable `classic` storefront, in two layers over a
published five-section fixture with a deliberately long business name,
heading, and body copy:

- **Automated** (`e2e/tests/storefront-responsive.spec.ts`): `/` and
  `/menu` at **320×900, 375×812, 390×844, 430×932, 768×1024, and
  1280×900** — no horizontal document overflow, identity and headings
  visible and unclipped, sections stacked without overlap, images
  inside the viewport with delivered bytes and sane proportions,
  primary navigation and the primary action operable at every width
  (the menu page is reached by activating the hero action), exact
  section order and visibility, and a 14 px body-text readability
  floor. Semantic and geometric assertions only.
- **Manual visual acceptance** at **320×900, 390×844, 768×1024, and
  1280×900** for both routes: screenshots are captured into the
  gitignored Playwright results directory as **disposable inspection
  evidence** — never committed baselines, never a pixel gate — and
  inspected for overlap, clipping, readability, wrapping, distortion,
  obscured actions, and compressed-desktop mobile layouts.

Passing this matrix is evidence for these widths and this content; it
is **not** proof of support for every possible device. A responsive
defect discovered here is a stop-and-report, never an in-scope repair.

### 4. Browser accessibility verification

One spec (`e2e/tests/storefront-a11y.spec.ts`) over the smallest
deterministic published fixture exercising all five section types, with
one new dependency:

- **`@axe-core/playwright` 4.12.1, exact-pinned, development-only, in
  the e2e package.** The lockfile gains exactly
  `@axe-core/playwright@4.12.1` and `axe-core@4.12.1`, peer-resolved
  against the already-pinned `playwright-core` 1.61.1. No
  application/runtime package changes; upgrades are deliberate commits.
- **Page/state set:** published public `/`, published public `/menu`,
  the workspace overview/composer, the composer with a section-edit
  dialog open, the saved-draft preview, history, and version detail.
- **Policy:** scans run the WCAG 2.0/2.1 A and AA rule tags and are
  **blocking at zero violations**, with **no blanket exclusions** — no
  pre-authorized rule, selector, component, or region exclusions exist.
  A discovered violation is a stop-and-report (exact rule, impact,
  page/state, target, failure summary, likely defect) before any
  application change or exclusion.
- **Focused semantic checks** cover what the scan does not judge: a
  single h1 and the four committed landmarks (ADR-021 §10), keyboard
  reachability of the primary navigation, and real-browser dialog focus
  (focus enters the dialog on open; Escape closes it and returns focus
  to the invoking control) — exactly the behavior jsdom could not
  prove (ADR-022 §10).
- **Claims boundary:** automated engines detect only a subset of
  accessibility defects; no screen-reader behavior is verified, and
  per-tenant document language remains unmodeled (ADR-021 §9). A pass
  is engineering evidence within this boundary — it is **not WCAG
  certification, not complete accessibility compliance, and not proof
  that no accessibility defects exist**.

### 5. Milestone 4 exit-criteria verification map

The blueprint §19 exit criteria map to evidence as follows; the map is
the close-out's checklist, not a completion claim:

| Exit criterion                    | Evidence                                                                                                                        |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Invalid config cannot save        | Backend validation suites (M4A/M4B, in the 1070) and the workspace 422-mapping suites (ADR-022 §7)                              |
| Published config always renders   | Renderer exhaustiveness and fail-closed suites, `pnpm storefront:verify`, and the journey's rendered public assertions          |
| Draft is never public             | M4C projection/preview suites and the journey's pre-publication, post-edit, and post-restore public assertions                  |
| Performance/accessibility budgets | `pnpm storefront:budget` + `pnpm storefront:verify` (CI, unchanged) plus the §3 responsive matrix and §4 accessibility boundary |

### 6. Non-goals

M4F changes **no** application or runtime behavior: no backend, control
center, storefront, or shared-renderer code, no database model or
migration (Alembic head `a41d9c7e5b30` unchanged), no API or OpenAPI
change (contract stays 66 operations), no publication-model change, no
CI workflow change, no production media handling change, and no
host-isolation change. It implements no new design variant, no
variant-selection or palette/typography/logo UI, no hero video, no
scroll-linked animation, no tenant CSS/HTML, no page builder, and no
M5+ behavior. It fabricates no non-default variant: exactly one
production-renderable variant (`classic`) exists, and the journeys use
it with realistic tenant-specific content.

### 7. The recorded M4G boundary (future work, not authorized here)

Visual differentiation is real but thin today: one variant, one
arbitrary accent token, no typography choice, no logo slot, no video —
every storefront shares one structure, differentiated by content,
imagery, ordering, visibility, and accent (the M4F addendum's
inventory). The intended next product slice after M4F is:

**M4G — Curated Storefront Design and Motion**, planned **before M5**,
subject to its own formal roadmap reconciliation, discovery, and
authorization after M4F closes. Nothing in M4F implements or
pre-commits any of it. Its recorded objective:

- **Three production-ready curated variants total** (proposed names,
  unconfirmed until M4G discovery): **Classic** (warm, familiar, clear
  hierarchy, image-first or static hero, minimal optional motion),
  **Editorial** (premium typography, larger imagery, spacious
  composition, the strongest scroll-linked storytelling, optional
  lightweight looping hero enhancement), and **Express** (compact,
  action-oriented, menu-and-ordering emphasis, faster and denser,
  minimal motion).
- **Controlled customization to evaluate:** four to six approved
  accessible brand palettes; a small approved typography-pairing
  registry; tenant logo support; controlled hero-image treatments;
  variant-specific layout, spacing, card, button, navigation, and
  section presentation — over the existing section ordering/visibility,
  restaurant content and imagery, one shared storefront application,
  one shared renderer architecture, shared section schemas where
  possible, and the existing draft/preview/publication/version/
  restoration/snapshot behavior unchanged.
- **Motion priority: scroll-linked animation** — motion tied to normal
  scroll progress; restrained reveals; subtle media scale, depth,
  position, or opacity changes; smooth section transitions; **no**
  scroll hijacking, forced timelines, or blocked menu access; content
  never requires animation to be understood; progressive enhancement
  with a fully usable no-JS experience; reduced or disabled motion
  under `prefers-reduced-motion`; mobile simplification; performance
  budgets and layout stability preserved. Animation enhances a variant;
  it never defines whether the storefront works.
- **Optional lightweight hero loop, secondary:** if separately
  approved, a subtle 4–5-second seamless muted inline loop with a
  poster, a static-image fallback, a reduced-motion fallback, and a
  mobile-specific smaller asset or static poster — professionally
  prepared, never required of owners, never load-bearing for a
  variant's identity, and **no large cinematic background video and no
  audio**. The business need may be fully met by scroll animation and
  static imagery; the loop must not block the three variants.
- **Media-pipeline boundary:** a simple optional loop does **not**
  authorize a customer-managed video platform. Arbitrary customer video
  upload, large-file workflows, transcoding, multi-resolution/bitrate
  delivery, poster generation, video scanning, quotas, lifecycle
  cleanup, and general video asset management all remain outside M4G
  unless separately investigated and authorized. If an
  administrator-prepared loop cannot safely use the existing media
  architecture, M4G proceeds with static imagery, CSS/browser-native
  progressive motion, and scroll animation, plus a future-compatible
  media contract where justified.
- **Quality obligations:** responsive and accessibility acceptance for
  every real variant, reduced-motion behavior, keyboard usability,
  mobile performance constraints, no horizontal overflow at supported
  widths, static fallbacks, deterministic preview/public parity,
  published-snapshot preservation of the selected visual configuration,
  safe behavior for unknown or retired variants, and compatibility for
  existing `classic` restaurants and historical snapshots. Test growth
  is bounded by shared renderer contracts, per-variant contract tests,
  one representative journey per variant, narrow-width and long-content
  boundary cases, a small pairwise configuration matrix, and focused
  reduced-motion checks — never an exhaustive palette × typography ×
  layout × section-order product.
- **M4G must not introduce:** arbitrary CSS or HTML, a drag-and-drop
  page builder, a theme marketplace, separate deployments per
  restaurant, per-restaurant source branches, or one-off tenant
  modifications in shared components.

The persistence architecture is already variant-ready (variant on the
version row, snapshot and restore preservation, fail-closed unknown
values — ADR-020/021/022), so M4G is registry, renderer, contract-enum,
assignment-UI, and test work; it requires its own ADR when implemented.

### 8. Close-out mechanics

M4F follows the established two-PR pattern: the implementation PR
(this work plus this ADR) and, after it is reviewed, exact-head CI
passes, it is merged SHA-bound, and exact-merge-SHA CI passes, a
**separately reviewed docs close-out PR** performs the roadmap,
architecture, domain-rules, and test-strategy reconciliation and marks
Milestone 4 complete. Until that close-out merges and is verified,
**M4F is not delivered and Milestone 4 remains in progress.**

## Alternatives considered

- **Production build + `next start` in the E2E stack** — rejected: it
  duplicates the wire verification `storefront:verify` already owns,
  adds a build to the e2e path, and (with the dev forwarder
  production-disabled) breaks same-origin media unless the orchestrator
  also grows a reverse proxy — a fourth process for no added proof.
- **An orchestrated same-origin proxy** — rejected with the above: more
  lifecycle surface, no additional evidence.
- **Screenshot baselines or pixel gates for responsiveness** —
  rejected: brittle against font and platform rendering, and the M4E
  precedent already proved pixel identity where it mattered; geometry
  and semantics are the durable assertions.
- **Report-only accessibility scans** — rejected: a report nobody must
  act on decays; zero-violation blocking with stop-and-report keeps the
  gate honest.
- **Pre-authorized axe exclusions** — rejected: every exclusion is a
  decision, and decisions are made on evidence, not in advance.
- **Splitting the journey into per-step tests** — rejected: the steps
  are one business narrative over one tenant's evolving state; separate
  tests would either share state (order coupling) or rebuild it
  repeatedly for no added proof.
- **Exercising a second design variant in M4F** — rejected: none
  exists; testing a fabricated variant would prove nothing about the
  product (the M4B stand-in already proves the assignment mechanics).

## Consequences

`pnpm e2e` now starts three servers and runs thirteen tests across eleven
spec files; the orchestrator regression suite grows from 24 to 29
cases. The e2e package gains its second registry dependency
(`@axe-core/playwright`, dev-only, exact-pinned). CI is unchanged — the
e2e job runs the identical entry point. Journeys 2 and 3 are
completable and completed at the automation level; the close-out PR
records them and the Milestone 4 exit criteria after review. A known
cosmetic side effect: any `next dev` run (including this stack) rewrites
the generated `apps/storefront/next-env.d.ts` route-types reference in
the working tree — the same effect `pnpm dev` has always had; the file
is generated, gitignore-adjacent by nature, and restored rather than
committed.

## Security and operations impact

No authorization, tenancy, CSRF, cookie, host-guard, or CORS behavior
changes. Tenant selection on the rendered surface remains Host-only,
proven end to end from a real browser; the storefront's E2E API origin
is constructed so the preserved development backend is unreachable; all
test data lives in the disposable database and media root and is
dropped/removed on every exit path. The public-repository artifact
policy (ADR-016) is untouched: responsive screenshots land only in the
gitignored local results directory and are never uploaded; CI keeps
uploading only secret-scanned `error-context.md` files on failure.

## Reconsideration triggers

M4G (curated variants and motion — the §7 boundary, its own ADR); M5
hours (journey content gains structured hours); M6 ordering (journeys
4–5 arrive, and the cart is the first real client-JS surface the a11y
boundary must grow to cover); the M8 reverse proxy and staging suite
(the critical Playwright suite against staging); parallel E2E workers
(per-worker databases, media roots, and ports); axe-core upgrades (a
deliberate pin bump revalidating the zero-violation gate); a WCAG 2.2
rule-boundary decision; per-tenant document language (unlocks
screen-reader verification the current boundary excludes).
