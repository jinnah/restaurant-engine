# 06 — Test Strategy

Summarizes blueprint §15. The blueprint is authoritative.

## Current state (M5B — delivered 2026-08-02)

M5B adds the public availability projection's coverage (ADR-025) at the
API and isolation layers. The backend suite grows from **1,228** to
**1,240** and the api-client suite from **106** to **109**; every other
suite is unchanged — M5B ships no UI, so no browser-level coverage was
added (deliberately M5C–M5E).

- **The public contract, host-first.** The neutral-404 matrix covers
  unknown hosts, every non-active lifecycle state, reserved labels, the
  apex, deep subdomains, IP literals, and malformed hosts — one
  indistinguishable answer. The public-surface invariant test covers the
  new route automatically (every registered public GET/HEAD route must
  carry the resolver dependency).
- **The honest empty state.** An active business with no configured
  hours answers 200 with `is_open_now: false`, an empty weekly schedule,
  no upcoming exceptions, and disabled pickup — and the read provably
  writes no fulfillment row.
- **Derived from structured settings.** An around-the-clock schedule is
  open now with a real close instant; a closed-today exception (seeded
  for today _and_ tomorrow in the tenant-local calendar, so the
  assertion cannot flip at local midnight) defeats the weekly schedule
  and surfaces the D6 note; pickup facts follow the stored policy;
  the exception window is forward-only and bounded (past overrides and
  far-future ones are absent). Every fixture is time-robust by
  construction — instant-exact DST facts stay at the unit layer and the
  member preview probe, never re-derived from the wall clock here.
- **Never cacheable (ruling D4).** `Cache-Control: no-store` is pinned
  on the success and the neutral 404 alike; the HEAD companion answers
  bodiless.
- **Isolation.** Two hosts answer only their own schedules (asserted in
  the table as well as through the API); suspension hides availability
  publicly while the rows survive intact.
- **Facade coverage.** `public.getAvailability()` with an injected
  fetch: no tenant-selection input of any kind, the typed payload, the
  neutral 404 narrowing, and network failure.

**The failed M5B merge run, recorded plainly.** Exact-merge CI run
`30732209402` failed twice (attempts 1 and 2) in the pre-existing
storefront-design-assignment isolation journey — a connection-level SSR
fetch failure before any request reached the backend, on the same
runner image and Node version as the passing exact-head run of the
identical tree. The best-supported cause (stated as such, not proven)
is the undici idle-socket reuse window racing uvicorn's default
5-second keep-alive timeout after a quiet gap in SSR traffic.
Corrective PR #44 gives the orchestrated E2E backend
`--timeout-keep-alive 75` — no assertion weakened, no retry added, no
production change — and the suite passed on the corrective's exact-head
and exact-merge runs. **Fourth retained risk:** if the signature
reappears with the flag in place, that reading is falsified and the
investigation reopens.

The other three retained risks stand unchanged: the dirty-navigation
failure from run `30652179044` remains unexplained; the earlier local
E2E non-zero exit remains unidentified; the accent-sweep 15-second
allowance remains unexercised.

## Earlier state (M5A — delivered 2026-08-01)

M5A adds the hours domain's coverage (ADR-025) at the unit, service,
API, and isolation layers. The backend suite grows from **1,132** to
**1,228** and the api-client suite from **95** to **106**. The
storefront-renderer (146), storefront (70), control-center (439), E2E
orchestrator (43 tests, one Windows-symlink skip), and Playwright (23)
suites are unchanged — M5A ships no UI and no public endpoint, so no
browser-level coverage was added (deliberately M5C–M5E).

- **The DST contract, proven exhaustively at the pure layer.** The
  timekeeping and availability modules take `now` as an argument, so
  every case is deterministic: every minute of the New York
  spring-forward gap resolves to the gap's end for both boundary kinds;
  fall-back openings take the earlier occurrence and closings the later
  (the whole repeated hour asserted one hour apart); overnight intervals
  spanning each transition have their real length; an interval entirely
  inside a gap never exists, and its next real occurrence is found; the
  matrix runs the same rules through America/Phoenix (no transitions),
  Australia/Sydney (southern-hemisphere dates), and Australia/Lord_Howe
  (a thirty-minute shift), so no hour-granularity or northern-calendar
  assumption survives.
- **Precedence and the calendar.** An exception replaces its date's
  weekly schedule entirely (closure over an open weekday, special hours
  over a closed one, replace-not-merge); an overnight interval survives
  the _next_ day's closure and dies with its own service day's; "today"
  is the tenant-local date, asserted on both sides of a UTC midnight;
  next-opening searches cross multi-day closures, week wraps, and the
  year boundary, and a business with no hours terminates with none.
- **Pickup-slot rules.** Lead time pushes the first slot onto the grid;
  before opening the first slot is the opening; the cut-off blocks the
  end of service exactly (a slot landing on the boundary is valid);
  `max_days_ahead` counts service days; slots step evenly in real time
  across a fall-back transition; enumeration honours its limit.
- **Full-set replacement semantics through the API.** The weekly PUT
  round-trips canonically from a scrambled payload, replaces exactly,
  accepts the empty schedule, rejects same-day and cross-midnight
  overlaps (a Sunday overnight is checked against Monday) while touching
  intervals pass, enforces the per-day limit and the minute bounds, and
  suppresses the exact no-op — asserted by audit-row count, not by
  response shape. The per-date exception PUT stores special hours and
  closed-all-day distinctly, normalizes and bounds the D6 note, enforces
  the tenant-local editable window as a service-level 422 with the
  window in `details`, and deletes to a 404 when nothing exists.
