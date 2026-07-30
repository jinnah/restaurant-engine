# ADR-022: Control-Center Storefront Workspace (M4E)

- **Status:** Accepted; **M4E delivered 2026-07-30** (delivery record
  below)
- **Date:** 2026-07-30
- **Deciders:** Product owner, principal architect

## Context

M4B delivered the administrative storefront API (draft read/update,
publication, archived-only restore, history, platform design assignment;
ADR-020), M4C the public projection and the authenticated draft preview,
and M4D the server-rendered public storefront (ADR-021). No product
surface lets an owner or manager _use_ any of it: the control center has
no storefront area, and the roadmap's M4E row — "storefront workspace:
edit, reorder, preview, publish, history, restore" — is the last
undelivered product slice before the M4F close-out.

M4E consumes only shipped contracts: the seven-operation `storefront.*`
facade group and `storefront.preview()` (66 operations total). It adds no
backend behavior, no migration, and no OpenAPI change.

This ADR records the approved architecture (discovery report, revision,
and implementation addendum, 2026-07-30). Its rulings are binding.

## Decision

### 1. Routes and workspace structure

Four deep-linkable full pages under the existing keyed business-workspace
boundary (ADR-018; the keyed `Outlet` remains the business-switch state
discard):

```text
/businesses/:businessId/storefront                      overview + draft composer
/businesses/:businessId/storefront/preview              saved-draft preview
/businesses/:businessId/storefront/history              version history (paged)
/businesses/:businessId/storefront/history/:versionId   version detail + restore
```

"Storefront" joins "Menu" in the workspace navigation. Full pages, not
drawers: deep-linkable, refreshable, back-button-correct, and the right
mobile primitive (the ADR-018 precedent).

### 2. Shared renderer package and dependency direction

The M4D renderer's framework-neutral visual surface moves to
**`packages/storefront-renderer`**, consumed by both applications, so the
authenticated preview renders through the _same_ components as the public
site — never a parallel preview renderer.

The package contains only reusable visual rendering: the projection
contract types, the exhaustive section dispatch and the five section
renderers, the variant dispatch and the `classic` layout, the responsive
image component, the public menu listing, the pure `accent`, `money`,
`contact-links`, and `assert-never` helpers, their scoped stylesheets,
and the tenant-page baseline stylesheet (scoped under a root class with
zero-specificity `:where()` prefixes so the public cascade is preserved
exactly).

`apps/storefront` keeps everything else: host and tenant resolution, the
`node:http` tenant transport and data loading, Next routes, metadata and
canonical URLs, robots and sitemap, the audited JSON-LD boundary (the one
`dangerouslySetInnerHTML`), public lifecycle/error behavior, and the
development `/api` forwarder.

Dependency direction: `storefront-renderer` depends on `react` (peer) and
type-only on `@restaurant-engine/api-client`. Both apps depend on the
package; the package never imports from an app; the api-client never
imports the package; the backend is untouched. The package is consumed as
raw TypeScript source (the api-client precedent), and it must contain no
`'use client'` directive — pinned by a scan with an empty allowlist — so
everything it exports remains a server component in the storefront and an
ordinary component in the control center. The public routes must keep
shipping zero page-specific client JavaScript under the unchanged
502,201-byte budget.

The api-client facade index re-exports the M4C projection types
(`PublicStorefront` and its section/image family) — the small facade
change ADR-021 approved in principle. Handwritten facade only; no
generated file is edited and the operation count stays 66.

### 3. Preview link mode

The renderer gains exactly one narrow prop: `links?: 'active' | 'inert'`
(default `'active'`) on the variant layout and section list, threaded to
the three navigation sites (layout nav, hero call to action, menu-section
link). `'inert'` renders the same `<a>` element with the same classes and
children but **no `href`**: no URL exists for any mouse, keyboard,
auxiliary-click, or context-menu navigation path, the element has no link
role (assistive technology is not told there is a link that cannot be
followed), and element-selector styling still applies, so the visual
presentation is preserved. The public pages pass nothing and render
byte-identical markup. Event-handler interception, `pointer-events`, and
overlays were rejected: none of them close every navigation path, and the
first two mislead assistive technology.

