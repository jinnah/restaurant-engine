# ADR-019: M3F End-to-End Coverage and Milestone 3 Verification

- **Status:** Accepted (architecture); delivery record open — M3F is **not
  closed** and Milestone 3 remains **In progress** pending owner
  acceptance
- **Date:** 2026-07-22
- **Deciders:** Product owner, principal architect

## Context

M3F is the last slice of Milestone 3: the Playwright menu journey,
verification, and close-out (`docs/08_ROADMAP.md`, ADR-017). M3A–M3E
delivered the catalog, modifiers, media, the public menu API, and the
control-center menu administration UI. What none of them delivered is
evidence that those pieces work _together_ against a real stack — M3E's
coverage is component and integration level, and the Playwright menu
journey was deferred here by explicit decision.

A source-grounded discovery pass preceded this ADR and produced findings
that changed the design before any code was written. They are recorded
below as rulings rather than left in a proposal, because several of them
constrain what M3F may honestly claim.

## Decision: binding rulings

### D1 — "Public surface" means the host-resolved public API

M3F proves that control-center changes become visible through the
**tenant-Host-resolved public menu and public media APIs**
(`GET /api/v1/public/menu`, `GET /api/v1/public/media/{asset_id}/{variant}`).

This is **not** a rendered public storefront, and must never be described
as one. `apps/storefront` is still the Milestone 1 foundation shell — its
home page reads "This is the public storefront foundation (Milestone 1)"
— it has no menu route and no tenant resolution, and the E2E orchestrator
does not start it. Customer-facing menu rendering is Milestone 4.

### D2 — Blueprint journeys 2 and 3 are only partially satisfied