- **Fulfillment defaults, materialization, and bounds.** A read without
  a stored row projects the documented defaults with
  `is_configured: false` and provably writes no row; the first write
  materializes; the second identical write audits nothing; every bound
  is schema-enforced and partial documents are rejected.
- **Authorization, lifecycle, and isolation.** Every member role reads
  (ruling D7); owner and manager write; staff writes are 403; nonmembers
  — including platform administrators — get 404 for reads and writes
  alike; a closed business answers every mutation with 409
  `invalid_state` while staying readable; provisioning and suspended
  businesses stay editable; hours rows never cross tenants (asserted in
  the table, not just the API) and survive suspension intact.
- **The preview probe and the timezone command.** The member preview at
  an injected instant proves the pure core is wired end to end (the
  spring-forward close observed through the API); naive instants are 422. The platform timezone command changes the zone, audits both
  values, suppresses the exact no-op, refuses unknown zones, closed
  businesses, and missing businesses — and a preview at the same instant
  flips from open to closed when the zone moves west, proving the
  re-interpretation is real.
- **Facade coverage.** The `hours` group and `platform.setTimezone` are
  covered with an injected fetch: request shape (method, path, CSRF
  header, body, query), the defaults-projected fulfillment payload, the
  window-rejection envelope with its details, and network failure.

Deliberate limits, recorded plainly. The pickup-slot service has **no
consumer until M6** — its proof is the unit suite and the preview probe,
not a checkout. No browser-level evidence exists for any hours surface
(M5C–M5E own it). The three retained risks stand unchanged: the
dirty-navigation failure from run `30652179044` remains unexplained; the
earlier local E2E non-zero exit remains unidentified; the accent-sweep
15-second allowance remains unexercised.

## Earlier state (M4G-D — delivered 2026-08-01)

M4G-D adds the per-variant browser and visual acceptance layer (ADR-024
§11/§12) as a test-only change: `pnpm e2e` grows from **13** to **23**
Playwright tests through four new specs and three new support modules,
all under `e2e/`. Every other suite is unchanged — backend (**1,132**),
api-client (**95**), storefront-renderer (**146**), storefront (**70**),
control-center (**439**), E2E orchestrator (**43** tests, 0 failed, one
Windows-symlink skip) — because M4G-D changes no application behavior.

- **One representative journey per variant.** classic (warm × humanist),
  editorial (midnight × serif_display), and express (ember × geometric)
  each travel the governance split end to end: the platform assigns the
  structural variant through the documented command, the owner saves a
  draft carrying palette, pairing, accent, and a staged logo, the
  authenticated preview renders the saved draft with the same variant
  and painted palette, publication makes it public, and a fresh
  anonymous visitor under the tenant host receives exactly that design.
  The rendered `h1` is asserted as the variant's own base multiplied by
  the pairing scale, and the stored accent is delivered unrewritten.
- **The `--accent-text` derivation, observed.** The token is asserted to
  clear the AA body floor against the palette background and surface on
  every journey — `midnight` deliberately seeded with an accent that
  cannot pass unadjusted, so the derivation is genuinely exercised.
- **Per-variant accessibility floors.** Blocking zero-violation axe
  scans (the ADR-023 WCAG 2.0/2.1 A/AA boundary, no exclusions) on
  published `/` and `/menu` for all three variants; the four landmarks;
  the business name as the single visible `h1` with the decorative logo
  beside it carrying a literal empty `alt` and no accessible name;
  keyboard reachability with the focus indicator asserted actually
  painted; and the 44 px navigation target measured per variant. A pass
  remains engineering evidence within the stated boundary — not WCAG
  certification, not complete accessibility compliance, and not proof
  that no defect exists.
- **Real-browser reduced motion, per variant.** Under
  `prefers-reduced-motion: reduce`, every section's animation duration
  is collapsed and its scroll timeline detached, and the content is
  fully visible — the unenhanced state the M4G-B keyframes terminate
  at, now proved where jsdom could not.
- **Per-variant responsive acceptance.** editorial and express run both
  public routes at the six ADR-023 viewports through the same geometric
  floors as the delivered classic matrix — the floors moved verbatim to
  `e2e/support/layout.ts` so both matrices assert one definition — with
  the capture subset recorded as disposable per-run evidence, never a
  committed baseline or pixel gate. classic's six-viewport matrix is
  unchanged and still passes.
- **The pairwise palette × typography selection.** Five combinations
  cover all five palettes and all three pairings (the §12 selection,
  never the fifteen-cell product), including both §7 logo-absence
  branches: no logo renders name-only chrome, and a logo whose bytes
  are refused at the transport layer costs nothing informational.
- **Assignment, authorization, and isolation in the browser.** The
  design-assignment UI journey proves assignment is not publication —
  the public site changes only after the owner publishes — and the
  same-variant exact no-op is never described as a change; a
  non-administrator never reaches the panel and the command is proved
  never called; two tenants assigned different variants render only
  their own design from one browser context.
- **Hygiene as a gate.** Console errors, uncaught page errors,
  transport failures, and unexpected 4xx/5xx responses recorded per
  navigation fail the affected test. The sole standing exclusion is the
  exact path `/favicon.ico`, which Chromium requests speculatively and
  nothing in the application references; recording is explicitly
  cleared after sign-in because the control center's pre-authentication
  session probe legitimately answers 401.