The control-center preview page consumes `storefront.preview()` (the
current _saved_ draft — enabled sections only, authenticated relative
media URLs that resolve through the same-origin proxy with the session
cookie) and renders it through the shared renderer in `'inert'` mode,
with an honest fidelity note: featured menu items come from the
host-resolved public menu, which the control center cannot fetch and must
not re-derive from administrative data, so the menu section previews its
own heading/intro with the caption that featured items appear on the live
site. Unsaved editor changes are not in the preview; the editor says so
("save to preview") rather than pretending. No public or tokenized
preview exists (ADR-020 §9), and JSON-LD — app-owned metadata — does not
render in preview.

### 4. The draft composer and explicit Save Draft

One parent React Hook Form holds the complete `StorefrontConfig`. The
editor page shows the accent control and one **summary card per section**
(type, one-line summary, enabled state, Move up / Move down, Edit,
Remove) plus an "Add section" affordance offering only the missing types
(at most one section per type — the registry invariant). Editing opens a
focused dialog that renders **no nested native `<form>`**: it mounts its
own RHF instance seeded from a deep snapshot
(`structuredClone(parent.getValues())` of that section), Apply validates
and commits one complete section value into the parent via
`setValue('sections.N', value, { shouldDirty: true, shouldValidate:
true, shouldTouch: true })`, and Cancel/Escape discards only the dialog
snapshot. The parent form is the single owner of dirtiness.

One explicit **Save Draft** performs the full-document PUT with the D-5
intent representation derived from the cached overview: no draft →
omitted `expected_lock_version` (create); otherwise the saved draft's
exact `lock_version` (update). No autosave, no optimistic mutation, no
hidden writes; `UnsavedChangesPrompt` guards navigation. New sections get
`id` = their type name (valid slug, unique by the one-per-type
invariant); existing ids round-trip unchanged.

Media selection reuses the shipped library through a shared primitive
with thin adapters: the menu adapter preserves the existing item-image
labels, confirmations, and messaging verbatim; the storefront adapters
cover the hero single image (select/replace/remove, per-placement alt
text with the ADR-018 ruling-9 describe/decorative choice) and the
ordered gallery (keyboard reorder, per-image alt). Selecting or uploading
only stages `{media_id, alt_text}` in form state — **the claim happens at
draft save** (ADR-020 §10), and no copy may claim that selection, upload,
or even draft save makes media public.

### 5. Authorization and lifecycle

`storefrontPermissions(membership)` derives affordances from **both**
role and business lifecycle, mirroring the ADR-020 §7 matrix:

| Derivation                                     | Rule                                                  |
| ---------------------------------------------- | ----------------------------------------------------- |
| `canRead` (overview, preview, history, detail) | owner or manager — every lifecycle including `closed` |
| `canEdit` (draft save, media staging)          | owner or manager, and status ≠ `closed`               |
| `canPublish` / `canRestore`                    | owner only, and status ≠ `closed`                     |

Staff hold no storefront read capability, so they see no Storefront
navigation at all and a deep link renders the honest 403 explanation.
Platform administrators hit the existing nonmember 404. Closed businesses
render the full read surface with mutation controls absent; provisioning
and suspended businesses keep every mutation the service allows. The
draft's `design_variant` is read-only metadata — no owner design
selection and no platform design-assignment UI exist in M4E. Every
derivation is presentation only; the API stays the authorization
authority, and a 403 or 409 that arrives anyway is rendered honestly.

### 6. Concurrency, conflict, and cache behavior

Query keys (all under the mandatory business scope):

```text
['business', b, 'storefront', 'overview']
['business', b, 'storefront', 'preview', lockVersion, updatedAt]
['business', b, 'storefront', 'versions', 'page', { limit, offset }]
['business', b, 'storefront', 'versions', 'detail', versionId]
```

