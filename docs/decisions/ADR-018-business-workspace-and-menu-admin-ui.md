# ADR-018: Business Workspace and Menu Administration UI

- **Status:** Accepted (architecture); delivery record filled at close-out
- **Date:** 2026-07-21
- **Deciders:** Product owner, principal architect

## Context

M3E gives restaurant owners, managers, and staff their first product surface.
Until now every catalog and media capability existed only as the M3A–M3C
APIs, and the control center had exactly two areas: the M2E authentication
flows and the M2F platform administration area. There was no business
workspace, no way to select a business, and no menu UI at all.

The roadmap scopes M3E as "business workspace + menu management in the
control center" (docs/08), and blueprint §19 M3 sets the acceptance bar:
**responsive menu administration works on mobile**. The architecture went
through a source-grounded discovery proposal, a corrections addendum, and
binding product-owner rulings — all recorded here before implementation.

M3E consumes the M3A–M3C administrative contracts. It adds no route, no
migration, no authorization rule, and no catalog or media behavior. The one
deliberate exception is the dietary-tag contract-fidelity correction below,
which was authorized separately and changes the published contract without
changing any accepted value or any service behavior.

## Decision: binding architectural rulings

### 1. Route vocabulary is `businesses`, never `restaurants`

Workspace routes are `/businesses/:businessId/...`. Blueprint §13 sketched
`/restaurants/:restaurantId/...` before ADR-012 renamed the tenant aggregate
to **Business**; every API path, every domain module, and the shipped
platform area already use `businesses`. The blueprint is amended in the same
change rather than left to contradict the implementation.

M3E registers exactly one section, `menu`. The workspace layout is the slot
where storefront, hours, orders, and team arrive in later milestones.

### 2. The business switcher is route-derived, never stateful

A native `<select>` in the authenticated chrome, labelled visibly, whose
options come **only** from `session.memberships` and whose value is derived
from the route (`useMatch('/businesses/:businessId/*')`). There is no
current-business context, no store, no `localStorage`, no `sessionStorage`.
The URL is the single source of truth, so the control and the workspace can
never disagree.

A native control is chosen deliberately over a custom `role="listbox"`
popup: arrow keys, Home/End, type-ahead, and Escape are correct in every
browser for free, and on a phone the OS renders its own picker — which is
better at 320 px than anything hand-written, and is the milestone's
acceptance bar. The accepted cost is that option content is text-only, so
lifecycle status is encoded in the option label (`Shalik — owner ·
suspended`), which is colour-independent by construction.

Zero memberships renders no switcher. Platform administrators hold no
membership (ADR-011), so they never see one and their deep links receive the
same neutral not-found treatment any nonmember gets. The switcher is a
navigation aid; the backend remains the authorization boundary.

### 3. Forms use React Hook Form with a Zod resolver

ADR-015 decision 10 deferred React Hook Form and Zod to "the first complex
editing workflow (expected M3)". This is it. Three exact-pinned direct
dependencies are added to `apps/control-center` (blueprint technology table;
docs/02 locked decision 6). Zod validates **UI shape only** — required,
trimmed, length, decimal precision. API truth stays generated from OpenAPI
(ADR-004), and no backend enum is copied by hand.

Item creation and editing share presentation (`ItemFields`) and one Zod
schema, but keep **two distinct request adapters** with two distinct return
types (`ItemCreate` and `Partial<ItemUpdate>`), so a create payload can never
acquire an update-only field.

### 4. Server-confirmed state; no optimistic updates

ADR-017 D5 fixes this: row locks serialize writes but do not detect stale
editors, so the control center invalidates and refetches after every
mutation. Where a command returns the authoritative aggregate — the two
reorder operations return `AdminMenu`, the option mutations return the
recomputed `ModifierGroupView` — the response is written straight into the
cache. Everything else invalidates. No mutation renders a state the server
has not confirmed.

### 5. Reordering is keyboard-first, with no drag-and-drop

Move up, Move down, and Move to position, inside an explicit reorder mode.
Reorders are full-set, exact-set-validated permutations built from the
currently cached authoritative order; an inexact set returns 409 and the UI
refetches and explains. Drag-and-drop is deliberately absent: it would need
a dependency or a hand-written pointer system, would still require an
accessible alternative, and would still have to compute the same
permutation. If it is ever added it sits on top of this model.

### 6. Notifications are visible, and never fight a modal