Deliberate limits, recorded plainly. Screenshots are disposable per-run
evidence; passing this matrix is evidence for these widths, themes, and
content, not proof of every device, composition, or browser behavior.
Editorial's full-page home captures photograph below-viewport sections
at their pre-entry reveal state (scroll-driven animation holds
never-entered sections at their first keyframe while the capture
photographs beyond the viewport); the suite asserts the content's
presence, order, and geometry directly, and the reduced-motion checks
prove the fully visible unenhanced state. The three retained risks
stand: the dirty-navigation failure from run `30652179044` remains
unexplained and still has no browser coverage (ADR-024 assigns none to
M4G-D); the earlier local E2E non-zero exit remains unidentified; and
the accent-sweep 15-second allowance — a Vitest unit test unreachable
from the browser suite — remains unexercised.

## Earlier state (M4G-C — delivered 2026-07-31)

M4G-C adds the control-center and platform slice's coverage (ADR-024) at
the component and integration layers, through the real route table and an
injected client. The control-center suite grows from **398** to **439**.
The backend (**1,132**), api-client (**95**), storefront-renderer
(**146**), storefront (**70**), E2E orchestrator (**43** tests, 0 failed,
one Windows-symlink skip), and Playwright (**13**) suites are unchanged —
M4G-C adds no browser-level acceptance, which is deliberately M4G-D.

- **Brand controls, driven through the real composer.** First-use
  defaults and a stored non-default theme both initialize the palette,
  typography, accent, and logo controls; every registered palette and
  pairing is offered, each described in words so colour is never the only
  cue; and changing a picker marks the draft dirty and blocks publishing.
- **The whole theme on every save.** The full-document draft PUT is
  asserted to carry `accent`, `palette`, `type_pairing`, and `logo`
  together, including several changed in one session. A stored logo
  survives an unrelated brand change, a legacy accent-only configuration
  still round-trips, and a successful save resets to the
  server-normalized pristine baseline.
- **Registry equality, pinned to the contract.** The palette and
  typography choices the composer offers are asserted equal to the
  published `PaletteId` and `TypePairingId` enums, in the renderer's
  registration order, so a registry member added to the backend but never
  surfaced — or offered but not published — fails here.
- **Logo staging reuses the delivered media behaviour.** Choosing stages
  the reference and performs no draft write; replacing swaps it; removing
  clears it without deleting or unclaiming the asset; cancelling leaves
  the draft untouched; an upload failure is reported inside the dialog
  and can be retried. Pending honesty and the claim-on-save contract are
  asserted in the logo's own wording.
- **The logo placement is permanently decorative.** Its picker is
  asserted to offer no describe/decorative choice, no description field,
  and no radio at all, and to confirm on a selected asset alone; the
  staged thumbnail carries a literal empty `alt`. A companion regression
  proves the section-image picker still _requires_ the description
  choice, so the shared primitive did not change for its other consumers.
- **Expired staged media is not a stale write.** A `409 invalid_state`
  from the claim path is asserted to render the server's message in the
  form summary while preserving every brand value and the staged
  reference, and explicitly **not** to enter the stale-draft conflict
  state — which a genuine `409 conflict` still does, with all values
  preserved.
- **Error routing by exact path.** A field error at
  `body.config.theme.palette` and one at `body.config.theme.logo.media_id`
  each land on the control that owns it and are asserted absent from the
  persistent summary, while the service-level media rejection — a general
  422 carrying `media_ids` and no field error — stays in the summary and
  is attributed to nothing, because that response is indistinguishable by
  design.
- **Saved-draft preview parity.** A projection carrying a non-default
  palette, pairing, accent, logo, and an `editorial` structural variant is
  asserted to reach the shared renderer with the tokens the renderer
  itself resolved, the platform-assigned layout arm, and the logo served
  from the authenticated member media route with a literal empty `alt`; a
  null logo renders name-only chrome. The caption stating that preview
  shows only the **saved** draft is pinned, because **no unsaved live
  preview exists**.
- **Platform design assignment.** The three variants are offered with
  none preselected and the action disabled until one is chosen; the
  confirmation states its three conditions; exactly one command is sent
  with the CSRF token and no lock version; and the three acknowledgements
  are asserted separately — first-draft creation, an actual variant
  change, and the **same-variant exact no-op, which is asserted never to
  be described as a change**.
- **Capability, role, and failure boundaries.** A closed business gets
  readable values with no editable control; a manager may edit but has no
  publish action; staff never reach the composer and no storefront
  request is made for them; a non-administrator never reaches the design
  panel and the assignment command is never called. 403, 404, and
  `409 invalid_state` on assignment are each rendered through the page's
  focused error panel, and double submission is prevented while pending.

Deliberate limits: M4G-C claims no browser-level evidence. The complete
per-variant real-browser responsive, axe, reduced-motion, target-geometry,
and visual-acceptance matrix — and the M4G overall close-out — remain
**M4G-D**.

**The exhaustive accent sweep's timeout, recorded plainly.** The first
exact-merge-SHA run of the M4G-C implementation failed on the
pre-existing M4G-B `midnight` 140,608-point sweep, which exceeded
Vitest's default 5,000 ms per-test limit — a timeout, not an assertion
failure, on a tree byte-identical to the one that had just passed. The
property was **not** weakened: it was not sampled, split, retried,
skipped, or quarantined, and the input space, loop bounds, production
calls, and assertion are unchanged. Only that one test received a
15-second allowance, so every other test in the package keeps the 5,000 ms
default and a genuine hang there still fails. PR #37 carried that single
change and restored a green `main`. **Neither successful corrective run
exercised the new allowance** — the sweep finished under the old limit on
both runners — so runner variability and latent nondeterminism remain
retained risks rather than excluded explanations. The separate
dirty-navigation failure and the earlier local E2E non-zero exit likewise
remain unresolved and unexplained.