Server-confirmed state only. Draft save and restore merge the returned
`DraftView` into the cached overview's `draft` while preserving
`published` (invalidate instead when the overview is not cached); publish
writes its returned `StorefrontOverview` wholesale and invalidates the
whole versions scope (the previously published row's state flipped).
Save, restore, and publish **remove** cached preview entries; the preview
key carries the saved draft's `lock_version` **and** `updated_at`
(`lock_version` alone collides across publication, which seeds a fresh
draft whose lock restarts), so opening preview after any mutation shows a
loading state and can never flash the preceding projection.

A stale write (409) enters an **explicit conflict state**: form values
and the original stale lock token are preserved untouched, further
mutations are disabled, and nothing auto-merges, retries, or adopts the
server's newer lock version into the stale payload. The overview cache is
marked stale _without_ an active refetch
(`invalidateQueries({ refetchType: 'none' })`), and the form is
structurally immune to background rebinding — it is seeded from
`defaultValues` once per loaded draft and reset only by the explicit
**Reload current draft** action, which alone refetches, resets, adopts
the current `lock_version`, and clears the conflict, behind a clear
replacement warning.

### 7. Validation and API-error mapping

Zod validates UI shape only. The **only** mirrored numeric bounds are the
two the committed contract publishes — `address_lines maxItems: 4` and
gallery `images maxItems: 12` — held in one handwritten module and pinned
by a build-time test against `packages/api-client/openapi.json`. The
text-length bounds (`storefront.policies`) are enforced by backend
validators and do **not** reach the OpenAPI document, so under the
ADR-018 ruling-7 principle they are not mirrored: no client-side length
blocks, no invented counters; the server's 422 field errors are the
authority and are mapped onto the exact inputs. Phone and email carry no
client format rules (the contract publishes bounded plain text). The
accent uses a native color input, which emits a valid lowercase
`#rrggbb` by construction — an affordance, not a mirrored pattern.

The verified error-path grammar (probed against the real `DraftPut`
model): the envelope joins Pydantic locations with dots, FastAPI
prefixes `body`, and the discriminated-union **tag appears after the
index** — for example `body.config.sections.0.hero.props.heading` and
`body.config.sections.2.gallery.props.images.0.alt_text`. Conversion:
strip `body.config.`, verify the tag equals the form's
`sections[i].type`, drop the tag segment, and set the error at the RHF
path (`sections.0.props.heading`); mismatched tags, whole-document
paths, and media-reference 422s (one indistinguishable message, D-6)
fall back to the persistent form-level summary with the server's message
verbatim — matching is by full indexed path, never by field name, so
repeated names (`heading`, `alt_text`) cannot collide. Server-set errors
clear when the affected field changes, when a dialog Apply commits that
section, and wholesale on every save response; **any structural
mutation (move, remove, add) clears all server-set section errors**, so
a reordered list can never wear another section's error.

### 8. Publication, history, and restore

Publish is owner-only, requires a saved, non-dirty draft (it carries the
saved draft's exact `lock_version`; publishing over unsaved edits would
publish something other than what is on screen), and uses an explicit
confirmation whose copy claims no version number — numbers are minted
server-side. History is the paged published+archived list with a detail
page per version. Restore is offered for **archived** versions only,
through a `ConfirmDialog` with explicit consequence copy: it replaces the
current draft's content, publishes nothing, and leaves history unchanged
(typed confirmation is reserved for the permanent-deletion register).
The confirmation refetches the overview when it opens and uses the
fresh draft `lock_version` — the shipped contract requires an integer
(`RestoreRequest.expected_lock_version` is required; restore has no
create intent), and the service answers a missing draft with the
defensive 409. That state is unreachable through the product (archived
rows exist only after a second publication, publication always seeds a
draft, nothing deletes a draft), but the UI still guards: with no draft,
the restore affordance is absent and the page explains. After a restore
the owner is returned to review — publication remains a later, separate,
explicit action.

### 9. Honest status presentation

The overview shows only facts the server states: first-use (no draft) or
the saved draft's last-saved time; never-published or the published
version number and publication time; local unsaved changes (a client
fact about the client); the stale-conflict state; and provenance when the
server supports the statement — `source_version_id` equal to the current
published id reads "started from published version N", otherwise the
source version is resolved and reads "restored from version N".
`lock_version` appears only in a collapsed diagnostics disclosure. **No
timestamp-derived "edited since publish" claim and no draft-versus-
published equality or difference claim exists anywhere** — the metadata
cannot support one. If equality is ever wanted, it is a backend-computed
overview field requiring separate approval (recorded below).

### 10. Verification boundary between M4E and M4F

M4E owns component/integration-level coverage of every behavior above,
the jsdom-level accessibility implementation (labels, focus management,
error summaries, announcements, keyboard reorder), and the
disposable-environment visual acceptance procedure at 320/768/1280 px —
including a public-storefront regression pass, because the baseline
stylesheet scoping touches shipped styles. M4F still owns Playwright
journeys 2 and 3, real-browser axe checks, focus-order verification,
target geometry, the full cross-host published-versus-draft journey, and
the Milestone 4 close-out. No WCAG conformance is claimed from jsdom.

## Alternatives considered

- **A parallel control-center preview renderer** — rejected: duplicate
  presentation logic that drifts from the public rendering it claims to
  preview.
- **Rendering the draft through the storefront app** (iframe or a draft
  route) — rejected: the public renderer structurally cannot reach drafts
  (ADR-021), and adding a route would create the tokenized/public preview
  ADR-020 §9 forbids.
- **Event-handler interception, `pointer-events: none`, an overlay, or
  the `inert` attribute for preview links** — rejected: the first three
  do not close every navigation path (auxiliary click, context menu), the
  first two announce active links assistive technology cannot follow, and
  `inert` hides the preview's content from assistive technology entirely.
- **All five sections edited inline on one long page** — rejected in
  review for focused per-section dialogs over summary cards.
- **Autosave / optimistic updates / automatic 409 retry or merge** —
  rejected: ADR-017 D5 and the explicit-intent contract (D-5) both demand
  server-confirmed state and surfaced conflicts.
- **Mirroring the text-length bounds in Zod** — rejected: the committed
  contract does not publish them, so a mirror is uncheckable and can
  drift into the client overriding the server (ADR-018 ruling 7).
- **Deriving preview menu data from administrative catalog reads** —
  rejected: it would re-implement the public visibility and featured
  policies client-side.
- **A timestamp-derived "edited since last publish" badge** — rejected:
  publication seeds a fresh draft with its own timestamps, so the
  comparison is not a reliable signal.

## Consequences

`packages/storefront-renderer` becomes the third workspace package; the
lockfile change is workspace importer entries only, with no external
dependency. `apps/storefront` shrinks to routing, data, SEO, and
transport concerns around the shared renderer; its renderer-pure test
suites move with the code. The control center gains its second workspace
area and inherits every shell primitive from M3E unchanged. The menu
image picker's behavioral core becomes a shared media-selection primitive
with the menu adapter preserving shipped behavior verbatim.

Recorded candidates deliberately **not** built in M4E, each requiring its
own approval:

- **Backend-computed draft equality** — an overview field stating whether
  the saved draft's composition equals the currently published version,
  so the workspace could make a truthful "unpublished changes" claim.
- **Publishing the text-length constraints into OpenAPI** — declaring the
  `storefront.policies` bounds as field constraints so the contract
  publishes what the service already enforces (the ADR-018 ruling-13
  precedent), enabling checkable client affordances.
- **A preview-menu projection** — a backend-computed featured-items
  payload for the authenticated preview, if menu-section fidelity is ever
  required there.

## Security and operations impact

No authorization rule changes; every guard is presentation over the M4B
capability matrix, and the backend's non-disclosure contract (nonmember
404, capability 403) is reproduced verbatim in the UI. Draft content
stays unreachable anonymously: the preview is the authenticated M4C
endpoint, `no-store`, and its media URLs are the authenticated
business-scoped routes. The public storefront's security posture is
unchanged by the extraction — the transport, Host handling, caching
prohibitions, JSON-LD boundary, and error surfaces all remain in
`apps/storefront`, and the package introduces no client JavaScript, no
network access, and no tenant state. CSRF handling is inherited: every
unsafe call resolves the session token at execution time.