A single notification region is mounted from application start (a live
region created at the same moment as its message is frequently not
announced) and renders **beneath** any active modal overlay. A dismissible
notification above an `aria-modal` dialog is visible but unreachable,
because the dialog owns focus — so a successful modal mutation closes the
modal first, restores focus to the triggering control, and only then
publishes the notification. Success and information only, polite, auto
dismissed after a timeout that pauses while hovered or focused, dismissible
by keyboard, never focus-stealing, animation suppressed under
`prefers-reduced-motion`.

Failures never enter this system. They stay persistent and inline through
the M2E `ErrorSummary` (focus-moving `role="alert"`) and per-field errors,
and never auto-dismiss. The notification API has no error tone to pass.

### 7. Governed limits are shown, not discovered by failure

The featured ceiling renders as `Featured items: n of 6` from the first
authoritative menu read, counting hidden featured items exactly as ADR-017
R1 counts them. The `6` is a named, documented feature-local **UX mirror**
of `catalog.policies.MAX_FEATURED_ITEMS`; the server stays authoritative. A
409 carrying a different `details.limit` reverts the attempted state,
displays the server's number, refetches, and reports the discrepancy
visibly and through a stable diagnostic marker — the frontend constant is
never treated as authoritative. `MAX_PRICE_MINOR` follows the identical
convention.

### 8. Money is converted by string arithmetic, never floating point

Input syntax is deliberately locale-fixed: ASCII digits (Bengali–Indic
digits normalized first, per the launch market), a dot decimal separator,
no grouping separator, no symbol, no sign. `Intl` provides formatting but no
standard parser, and hand-rolling locale-aware parsing is a correctness
hazard with no dependency budget, so the accepted syntax is stated in the
UI instead of guessed.

Fraction digits come from
`Intl.NumberFormat(...).resolvedOptions().maximumFractionDigits`, never a
hardcoded 2. Conversion pads the fractional part and **concatenates digit
strings** into an integer — no multiplication ever touches the input path,
so `0.10` is exactly 10 minor units. The server's integer is authoritative.

### 9. Alt text: an explicit choice, not an invented requirement

`ItemImageSet` allows an image with null alt text, normalizes blank to null,
and rejects alt text without an image. The UI therefore offers two explicit
branches — describe the image, or mark it decorative — and requires a choice
only for a **newly selected** image, as form-completeness guidance. Editing
an image that already has null alt text preselects "decorative", so nothing
forces a description onto an existing record. Clearing an image sends
`media_id: null` and no alt-text key at all; the invalid combination is made
unrepresentable by the adapter's type signature.

### 10. Uploads are honest about what the client can and cannot do

`accept` guides the file picker only. A clearly unsupported non-empty MIME
type is rejected client-side; an **empty or unrecognized** `File.type` is
accepted for submission, because some pickers report nothing for perfectly
valid images and the backend's magic-byte and decoded-format agreement check
is the authority. Size is displayed with advisory guidance only — the real
cap is a deployment setting the client cannot see, so no client-side block
pretends to know it.

While an upload is in flight the dialog's close, cancel, and Escape are
disabled, and in-app navigation and browser unload warn. The warning says
plainly that leaving does **not** cancel the upload, because the generated
client exposes no abort mechanism. An uploaded but unattached asset stays in
the library as pending and expires normally (ADR-017 R7); the library shows
its expiry rather than hiding it.

Uploading, attaching, detaching, and deleting are four different actions
with four different labels, because they have four different consequences.

### 11. Failure presentation distinguishes context, never existence

A workspace or initial item 404 renders the ordinary not-found experience.
A resource that disappears **during** a mutation does not: it explains that
the record changed or was removed, invalidates and refetches, and navigates
to the nearest valid parent only when the open record itself is gone. A
media 404 inside the picker drops the stale tile and keeps the picker
usable. A 403 after a role change explains the permission loss, invalidates
the session, and recomputes affordances from the refreshed authoritative
roles. 401 keeps the ADR-015 clear-session behavior unchanged.

Copy never distinguishes a foreign-tenant resource from a nonexistent one —
the backend's non-disclosure contract is preserved verbatim in the UI.

### 12. No undo, and no simulated undo

Every catalog and media delete is a hard delete; the backend exposes no
restore contract. Blueprint §13's "undo where safe" therefore has **no safe
case** in M3E. Proportionate confirmation is used instead, and deleted
records are never recreated to imitate undo — that would forge new
identifiers, new timestamps, and new audit events for a record the operator
believes was restored.

