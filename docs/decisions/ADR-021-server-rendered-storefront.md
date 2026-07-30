# ADR-021: Server-Rendered Storefront (M4D)

- **Status:** Accepted (architecture); M4D implementation under review —
  no delivery close-out is recorded yet
- **Date:** 2026-07-29
- **Deciders:** Product owner, principal architect

## Context

M4C completed the public read path: `public.getStorefront()` projects the
current published composition of the Host-resolved business, and
`public.getMenu()` has projected the catalog since M3D. `apps/storefront`
was still the Milestone 1 shell — no tenant awareness, no renderer, no
SEO. M4D turns that shell into the customer-facing storefront (docs/08:
`apps/storefront` rendering, section renderers, SEO basics,
performance/accessibility budgets, Unicode/complex-script rendering
verification). ADR-020 recorded one obligation directly on M4D: an empty
published configuration must render coherently, because the default draft
has no sections.

## Decision

### 1. Universal restaurant-platform positioning (product ruling)

Restaurant Engine is an **English-first, universal U.S. restaurant
platform** for restaurants across cuisines, cultures, ownership
communities, and geographic markets. The initial go-to-market segment
(independent Bengali-owned restaurants in Buffalo, NY) is a sales
strategy — never a product boundary or architectural identity. Nothing in
the product may introduce community-specific branding, navigation,
workflows, field names, defaults, placeholder content, themes, imagery,
SEO assumptions, onboarding behavior, routes, or business rules; no public
claim is made that the platform is intended primarily for any one
community. The blueprint's and roadmap's "Bengali rendering verification"
is read prospectively as **Unicode and complex-script rendering
verification, with Bengali as the required initial complex-script
fixture** — engineering test data (conjuncts, matras, ZWNJ/ZWJ, NFC) that
never becomes seed data, production defaults, or visible positioning. The
platform remains restaurant-specific: this ruling does not generalize it
into a website builder for non-restaurant businesses. The governing
documents carry dated amendments; historical wording is unaltered.

### 2. Routes and rendering model

Two public routes exist: `/` (the published composition) and `/menu` (the
complete public menu). Both are **gated on the published storefront
version**: the design variant and theme live only on that row, so a
business that has never published has no public site under any route —
one neutral 404 for every ineligible case (unknown host, unpublished,
suspended, provisioning, closed — indistinguishable by design, ADR-013).
`hero.primary_action = view_menu` navigates to `/menu`. No `/order`,
`/about`, `/contact`, slug-based, or other route exists; the sitemap
emits only routes that exist (ADR-020 §1).

Rendering is **fully dynamic request-time SSR** (`force-dynamic`), server
components only. No SSG, ISR, PPR, full-route caching, or Next data
caching exists for tenant data. Navigation is plain anchors — full page
loads; there is no client-side navigation machinery to enhance. Exactly
one client component exists: the framework-required route error boundary,
pinned by a permanent allowlist test.

### 3. Tenant-safe server data access

One server data-access boundary (`lib/server/`) reads the backend through
the api-client facade over a **`node:http(s)` tenant transport**, not
global `fetch`, for two load-bearing reasons:

- **Host control is guaranteed.** WHATWG fetch treats `Host` as a
  forbidden header and drops it silently; `node:http` sends exactly what
  it is given. The incoming request's Host travels to the backend
  verbatim — the backend remains the only tenant resolver (ADR-013), and
  the storefront never parses slugs or accepts any alternative selection
  channel (cookies, query, `X-Business-ID`, forwarded headers — all
  stripped by the transport and pinned by permanent tests).
- **Framework caching is structurally impossible.** Next's data cache
  keys by URL, and every tenant shares the backend URL, so any
  framework-level caching would cross tenants — the ADR-013 rule that a
  cache key must include the resolved Business. A transport that never
  touches `fetch` cannot participate in that cache. Every request is
  additionally stamped `cache: "no-store"` (tested), and the transport is
  read-only (GET/HEAD, no body) with a **five-second deadline**.