## Earlier state (M4G-B — delivered 2026-07-31)

M4G-B adds the renderer slice's coverage (ADR-024) at the unit,
component, policy, and build-measurement layers. The storefront-renderer
suite grows from **52** to **146** and the storefront suite from **66**
to **70**; a new **13**-case CSS-measurement regression suite ships
beside the measurement command. The backend (**1132**), api-client
(**95**), control-center (**398**), orchestrator (**42** passed with one
Windows-symlink skip), and Playwright (**13**) suites are unchanged —
M4G-B adds no browser-level acceptance, which is deliberately M4G-D.

- **Per-palette contrast, proved at build time.** Every text-on-
  background pairing the shipped stylesheets actually use is enumerated
  and asserted against WCAG AA for all five palettes, because palettes
  are platform code rather than tenant input. `warm` is pinned equal to
  the delivered five colour tokens and `humanist` to the delivered stack
  and scale, so an untouched configuration cannot drift.
- **`--accent-text`, proved rather than sampled.** Termination is
  established analytically: for each palette the preferred direction's
  exact endpoint is asserted conformant, so the derivation resolves for
  every sRGB input. On top of that proof the suite sweeps a 4,096-point
  cube per palette, a 140,608-point sweep on the hardest palette, and a
  full 360-point hue sweep at maximum saturation, plus identity,
  black/white, rounding-edge, hue-preservation, determinism, and the
  fallback branch. The stored accent is asserted unchanged whenever it
  already conforms.
- **Accessibility invariants per variant.** The four landmarks, the
  fixed heading hierarchy, the business name as the single visible `h1`,
  the logo's literal `alt=""` (present and empty, with no accessible
  name that could duplicate the `h1`), name-only fallback, inert-preview
  link parity, and the 44 px navigation target are asserted for
  `classic`, `editorial`, and `express` alike.
- **Motion policy as authoring rules.** jsdom runs no animation, so the
  suite pins what makes the enhancement safe by construction: every
  motion declaration inside an `@supports` scroll-timeline guard, every
  keyframe terminating at the unenhanced visible state, purchasable menu
  content never animated (the menu section excluded explicitly and the
  `/menu` listing structurally out of reach), Express at zero motion,
  and the reduced-motion floor intact with its scroll-timeline
  detachment. Real-browser reduced-motion and scroll behaviour remain
  M4G-D.
- **Measurement integrity, not size.** The CSS command enforces no
  threshold by decision, so its regression suite pins the ways it could
  mislead instead: absent build output, malformed or unexpected
  manifests, an unresolved `/` or `/menu`, a missing referenced asset,
  and duplicate references counted twice each exit non-zero, while a
  successful run reports exactly one delivered row per route and
  variant, labels authored bytes diagnostic, and still succeeds on a very
  large stylesheet. Every case runs against disposable temporary
  fixtures and never reads the repository's production build.

Deliberate limits: M4G-B claims no browser-level evidence. The
per-variant responsive, axe, real-browser reduced-motion, and visual
acceptance matrix — and the M4G overall close-out — remain **M4G-D**;
the control-center pickers, logo staging, and platform design-assignment
UI remain **M4G-C**.

## Earlier state (M4G-A — delivered 2026-07-31)

M4G-A adds the curated-theme foundation's coverage (ADR-024) at the
unit, service, and isolation layers. The backend suite grows from
**1070** to **1132**; the control-center suite from **389** to **398**.
The api-client (95), storefront-renderer (52), storefront (66), and
Playwright (13) suites are unchanged — M4G-A ships no renderer or public
visual behavior, so no browser-level coverage was added.

- **Registry and contract pins.** The two registries are asserted to
  hold exactly their permanent values in order, with explicit registered
  defaults, lowercase snake_case identifiers (no hyphen — the
  repository-wide convention), and identifiers disjoint from the design
  variant. A build-time pin reads the committed OpenAPI document and
  proves both registries publish as closed enums with the defaults the
  server owns, so a registry change that is not regenerated fails here
  as well as in the drift check.
- **Compatibility, made executable.** A configuration stored before M4G
  — accent-only, or with no theme key at all — parses to the registry
  defaults; the canonical dump round-trips byte-identically with and
  without a logo; `schema_version` stays the literal 1; unknown theme
  keys and unregistered tokens are rejected on submission. A service
  test proves a **read** projects those defaults without rewriting the
  stored JSON or advancing `lock_version`, and its companion pins the
  single deliberate consequence: the first save of a pre-M4G draft is a
  real write that upgrades the canonical form once.
- **Media completeness and claim atomicity.** The completeness invariant
  is now document-level: every `media_id` in the canonical dump must be
  reachable by the claim path, so a future image-bearing field anywhere
  in the registry cannot escape it. The theme logo is proved to follow
  the established matrix — claimed when valid and pending, de-duplicated
  when shared with a section, and rejected before **any** claim occurs
  for unknown, cross-business, and expired references, with the
  co-referenced asset left unpromoted and no draft row written.
- **Authorization isolation for the third leg.** The published theme
  logo is deliverable, and independently so: authorized even when every
  section is disabled, while a disabled-section-only reference still
  authorizes nothing. Draft-only, archived-only, superseded, removed,
  pending, and cross-business references remain unauthorized, proven
  per-host in one run; corrupt authorization state fails closed to the
  neutral 404 while the projection of an unregistered stored palette or
  pairing is the opaque 500 with the established bounded
  `public_projection` log and no token disclosed. A bounded-query test
  proves the logo joins the single batched media read rather than adding
  a statement.