## Reconsideration triggers

The second registered design variant (the workspace must present
variant-specific preview chrome); M5 hours (contact-section adjacency);
M6 ordering (the `HeroAction` extension reaches the composer's closed
enum labels); the recorded candidates above; a request for drag-and-drop
reordering (sits atop the keyboard model, ADR-018 ruling 5); an
`admin-ui` package (second real application consumer); any framework
change that alters the RHF error-indexing behavior this design refuses
to rely on.

## Delivery record

### M4E — Control-center storefront workspace: delivered, 2026-07-30

**Delivered behavior.** The four deep-linkable workspace pages under the
keyed business boundary (§1). The framework-neutral shared renderer
package consumed as raw TypeScript source by both applications, with the
tenant-page baseline rewritten under the zero-specificity `:where()`
scope and the single `links: 'active' | 'inert'` API addition — public
pages render byte-identical active markup while the preview's in-site
navigation carries no `href` and announces no link role (§§2–3). The
draft composer: one parent form over the complete configuration, summary
cards with focused per-section dialogs (no nested native form; Apply
commits one complete section value; Cancel discards only the dialog
snapshot), keyboard-first ordering, staged hero/gallery media claimed at
draft save through the shared media-selection primitive (the menu
adapter preserves the M3E copy verbatim), the native accent control, and
the explicit full-document Save Draft with the D-5 create/update intent
(§4). The §5 lifecycle-aware permission presentation, including the
honest staff denial and the closed-business read-only surface. The §6
concurrency and cache rules: explicit stale-conflict state preserving
values and the stale token with "Reload current draft" as the only exit,
draft merges that preserve `published`, preview keys carrying the saved
draft's lock version and timestamp, and preview removal on every
mutation — no stale projection can flash. The §7 validation posture:
only the two contract-published count bounds mirrored and build-time
pinned to the committed OpenAPI document, and the verified 422 grammar
mapped by full indexed path with the documented clearing rules. §8
publication (owner-only, saved non-dirty draft, explicit confirmation,
no version-number claim), paged history, read-only version detail, and
archived-only restore with fresh dialog-open concurrency state. §9
server-fact-only status presentation.