Journey 2 ("Owner logs in, creates a menu, uploads an image, edits
content, and publishes") and journey 3 ("Public visitor sees only the
published version under the correct tenant host") both name publication,
which does not exist until M4.

M3F satisfies the M3-shaped part: login, menu creation, editing, image
upload, public API visibility, availability, and tenant resolution.
Draft/publish behaviour, published-version semantics, and storefront
composition remain pending M4. Neither journey may be recorded as
complete.

### D3 — Phone-width coverage becomes a project command

Blueprint §19 sets M3's acceptance bar as "responsive menu administration
works on mobile". ADR-018 left this as its weakest evidence: real, but
reproducible only by repeating a documented procedure, because the driver
lived in a scratchpad and was never committed.

M3F commits one narrowly scoped test at 375×812 covering the core
administrative path. A second Playwright project duplicating the whole
suite to change one viewport is rejected — the phone-specific risks are
concentrated in a few screens.

At each of those screens: the principal control is present and operable,
dialogs and forms can be _completed_ rather than merely opened, and the
document does not scroll horizontally. The overflow check measures
`document.documentElement`, because a wide element scrolling inside its
own container is a normal responsive pattern while document-level
horizontal scroll is what puts controls out of reach.

This is **limited engineering evidence about layout and reach at one
width**. It is not an accessibility audit and no conformance claim is
made: no automated accessibility scan runs, and target size, contrast,
and focus order are not assessed. An earlier draft asserted a 44 px
target minimum attributed to WCAG 2.2 SC 2.5.8; the attribution was
wrong — that criterion is satisfied by size **or** spacing — and target
size is not needed to show menu administration works on a phone. It was
removed rather than restated.

### D4 — The image fixture is committed

`e2e/fixtures/menu-item.png` (800×600, 2350 bytes) is committed rather
than synthesized at run time. A runtime PNG encoder would need
`@types/node`, which the e2e package deliberately does not carry, and
would itself be untrusted code. `.gitattributes` already declares
`*.png binary`; git records the file as `i/none attr/-text`, so the CI
LF-normalization check is unaffected.

800 px wide is deliberate: the canonical rendition stays 800, so `w320`
and `w640` are generated and `w1280` is not (variants exist only strictly
narrower than the canonical, ADR-017 R3/R4). A smaller fixture would
produce no variants and the responsive-image assertion would be vacuous.

### D5 — M3F carries its own ADR

This document, following ADR-016's precedent for M2F.

### D6 — A spec may own several namespace keys

ADR-016 gave each spec a fixed namespace. M3F extends this: a spec may own
**several** keys when its subject genuinely needs more than one business —
cross-business isolation cannot be demonstrated with one tenant. The
invariant that matters is unchanged: every key belongs to exactly one
spec, and no spec ever names another spec's.

### D7 — Cross-business catalog and media isolation belongs to M3F

The M3 exit criterion names cross-tenant media and catalog tests, and
blueprint journey 6 is that one tenant cannot discover or modify
another's data through the API or the UI. M3 created the first
tenant-owned catalog and media surfaces; the boundary they introduced is
covered here.

## Decision: the disposable media root

The orchestrator has owned a disposable database since M2F, but media
objects live on the filesystem. With `MEDIA_STORAGE_ROOT` unset the
backend fell through to its development default `backend/var/media`, so
the first E2E run that uploaded an image would have written into the
developer's own media root — which `docs/07` treats as one logical backup
set with the development database — and left every object orphaned there,
because cleanup drops only the database.

M3F gives the E2E stack `backend/var/media-e2e`, **constructed** from the
repository root and never inherited, exactly as the E2E database URL is
constructed rather than read from the environment. `assertRemovableMediaRoot`
guards every removal, layered like the reset script's URL allowlist: the
development root is refused by name with its own message, and anything
else must equal the constructed path exactly.

Creation happens before the backend spawns (it creates its scratch
directory under this root at composition time). Removal happens after the
children are stopped (a live backend holds handles Windows will not let go
of) and is its own cleanup step, so a failed database drop cannot strand
it and its own failure cannot hide one. A removal failure is loud and
nonzero without ever masking a primary failure.

## Decision: the public surface is read by browser navigation

Playwright's `request` fixture runs in the Node driver and uses the
operating-system resolver. Windows does not resolve `*.localhost`.
Measured before anything depended on it:

```text
node fetch        => ENOTFOUND
page.request      => getaddrinfo ENOTFOUND e2e-menu.localhost
page.goto         => 200, Host: e2e-menu.localhost, from 127.0.0.1
```

Chromium resolves the `.localhost` TLD to loopback itself (RFC 6761),
independently of the operating system. So **every public assertion is a
browser navigation**; using `request` would have produced a suite that
passes in CI and fails on a developer machine. Top-level navigation is
also not subject to CORS, which is what makes this work against a backend
that deliberately exposes no CORS surface.

The public surface also cannot be reached through the UI origin: the Vite
dev proxy forwards with `changeOrigin: false`, so a proxied request
arrives as `Host: localhost:5273`, which is not one label above the
platform base domain and resolves to no tenant. A test pins this from the
other side, so a future `changeOrigin: true` fails loudly and says why.

Public reads use a fresh browser context. It carries no session cookie, so
a passing public assertion cannot be an artefact of being signed in; and
it starts with an empty HTTP cache, which matters because successful
public media responses are `public, max-age=3600, immutable` — a context
that had already fetched an image would answer later requests from its own
cache and never ask the server, making "this image is no longer served"
unprovable.

## Application defect found by the vertical slice

**This was discovered by the M3F journey, not by unrelated review, and it
is the clearest argument for the slice existing at all.**

`ItemImageSection` offered "Delete from library" gated on
`assetId !== null`, where `assetId` is `item.image_media_id`. The control
therefore rendered exactly when the asset was referenced — the one state
in which the backend must refuse the delete, via the `menu_items` RESTRICT
foreign key that `safe_flush` converts to a 409. Its confirmation dialog
said "Remove it from this item first"; doing so set `image_media_id` to
null, which unmounted the control. The instruction could not be carried
out from the screen that gave it.

The asset was then unreachable: the picker offered upload and selection
but no delete, no other route reaches the media library, and ADR-017 R7
never sweeps an ever-attached asset for being unreferenced. Every image a
business ever detached was permanent, with no way to remove it.

The correction moves deletion into the library, where it belongs, scoped
narrowly to the existing picker — no new page, no redesign. Each entry
carries its own delete control as a sibling of its tile (a button inside a
button is invalid). Confirmation is inline rather than a nested
`ConfirmDialog`: that builds on `Dialog`, and two `Dialog`s would install
two competing focus traps over the same tree, since the inner handler
stops Escape from propagating but not Tab.

Backend semantics are untouched — nothing cascades, nothing is detached on
the client's initiative, the constraint is unchanged, and a referenced
asset still returns 409, now reported in the library with the entry still
present and still offering the action that becomes legal once detached.
Authorization is unchanged and still gated on `business.media.write`, with
the service re-checking the capability and the business boundary on every
request. No API, OpenAPI, or generated-client change was required:
`client.media.deleteAsset` already existed and is simply called from its
proper place. The item page keeps Upload, Use for this item, and Remove
from item, losing only the control that could never succeed.

## Alternatives considered

- **Keeping a detached asset temporarily visible on the item page**
  (rejected): local state would disappear on reload and would still give
  no way to manage any other unused library asset.
- **A dedicated media-management page** (rejected): a redesign, far beyond
  the correction the defect requires.
- **Deferring the defect and dropping media cleanup from the journey**
  (rejected by the product owner): cleanup is named scope.
- **A second Playwright project for the phone viewport** (rejected, D3).
- **Synthesizing the fixture at run time** (rejected, D4).
- **Reading the public API with Playwright's `request` fixture**
  (rejected on measured evidence — it cannot work on Windows).

## Consequences

`pnpm e2e` now covers the Milestone 3 vertical slice, cross-business
isolation, tenant-host resolution, and phone-width administration, with
no lifecycle logic duplicated into CI — the workflow is unchanged, because
the orchestrator owns the media root exactly as it owns the database.

An E2E run can no longer touch development data: the database was already
unreachable by construction, and the media root now is too.

The blueprint's mobile acceptance bar for M3 is a project command rather
than a documented procedure, which answers ADR-018's open question in the
narrow sense it was asked. Whether broader visual/accessibility tooling is
worth committing remains open and is deliberately not answered here.

## Security and operations impact

No authorization, tenancy, CSRF, cookie, host-guard, or CORS behaviour
changes. No new dependency. The public-repository artifact policy
(ADR-016) is untouched: CI still uploads only secret-scanned
`error-context.md` files and still fails closed.

One consequence worth recording: media-rich ARIA snapshots increase the
chance that the `issued-token-shaped-value` pattern
(`/[A-Za-z0-9_-]{43,}/`) matches something innocuous and voids an upload.
That is the policy working as designed — failures are reproduced locally
for full traces — and the scanner is deliberately not weakened.

## Reconsideration triggers

M4's storefront composition (which makes journeys 2 and 3 completable);
parallel E2E workers (per-worker databases _and_ media roots); a real
media-management surface; adoption of an automated accessibility scan;
S3-backed media (the disposable root becomes a disposable bucket prefix).

## Delivery record

**Open.** The technical implementation is complete and verified locally on
`feature/m3f-e2e-closeout`; the milestone is not closed. Owner UAT is a
mandatory gate before M3F or Milestone 3 may be marked complete, and the
roadmap is deliberately unchanged until then.