The API origin is one server-only variable, `STOREFRONT_API_ORIGIN`, read
at request time: development/test default to the local API; production
fails closed on the first request when it is missing or invalid;
zero-environment production builds keep passing. The only permitted
memoization is `React.cache` on the argument-less loaders — its store
lives for exactly one server request (the React contract), the host is
re-derived inside it, and the measured render cost is **two backend
requests per page render** (projection + menu), verified against the
built server. Backend outcomes collapse to three render states: ok /
neutral not-found / unavailable.

### 4. Development media-forwarding topology

Relative media URLs must resolve on the tenant origin
(`{slug}.localhost:3000`) in development. A **development-only `/api/*`
route handler** forwards GET/HEAD to the configured API origin through
the same tenant transport, preserving the browser's original Host
verbatim (proven by live-stub tests); conditional requests
(`If-None-Match`/304) and the backend's centrally assigned cache policy
pass through untouched. Only GET and HEAD are exported, the destination
is always the fixed API origin, and the handler answers a neutral 404 in
production, where the recorded same-origin reverse proxy owns `/api/*`
(ADR-013; topology M8). An external Next rewrite was rejected: its Host
behavior is not contractual, and the explicit handler makes forwarding
provable by construction.

### 5. Section renderers and the variant registry

One shared server component per registered section type (hero, menu,
story, contact, gallery), dispatched by an **exhaustive switch ending in
`assertNever`** — the renderer-side teeth of the M4A registry: a sixth
section type in the generated contract fails the strict typecheck before
it can ship unrendered, and runtime drift (a stale deployment against a
newer API) throws into the generic error boundary with nothing disclosed.
The design-variant registry is the same pattern at page level: `classic`
is the sole variant, variants select chrome/composition/scoped styling
while section renderers are shared, and the second registered variant
cannot ship without its layout arm. Future premium/cinematic
presentations are new platform-controlled variants — no cinematic
functionality, video hero, visual editor, or tenant HTML/CSS/JS exists.

Renderer contracts: projection array order is display order; disabled
sections never arrive and enablement is never re-derived; optional values
are omitted, never fabricated; empty galleries render nothing; the empty
published configuration renders coherent tenant chrome (name, navigation,
landmarks) with no fabricated tenant content. Contract types are derived
structurally from the exported `PublicApi` in one module
(`lib/contract.ts`) because the facade index does not yet re-export the
M4C projection types — no field is restated, and if the facade adds the
re-exports the module collapses to plain re-exports.

The menu section composes with `public.getMenu()` (fetched only when an
enabled menu section needs it): heading/intro from the section, the
centrally governed featured items, and navigation to `/menu`. The `/menu`
page renders the complete projection — categories and items in projection
order, sold-out items listed with a badge, dietary tags as neutral
labels. Deliberate presentation boundaries: modifier groups and
`is_orderable` are ordering-surface facts (M6) and are not rendered;
there is no search. Prices are **exact minor-unit digit placement**
formatted through Intl with string input (never a float), in the `en-US`
presentation locale with the tenant currency.

### 6. Media rendering

Native responsive `<img>` elements built from the projection's URL
descriptors: `srcset`/`sizes` from the delivered renditions plus the
canonical, intrinsic width/height (no CLS), the hero image eager with
`fetchpriority="high"` (the LCP candidate), everything below the fold
lazy. Alt text is the delivered contextual alt; absent alt renders
`alt=""` — never an invented description. `next/image` is deliberately
not used: the backend already generates and authorizes the responsive
WebP renditions per tenant (M3C), and a second optimizer pipeline would
add caching identity and configuration surface for no benefit. The
`no-img-element` suppression is scoped to exactly the one image
component and documented there.

### 7. Metadata, canonical origins, robots, sitemap, JSON-LD