- **Snapshot stability and preservation.** Publication freezes the theme
  into the published version and seeds the next draft from it; an
  archived version keeps the theme it was published with after a
  republication changes the draft; restore copies the archived theme and
  logo. In the control center, dedicated tests prove a non-default
  palette, a non-default typography pairing, and an existing logo all
  survive an unrelated composer save, that editing the accent preserves
  every other theme field, and that a legacy accent-only payload still
  works — including one end-to-end proof through the real composer form.

M4G-A changed no CI workflow file, no dependency, and no lockfile.
Browser-level coverage of the new variants, palettes, pairings, and logo
chrome belongs to M4G-B and M4G-D; the Playwright suite below is
unchanged.

## Earlier state (M4F — delivered 2026-07-30)

M4F closes Milestone 4's verification deferrals (ADR-023). `pnpm e2e`
grows from nine tests to **thirteen**, and its orchestrator now owns a
third server: the storefront dev server (port 3100, loopback-bound,
`STOREFRONT_API_ORIGIN` constructed to the E2E backend, answering
200-or-404 readiness for the storefront only — the backend and control
center keep strict-ok readiness), started between the backend and the
control center and covered by five new orchestrator regression cases
(24 → 29).

- **The storefront journey (mandatory journeys 2 and 3, complete).**
  One cohesive browser journey: an owner composes a draft with all five
  section types through the workspace dialogs, saves it (media claimed
  at save), previews the saved draft through the shared renderer with
  structurally inert links, and publishes; a fresh anonymous visitor
  sees the published version rendered under the tenant host — home and
  `/menu`, with delivered media proven by loaded image bytes. The
  published-versus-draft contract is proven cross-host: the draft is
  never public before publication or after later edits; publishing
  version 2 archives version 1; restoring archived version 1 through
  the Control Center replaces only the draft (the second publication is
  structurally mandatory — restore accepts archived sources only);
  republication brings version 1's content back; suspension hides the
  published site and reactivation restores the same output; and a
  second never-published business proves the rendered surface separates
  hosts.
- **Responsive acceptance for `classic`.** Both public routes at
  320×900, 375×812, 390×844, 430×932, 768×1024, and 1280×900 —
  document-overflow, clipping, stacking, image-containment and
  -proportion, operability, section order/visibility, and a 14 px
  readability floor, all semantic and geometric (no screenshot
  baselines, no pixel gates), over a published five-section fixture
  with deliberately long name and copy. Four viewports are additionally
  captured as disposable manual-inspection evidence per run.
- **Browser accessibility verification.** Blocking axe scans within the
  WCAG 2.0/2.1 A/AA rule tags across eight page/states (public `/` and
  `/menu`, the workspace overview/composer, the composer with a
  section-edit dialog open, the saved-draft preview, history, and
  version detail) — **zero violations, no exclusions** — plus
  real-browser dialog focus (enter on open; Escape closes and returns
  focus), landmarks, single-h1 structure, and keyboard reachability.
  This is engineering evidence within the stated boundary, **not** WCAG
  certification, complete accessibility compliance, or proof that no
  accessibility defects exist.

M4F changed no production runtime or CI workflow file; the only new
dependency is the exact-pinned, development-only `@axe-core/playwright`.
The mandatory journeys 2 and 3 below are therefore **complete**, and
Milestone 4's exit criteria are verified (docs/08, Milestone 4
close-out).

## Earlier state (M4E — delivered 2026-07-30)

M4E adds the control-center storefront workspace's coverage (ADR-022)
and the shared-renderer regression net, at the component/integration
level:

- **Control center (Vitest, jsdom; 389 tests at delivery).** The full
  role-by-lifecycle permission matrix (owner/manager/staff across
  active, provisioning, suspended, closed) and its presentation — staff
  see no navigation and get an honest deep-link denial without a
  request; closed businesses render read-only. Composer behavior: first
  draft (create intent by omission) versus existing draft (exact lock
  version), dialog Apply/Cancel against the single parent form, the
  verified nested 422 grammar mapped by full indexed path (tag checked
  against the discriminant, never name-matched) with clear-on-change and
  structural-mutation clearing so a reorder can never wear another
  section's error, the contract-pinned count bounds asserted at build
  time against the committed `openapi.json`, media staging through the
  shared library primitive (menu suites unchanged as the regression
  net), stale-write conflict preservation with the explicit reload as
  the only exit and a proof that background refetches cannot rebind a
  dirty form, cache safety (draft merges preserve `published`;
  save/restore/publish remove cached previews; the preview key carries
  the saved draft's lock version and timestamp so no stale projection
  can flash), owner-only publication gated on a saved non-dirty draft,
  paged history, read-only version detail, archived-only restore with
  fresh dialog-open concurrency state, and the defensive no-draft
  restore explanation.
- **Shared renderer (`packages/storefront-renderer`; 52 tests).** The
  renderer-pure M4D suites moved with the extracted code (sections,
  classic layout, image srcset, accent, money, contact links, the
  Unicode/complex-script fixtures) plus the repointed stylesheet-policy
  pins (now asserting the `:where()`-scoped tenant baseline), an
  empty-allowlist `'use client'` scan, and the `links: 'active' |
'inert'` suite proving inert markup differs from active markup only by
  `href` absence. Public rendering is unchanged: the storefront app's
  page-level, SEO, isolation, and built-server suites stayed green, the
  first-load budget was unmoved, and disposable visual acceptance
  measured the M4E build pixel-identical to the M4D baseline on every
  compared public home/menu viewport.