**Delivery evidence.** Implementation PR #27; reviewed feature head
`5f52a602aacb8a018e2224a310498545559d7277`; merged to `main` as
`09aa177c1cc9a89dff84cd7d8b09e6929de8a884` with ordered parents
`b11253695ac68dce22bfe4da24e6fb126be2f505` then
`5f52a602aacb8a018e2224a310498545559d7277`; the merge tree equals the
reviewed feature-head tree. Exact-head PR CI run `30562964833` and
exact-merge-SHA push CI run `30563536274` both completed successfully
with all five jobs (repository-contract, frontend, contract, backend,
e2e) green and zero artifacts. Substantive results: backend **1070
passed**; api-client **95 passed**; storefront-renderer **52 passed**
(the extracted renderer-pure suites plus the link-mode, client-directive,
and stylesheet-policy pins); storefront app **66 passed**;
control-center **389 passed**; E2E orchestrator **37 passed** with the
one pre-existing Windows symlink skip; Playwright **9 passed** with the
disposable database and media root created and cleaned per run; contract
byte-clean at exactly **66 operations**; both production builds green;
the storefront budget measured **456,547 bytes** for both `/` and
`/menu`, under the **502,201-byte** ceiling; the built-server
verification passed in full. Disposable visual acceptance (2026-07-30)
passed at exactly **320×900, 768×900, and 1280×900**: the seven
principal workspace surfaces plus the dirty, live stale-conflict,
first-use, manager, staff-denial, and closed-business states, zero
measured horizontal overflow across every capture, a real-browser
conflict-and-reload drill, and public rendering **pixel-identical to the
M4D baseline** on every compared home/menu viewport — including
image-loaded captures behind a disposable same-origin reverse proxy. The
disposable database, media root, server processes, proxy, and the M4D
baseline worktree were removed afterward; preserved development/UAT
resources were untouched throughout.

**Limitations and deferrals, preserved.** Browser-level accessibility
verification — axe, focus order, target geometry — remains M4F, as do
Playwright journeys 2 and 3, the e2e-orchestrated storefront server, and
the complete cross-host published-versus-draft journey; no WCAG
certification is claimed. The recorded candidates (backend-computed
draft equality, publishing the text-length constraints into OpenAPI, a
preview-menu projection) remain future decisions. **Milestone 4 remains
in progress; its exit criteria stay open until M4F.**