All document metadata derives from published data only: title (business
name; `Menu — {name}` on `/menu`), description (hero subheading when
present, else none — never fabricated), Open Graph title/site
name/type/hero image. A request whose backend read is not ok gets empty
metadata. The **canonical scheme policy is deterministic**: `http` for
the local development host family (`localhost`, `*.localhost`, loopback)
only, `https` for every other host, port preserved, no
`X-Forwarded-Proto` input by construction; a malformed host yields no
canonical. Per-host `robots.txt` (allow + sitemap when published; neutral
disallow otherwise; 503 on outage so crawlers retry) and per-host
`sitemap.xml` (exactly `/` and `/menu`; neutral 404 when unpublished).
Not-found and error experiences are non-indexable (metadata robots +
Next's automatic error-document noindex + real 404/500 statuses).

**JSON-LD** is minimal accurate `Restaurant` data — name, canonical URL,
telephone and textual address from the enabled contact section when
present; no hours, cuisine, ordering, ratings, price range, or menu
structured data. It is embedded through the **one audited
serializer/component pair**, the single permitted
`dangerouslySetInnerHTML`: markup characters and JS line separators leave
as JSON escapes, a script-terminator breakout is proven impossible by
test, and a permanent scan pins the construct to exactly that component.

### 8. Cache headers

Storefront page, metadata-route, and error responses are
`Cache-Control: no-store` (ADR-020 §12), asserted against the built
server — not assumed from framework defaults. Hashed `/_next/static`
build assets keep the framework's immutable caching, and the development
`/api` forwarder passes the backend's centrally assigned policy through.
The 60-second public staleness bound is unchanged and unclaimed-below:
the server consumes the API per request with `no-store`.

### 9. Language and Unicode posture

Product chrome is neutral English; the root document stays `lang="en"`.
No locale column, migration, translation framework, language detector, or
onboarding setting exists in M4D. **Recorded limitation:** screen-reader
pronunciation of tenant content in another language cannot be guaranteed
until a business locale is modeled (a future Businesses-domain decision);
no full Bengali screen-reader verification is claimed under `lang="en"`.
Typography is a universal system stack with complex-script system-font
fallbacks (Bengali among them) after the primary faces; no webfont is
loaded. Wrapping (`overflow-wrap`), line height (1.6), reduced-motion,
and focus-visibility floors are stylesheet policy pinned by tests. The
Unicode suite proves Bengali conjunct/matra/ZWNJ/ZWJ fixtures render
NFC-intact and unmangled through sections, chrome, and metadata — the
fixtures are engineering data only (ruling §1).

### 10. Accessibility

Semantic landmarks (banner/nav/main/contentinfo), one fixed heading
hierarchy (h1 = business name, sections h2, menu categories h3 —
independent of section order), keyboard-reachable link targets at the
44×44 px floor, visible focus, reduced-motion protection, and structured
empty/error states. The **accent contrast guard**: the tenant accent may
decorate, but wherever it backs text the foreground is black or white by
a tested relative-luminance choice whose worst case (~4.58:1) clears WCAG
AA against every possible sRGB accent — property-tested across the color
cube; arbitrary tenant accents are never body-text colors. M4D's
accessibility evidence is lint + component/static level plus built-server
checks; browser-level axe, focus order, and target geometry remain M4F.
No WCAG conformance is claimed from jsdom.

### 11. Performance budget regime

Structural budget: zero client components beyond the error boundary,
enforced by the allowlist scan. Numeric budget: per-route first-load
JavaScript measured from the route build manifests as raw bytes of the
files each route loads (never their unstable hashed names, no absolute
paths), **baseline 456,547 bytes per route** (Next 16.2.10 framework
runtime; both routes ship zero page-specific client JS) **+10% =
502,201-byte ceiling**, enforced by `pnpm storefront:budget` after the
production build in the frontend CI job. `pnpm storefront:verify` boots
the built server against a disposable stub API and asserts headers,
statuses, Host forwarding, and the measured render cost. Both checks were
proven to fail on seeded violations (then removed). Raising the budget
requires amending this ADR. Real-device Core Web Vitals measurement is an
M8 operational concern.

## Alternatives considered

- **Global `fetch` with a Host header** — rejected: fetch drops the
  forbidden `Host` header silently, and Next's patched fetch is exactly
  the URL-keyed cache machinery that must never see tenant data.
- **Next data cache / ISR with 60 s revalidation** — rejected outright:
  URL-keyed caching crosses tenants; embedding the slug in the URL to fix
  the key would create the second tenant-selection path ADR-013 forbids.
- **`next/image`** — rejected: a second image pipeline in front of
  renditions the platform already generates and authorizes.
- **`next/link` client navigation** — rejected for M4D: a two-page
  server-first site gains nothing from client transitions, and plain
  anchors keep the zero-new-client-JS budget structural.
- **An external rewrite for development media** — rejected: Host
  preservation through a rewrite is not contractual; the explicit
  dev-only handler is provable and production-disabled.
- **A `Record`-based variant registry object** — replaced by an
  exhaustive dispatch component: same compile-time completeness, no
  dynamic component-during-render pattern.
- **Menu JSON-LD / hours / cuisine structured data** — rejected: not
  modeled or not yet owned (M5/M6); nothing unmodeled is claimed.
- **Adding a business locale field for per-tenant `lang`** — rejected for
  M4D: a Businesses-domain migration and onboarding question, out of a
  rendering milestone; the limitation is recorded instead (§9).
- **A homepage-only site (no `/menu`)** — rejected: the blueprint names
  the complete browsable menu, and `view_menu` needs a destination.

## Consequences

`apps/storefront` consumes `@restaurant-engine/api-client` (the recorded
M4D workspace link — an internal `link:`, no external dependency). The
facade index does not yet re-export the M4C projection types; the
derivation module covers M4D, and adding the re-exports is a small,
separate facade change if M4E wants it. `smoke:dev` now expects the
neutral 404 from bare `localhost:3000` — the tenant-resolved storefront's
deliberate health signal. With JavaScript disabled, the backend-outage
error page presents the neutral document without the boundary's visible
copy (the boundary is the framework's client component); status, noindex,
and non-disclosure hold regardless — a recorded progressive-enhancement
limitation. The storefront is CSP-_compatible_ (no inline event handlers,
no eval, no external origins); actual CSP headers land with the M8
reverse proxy, which must accommodate Next's inline RSC scripts and the
accent custom-property inline style (nonce or attribute policy).
Journeys 2–3, the e2e-orchestrated storefront server, and browser-level
accessibility verification remain M4F; the storefront workspace UI
(edit/preview/publish/history/restore) remains M4E; hours (M5), ordering
(M6+), campaigns (M10), custom domains, and tenant code stay excluded.

## Security and operations impact

Tenant identity enters only as the forwarded Host and is resolved only by
the backend; permanent tests pin the absence of every alternative
channel and of framework caching. Draft data is structurally unreachable
(no preview consumer exists in the renderer). All copy renders through
React escaping; the one `dangerouslySetInnerHTML` is the audited JSON-LD
boundary with a breakout-proof serializer. Error surfaces disclose
nothing: neutral 404 for every ineligible case, a neutral non-indexable
500 document on outage, bounded value-free renderer errors. The transport
sends no cookies or authorization to the public API and reaches only the
configured origin (no request-influenced destinations). No new logging of
payloads; no tenant data persists across requests in process-global
state (the HTTP keep-alive pool to the fixed API origin carries no
tenant state).

## Reconsideration triggers

The second registered design variant (first real exercise of the variant
dispatch seam); M5 hours (contact/JSON-LD/menu-page presentation gain
structured hours); M6 ordering (the `HeroAction` extension, cart islands
— the first justified client components, which must revisit the budget
and this ADR's structural rule); a business locale model (per-tenant
`lang` and screen-reader verification); the M8 reverse proxy (CSP
headers, forwarded-header trust, canonical-scheme interaction with TLS);
facade re-export of the projection types; any framework upgrade that
moves the measured baseline.