- **Disposable visual acceptance (2026-07-30).** The documented
  disposable-environment browser procedure at exactly 320×900, 768×900,
  and 1280×900: the seven principal workspace surfaces plus the dirty,
  live stale-conflict, first-use, manager, staff-denial, and
  closed-business states, with zero measured horizontal overflow across
  every capture and a real-browser conflict/reload drill. Engineering
  evidence, not a WCAG certification.

Deliberate limits, unchanged from M4D: mandatory journeys 2 and 3, the
e2e-orchestrated storefront server, browser-level accessibility
verification (axe, focus order, target geometry), and the complete
cross-host published-versus-draft journey remain M4F.

## Earlier state (M4D — delivered 2026-07-29)

M4D adds the storefront renderer's coverage (ADR-021), in three layers:

- **Component and unit (Vitest, jsdom/node).** Section renderers
  (dispatch exhaustiveness, projection order, optional-value omission,
  escaping, empty states), the classic layout (landmarks, fixed heading
  hierarchy, accent custom properties), exact minor-unit money by
  identity (`1250` must render as exactly `$12.50`), safe contact-link
  derivation, canonical-origin policy, the JSON-LD serializer's
  breakout-proof escaping with a permanent scan pinning
  `dangerouslySetInnerHTML` to the one audited component, metadata
  derivation, robots/sitemap handlers, and the
  Unicode/complex-script suite — Bengali conjunct/matra/ZWNJ/ZWJ fixtures
  (engineering data only) proved NFC-intact through sections, chrome, and
  metadata. Stylesheet floors (wrapping, line height, reduced motion,
  focus, 44 px targets) are pinned as policy-presence tests, because
  jsdom computes no layout — no WCAG conformance is claimed from jsdom.
- **Permanent tenant-isolation contracts (live loopback stubs).** The
  tenant transport is tested on the wire: the incoming Host forwarded
  verbatim, every alternative selection channel stripped
  (cookies/authorization/forwarded/`X-Business-ID`), `cache: "no-store"`
  stamped on every request, the five-second deadline, and the
  development `/api` forwarder's Host preservation and production gate.
- **Built-server verification (`pnpm storefront:verify`).** The
  production build boots against a disposable stub API and the wire
  contract is asserted end to end: page HTML `no-store` with hashed
  assets immutable, the neutral 404 (noindex) for unresolved hosts, the
  neutral non-indexable 500 document on backend outage, per-host
  robots/sitemap, the production-disabled forwarder, Host forwarding on
  every backend request, and the measured two-request render cost.
  `pnpm storefront:budget` enforces the first-load JS ceiling
  (ADR-021) from the same build; both checks were proven to fail on
  seeded violations.

Deliberate limits: no new Playwright journey ships with M4D — mandatory
journeys 2 and 3, the e2e-orchestrated storefront server, and
browser-level accessibility verification (axe, focus order, target
geometry, real rendering) are M4F. The suite below is unchanged.

## Earlier state (Milestone 3F — complete)

M3F adds the end-to-end coverage for Milestone 3 (ADR-019). It is
implemented, verified, and — with owner UAT accepted — **closed**, so
Milestone 3 is complete (2026-07-23; PR #17, merge
`742659122c008ed93c6eeea428f4c26e3f935c60`).

`pnpm e2e` grows from four journeys to nine tests, still Chromium-only,
one worker, zero retries:

- **The menu vertical slice.** An owner signs in, creates a category and
  two items, uploads and attaches an image, adds a required option group
  and a choice, hides the second item, features the first, reorders, and
  the result appears on the tenant's public surface. Money is proved by
  identity — `12.50` must arrive as exactly `1250` minor units and a
  `1.00` surcharge as exactly `100` — because a shape assertion would pass
  for a floating-point path too. Hidden and sold out are asserted as the
  different things they are: the hidden item is absent from the public
  menu entirely, the sold-out one stays listed with `is_available` and
  `is_orderable` false. The image assertions are chosen so they cannot
  pass vacuously (see the fixture note below).
- **Cross-business isolation.** Two businesses, both built by the spec.
  The decisive assertion is media: business A's image URL is a neutral 404
  under B's host **and** a live 200 under A's, in the same run. A 404 for
  something that does not exist proves nothing; a 404 for something being
  served one host away is the boundary.
- **Tenant-host resolution**, pinned before the journey depends on it, so
  a resolution failure can never present as a menu-administration failure.
- **Phone-width administration** at 375×812 — the blueprint's M3
  acceptance bar, now a project command rather than a documented
  procedure.

Three things about how this suite reads the public surface are worth
naming, because each is a trap that would otherwise be rediscovered:

- **Browser navigation, never `request`.** Playwright's `request` fixture
  runs in the Node driver and uses the OS resolver; Windows does not
  resolve `*.localhost` (measured: `ENOTFOUND`). Chromium resolves the
  `.localhost` TLD itself per RFC 6761. Using `request` would have given a
  suite that passes in CI and fails on a developer machine.
- **Not through the UI origin.** The Vite proxy forwards with
  `changeOrigin: false`, so a proxied request keeps `Host: localhost:5273`
  and resolves to no tenant. A test pins this from the other side.
- **A fresh browser context per public read.** No session cookie, so a
  passing assertion cannot be an artefact of being signed in; and an empty
  HTTP cache, because public media is `max-age=3600, immutable` and a
  warm context would answer "is this still served?" from its own cache.

The image fixture is committed (`e2e/fixtures/menu-item.png`, 800×600) and
its width is load-bearing: variants are generated only strictly narrower
than the canonical, so 800 px yields exactly `w320` and `w640` and no
`w1280`. A smaller fixture would produce none and the responsive-image
assertion would prove nothing.