### 13. Contract fidelity: the dietary-tag registry is published

ADR-017 D6 rules the dietary registry closed and append-only, and the
service rejects unknown values — but the OpenAPI document advertised an open
`string[]`, so the generated client offered no union to check a UI list
against. Since `dietary_tags` is replaced wholesale on update, an unbacked
frontend list would silently drop a tag added later backend-side.

The four affected annotations now use the existing `DietaryTag` enum, so the
contract publishes what the service already enforces. Normalization,
canonical lowercase values, duplicate rejection, the per-item cap, and the
fail-closed read projection are unchanged; no route, database, authorization,
or catalog-service behavior changes. The frontend list is then a
**display-only mapping backed by generated values** (ADR-004), checked
bidirectionally at compile time so adding a tag backend-side fails the
frontend typecheck until the UI is updated.

### 14. Shared components stay app-local

No `admin-ui` or `design-tokens` package is created. ADR-015 decision 10 sets
the bar at a second real **application** consumer; the storefront consumes
none of this. Shared primitives live in `apps/control-center/src/components/`.

## Alternatives considered

- **Custom listbox switcher** — rejected: hand-written roving focus,
  type-ahead, Escape, outside-click, and portal handling is the highest-risk
  accessibility code in the milestone, bought for richer option markup.
- **Drawer or nested tab item editor** — rejected: a full page is
  deep-linkable, refreshable, back-button-correct, and is the right mobile
  primitive for a form carrying details, image, and modifiers.
- **Drag-and-drop reordering** — rejected (see ruling 5).
- **Toast library** — rejected: a dependency for a component the repository
  can express in a small provider, and none of them solve the modal-overlay
  ordering problem that actually matters here.
- **Floating notifications above the modal overlay** — rejected: visible but
  keyboard-unreachable inside a focus trap.
- **Optimistic updates** — rejected by ADR-017 D5.
- **Generating a third artifact of runtime enum values** — rejected: the
  contract check pins the generator's output set, and the generator
  architecture is not worth changing for three strings that a
  compile-time-checked constant covers.
- **Parsing `openapi.json` at runtime** — rejected: megabyte bundle, and the
  package deliberately exports only its facade.
- **Deferring dietary-tag editing out of M3E** — rejected once the contract
  correction was authorized; it would have shipped menu administration with
  a delivered M3A field left uneditable.
- **A standalone media route** — rejected for M3E: the library exists to
  serve item image attachment, and a separate destination invites orphaned
  uploads.

## Consequences

The control center gains its first business-facing area, and every later
business milestone inherits the workspace shell, the switcher, the
notification system, the form primitives, and the failure-presentation
vocabulary without re-deciding them. Three form dependencies enter the
workspace and must be maintained with the same exact-pin discipline as the
rest.

The dietary-tag correction means M3E is not strictly control-center-only:
backend annotations, backend tests, the OpenAPI document, and the generated
client all change, even though no behavior does. Any future closed registry
exposed as a bare string is now a known contract smell with a precedent for
fixing it.

Admin media previews are `no-store` by the M3C security ruling, so
thumbnails re-fetch on each mount; the overview mitigates this by preferring
the smallest available derived variant, with the canonical as the documented
fallback. Embedding variant metadata in `ItemSummary` would remove the
fallback but is a contract change for frontend convenience and was not made.

## Security and operations impact

No authorization rule changes. Every guard added here is presentation: the
membership guard reproduces the backend's non-disclosure outcome and issues
no request for a business the session does not contain, and the backend
independently returns 404 for nonmembers including platform administrators.
Capability-gated affordances are hidden or disabled for roles that lack
them, and a 403 that arrives anyway is rendered honestly rather than treated
as a defect.

CSRF handling is inherited unchanged: every unsafe call resolves the token
from the session cache at execution time. Only the envelope's own neutral
message, its field errors, and `details.limit` are ever rendered, always as
text. No storage key, path, or checksum can appear because the API never
emits one. No new audit action exists and no audit data is displayed.

## Reconsideration triggers

A second application consumer of the shared components (creates the
`admin-ui` package); the first genuine need for concurrent-edit detection
(M4 draft/composition revisits ADR-017 D5's versioning deferral); a catalog
that outgrows the single-request admin menu tree; adoption of a CDN or
signed media URLs (changes the preview cache decision); a request for
drag-and-drop backed by a reviewed accessible design; the first closed
registry that cannot be expressed as an enum in the contract.

## Delivery record

To be completed at M3E close-out.