The E2E stack now owns a disposable **media root** as well as a disposable
database. Both are constructed rather than inherited, both are removed on
success, failure, timeout, and signal, and the development media root is
refused by name — an E2E run cannot touch development data.

Two limits are deliberate. The public surface here is the host-resolved
public **API**, not a rendered storefront: `apps/storefront` is still the
Milestone 1 shell and customer-facing rendering is M4. And the phone-width
coverage is limited engineering evidence about layout and reach at one
width — no accessibility scan runs, and target size, contrast, and focus
order are not assessed, so no conformance claim is made.

The mandatory journeys 2 and 3 below are therefore **partially** satisfied
by M3: everything except publication, published-version semantics, and
storefront composition, which are M4.

## Earlier state (Milestone 3E)

M3E is delivered and merged (PR #15, 2026-07-22, ADR-018). What follows is
the coverage on `main`.

The control center's business workspace is covered by component and
integration tests (Vitest, injected client, the real route table through a
memory router). Four kinds are worth naming:

- **Payload-shape assertions.** Every mutation test asserts the exact
  request the facade received, not just that it was called. That is what
  proves updates send only changed fields — a PATCH that resends an
  unchanged value silently overwrites a concurrent edit under ADR-017 D5's
  last-committed-write semantics — and that a create payload never carries an
  update-only field.
- **Pure utilities tested in isolation.** Money conversion and reorder
  permutations carry no JSX and are tested directly: `0.10` must be exactly
  10 minor units, every stored integer must round-trip through the editable
  form in a two-, zero- and three-decimal currency, and every permutation
  helper must return a complete permutation, because the server validates the
  submitted set against the stored one. The vitest `include` pattern covers
  `.ts` as well as `.tsx` so these cannot be silently skipped.
- **Advisory-not-blocking assertions.** Where the domain says a rule is
  report-only — modifier satisfiability above all — the test asserts both
  that the warning appears _and_ that the write still succeeds.
- **Error identity, not error presence.** Where a change moves a validation
  error, the test pins the error's type, location, and message rather than
  asserting that the field is mentioned somewhere. The dietary-tag element
  case is the worked example: a loose assertion covered it, passed under both
  the old and the new error, and so concealed the one behaviour the change
  actually moved.

Layout, computed contrast, touch geometry, and focus visibility are
deliberately **not** asserted in jsdom, which computes none of them. They are
verified by driving the real stack in a browser at 320 px, 768 px and 1280 px
against the disposable E2E database (ADR-018). That is engineering evidence
rather than a WCAG certification — no axe-core scan is run — and it is not a
standing per-change requirement. At the time it was also **not committed
tooling**: the driver was assembled per run, so the evidence was reproducible
only by repeating a documented procedure. M3F closes that gap for the
milestone's own acceptance bar by committing phone-width coverage (see the
M3F section above); whether broader visual tooling should follow is still
open.

## Earlier state (Milestone 3D)

The public surface carries permanent contract tests of its own. Three
kinds are worth naming because they exist to protect decisions rather
than behavior:

- **Route invariants.** Every registered `GET`/`HEAD` route under
  `/api/v1/public/` must carry `resolve_public_business` in its effective
  dependency graph — a recursive walk of the FastAPI dependency tree that
  includes schema-hidden `HEAD` companions, with a positive control (the
  route list may not be empty) and a negative control (a route without
  the resolver is detected). The host-guard exemption is only safe
  because of this test, so it fails the suite rather than a review.
- **Non-disclosure by denylist.** Public schemas are checked against a
  denylist of administrative and storage field names rather than an
  allowlist, so the check keeps failing as the contract grows. Response
  bodies, headers, and captured logs are asserted free of storage keys,
  paths, checksums, and filenames on both success and every failure path.
- **Bounded queries.** A one-category menu and a twelve-item,
  three-category menu with modifiers and images must cost exactly the
  same number of statements; an all-hidden menu must cost fewer, proving
  child reads are genuinely skipped rather than fetched and discarded.
  Representative sizes are deliberate — building a policy-maximum fixture
  to prove absence of N+1 would cost runtime without adding evidence.

Concurrency cases force their interleaving by patching a single
repository call to mutate the database just before it reads, which is
deterministic where racing real clients is not. Public media delivery is
covered for eligibility (detached, hidden-only, hidden-category-only,
pending, foreign), conditional requests, header contracts, the stat/open
race, and the discipline that expected public misses emit no warning.

## Earlier state (Milestone 2F)

The end-to-end layer exists (ADR-016): four Playwright journeys —
onboarding (the blueprint's mandatory journey #1: create → honest
missing-owner conflict → owner invitation with one-time token → guest
acceptance → activation), negative authorization, the anonymous
redirect round-trip, and lifecycle-plus-audit — run Chromium-only,
one worker, `fullyParallel: false`, zero retries. Every spec is
order-independent: it owns a fixed namespace (`e2e-onb`, `e2e-authz`,
`e2e-lc`) inside a database recreated fresh each run, creates its own
prerequisites (through the UI when that is the journey, through
authenticated API fixtures otherwise), and filters audit assertions to
its own business. A single Node orchestrator (`pnpm e2e`, docs/05) owns
ports, the disposable `restaurant_engine_e2e` database (exact-allowlist
reset script; the development database is unreachable by construction),
CLI admin seeding, both servers, Playwright, and guaranteed cleanup;
its failure paths are covered by a node:test regression suite with
injected fakes. CI runs the identical entry point in a fifth `e2e` job
and uploads failure-only artifacts with bounded retention. Component
tests (Vitest, injected client) own the platform UI's states and a11y
behavior; Playwright exercises only real cross-stack journeys.

## Earlier state (Milestone 2A)

The security/tenancy layer began with M2A: a permanent `tests/security/`
suite (PostgreSQL-backed, auto-marked `integration`) proves the ADR-010
contracts — uniform login failure compared under an injected fixed
correlation ID, backoff counter semantics, session rotation/revocation/
idle/absolute expiry, cookie flags per environment, the full fail-closed
CSRF precedence matrix, storage and log hygiene (no plaintext tokens or
passwords anywhere), and bootstrap CLI safety. Migration tests now walk
the revision chain **stepwise** (every migration applies against the
previous head) and prove downgrades are real. Audit detail schemas are
denylist-tested so the `details` column can never carry secrets. The
api-client suite covers the auth facade group with an injected fetch.

## Earlier state (Milestone 1C)

The API contract is under permanent test (ADR-009): backend unit tests
prove the canonical OpenAPI export is deterministic, byte-identical to the
committed `packages/api-client/openapi.json`, and carries exactly the
declared, unique operation ids; boot-time validation tests prove a route
without an explicit `operation_id` (or with a duplicate) cannot compose.
`packages/api-client` carries Vitest facade tests with an injected fetch —
typed success payloads, the ADR-008 error envelope on 503, non-JSON bodies,
and network failure — with no network and no running backend. The CI
`contract` job runs the identical local command `pnpm contract:check`
(temp-directory regeneration, byte-compare, repository untouched).
`pnpm smoke:dev` is the documented proof that the one-command dev stack
serves both health probes and both shells; it is deliberately not a CI job
(CI builds and tests every component individually).

## Earlier state (Milestone 1B)

Frontend tests live in each app (`apps/*/tests/`), run with **Vitest +
Testing Library + jsdom** via `pnpm test` from the root:

- **storefront** — placeholder page and not-found page render with the right
  headings/links; layout/page/not-found metadata declare the expected
  document titles (async server-component rendering is deliberately not
  simulated; shell pages are synchronous components).
- **control-center** — the exported route table is exercised through a real
  memory router: `/` renders the layout landmarks and home page with the
  right `document.title`; an unknown path renders the not-found page.

Production builds are part of the gate (`pnpm build`, zero environment
variables). Playwright/e2e remains deferred until the first real journey.

The backend foundation ships with real tests in `backend/tests/`:

- **unit/** — settings validation, error-envelope contract, constraint
  naming convention (no I/O);
- **api/** — health probes, correlation-ID behavior, error handlers, request
  logging, via the FastAPI test client (no database required);
- **integration/** — readiness against real PostgreSQL and
  `alembic upgrade head` from an empty scratch database. These carry the
  `integration` marker (applied automatically by directory) and **fail with
  a clear message — never skip — when the database is down**, so the suite
  cannot go green while silently not testing the database.

Run with `uv run pytest` (see docs/05 for marker selection). CI runs the
identical commands against the same pinned PostgreSQL image. Frontend and
end-to-end layers arrive with their surfaces (M1B onward).

## Test layers

| Layer               | Purpose                              | Examples                                            |
| ------------------- | ------------------------------------ | --------------------------------------------------- |
| Domain unit         | Fast business-rule feedback          | Modifier selection, status transitions, pickup time |
| Service integration | Transaction and persistence behavior | Publish state machine, order snapshot, reorder      |
| API                 | Auth, schemas, errors, permissions   | Login, menu commands, platform suspend              |
| Security/tenancy    | Permanent isolation contracts        | Cross-tenant IDs, uploads, cache, membership        |
| Frontend component  | Important interaction behavior       | Modifier form, publish warning, order ticket        |
| End-to-end          | Critical journeys across deployments | Onboard → publish; order → accept → ready           |
| Operational         | Restore and deployment confidence    | Migration on production-like DB, backup restore     |

## Database policy (ADR-005)

PostgreSQL is used for integration and API tests that depend on constraints,
transactions, JSONB, or locking. SQLite may be used **only** for pure tests
whose behavior is database-independent. A production PostgreSQL system does
not claim confidence from an SQLite-only suite. Tests use isolated databases
or schemas and deterministic factories; migrations are applied in CI rather
than relying on ORM table creation.

## Mandatory end-to-end journeys (by first commercial release)

1. Platform admin onboards a restaurant and owner.
2. Owner logs in, creates a menu, uploads an image, edits content, publishes.
3. Public visitor sees only the published version under the correct host.
4. Visitor customizes an item and places one pickup order despite a
   simulated retry.
5. Staff accepts, prepares, and marks the order ready; visitor sees status.
6. Tenant A cannot discover or modify tenant B data through API or UI.
7. Suspended tenant becomes unavailable publicly without data loss.

## Quality gates

A pull request cannot merge unless the checks relevant to its contents pass.
The full gate (from Milestone 1 onward, growing with the codebase):

- Ruff lint and format check; Python type check at the agreed strictness;
- pytest unit/integration/API/security suites;
- ESLint and Prettier; strict TypeScript; frontend unit tests;
- production builds;
- OpenAPI client regeneration produces no unexplained diff;
- migration upgrade from the previous schema succeeds;
- Playwright smoke suite for protected milestone branches;
- dependency/secret scan.

During Milestone 0 the gate is the subset that applies to existing files:
formatting, linting, configuration consistency, and repository hygiene.

Coverage is a diagnostic, not a target substitute: critical state machines
and tenant boundaries require behavior coverage regardless of the global
percentage.
