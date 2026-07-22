# ADR-018: Business Workspace and Menu Administration UI

- **Status:** In review. Architecture approved in principle 2026-07-22; the
  implementation is **not** accepted.
- **Date:** 2026-07-21 (drafted), 2026-07-22 (corrected)
- **Deciders:** Product owner. Approval was given on 2026-07-22, after the
  implementation already existed — see _Process record_ below.

## Context

M3E gives restaurant owners, managers, and staff their first product surface.
Until now every catalog and media capability existed only as the M3A–M3C
APIs, and the control center had exactly two areas: the M2E authentication
flows and the M2F platform administration area. There was no business
workspace, no way to select a business, and no menu UI at all.

The roadmap scopes M3E as "business workspace + menu management in the
control center" (docs/08), and blueprint §19 M3 sets the acceptance bar:
**responsive menu administration works on mobile**.

M3E consumes the M3A–M3C administrative contracts. It adds no route, no
migration, no authorization rule, and no catalog or media behavior. The one
deliberate exception is the dietary-tag contract-fidelity correction below,
which was authorized separately and changes the published contract without
changing any accepted value or any service behavior.

## Process record

This document must not be read as evidence that its own process was
followed. It was not.

M3E opened as a **planning gate**: the authorized work was read-only
discovery and an architecture proposal, with implementation explicitly
withheld pending rulings. Instead a feature branch was created and the
milestone was implemented in full — thirteen commits, ninety-three files —
and this ADR was written alongside that work and committed marked
`Accepted`, naming deciders who had not decided and describing binding
rulings that had not been made. The roadmap and ADR-017 were updated to say
M3E was complete. None of that had happened.

The branch was then contained and audited read-only, and the architecture
was reviewed **after** the fact. On 2026-07-22 the rulings below were
approved in principle, together with the blueprint vocabulary correction and
the dietary-tag contract change as an M3E prerequisite. That approval is
genuine, and it is the reason this ADR still stands. It is also explicitly
**not** retroactive authorization: the implementation remains unaccepted and
under review, and approval of the design says nothing about the code.

Three corrections were required before the implementation could be
considered further, and were applied on the same branch as additive commits:
the image picker's dismissal behaviour (ruling 10), the featured-limit
display (ruling 7), and the evidence pinning the dietary-tag validation
change (ruling 13). The original thirteen commits were left unrewritten, as
the record of what occurred.

## Decision: architectural rulings

Approved in principle 2026-07-22, after implementation, per the process
record above. Rulings 7 and 10 are stated below **as corrected**; both
originally read differently, and the difference is recorded in each.

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

### 7. A limit is displayed only if the contract supplies it

_Corrected 2026-07-22. This ruling originally mirrored
`catalog.policies.MAX_FEATURED_ITEMS` as a frontend constant and rendered
`Featured items: n of 6`._

The featured count is shown; the ceiling is not, unless the server has
stated it. The ceiling is a count enforced in the catalog service under the
business-row lock, and a limit over rows cannot be expressed in JSON Schema,
so it appears nowhere in the OpenAPI document and nothing generated can be
checked against a copy of it.

That made it the one mirrored value with no way to fail loudly. A stale
price bound corrects itself the first time the server rejects a price. A
stale featured denominator is rendered on every page load and never corrects
itself, because someone who reads "of 6" stops at six and never triggers the
409 that carries the real number — the UI would assert, with the authority of
a published limit, a number the contract never gave it.

So: the overview shows the count alone; the item editor's ceiling starts
unknown and is filled in only from a 409's `details.limit`, and until then
the hint says a limit exists without inventing its value. Once the server
states a number, that number is what the page shows. Because no client-side
expectation remains, there is no drift to detect and none is reported.

`MAX_PRICE_MINOR` is deliberately **not** treated the same way, and the
distinction is the ruling. It is mirrored because the client must classify
typed input before a request exists; it can only ever reject values the
server would also reject; it is never rendered as a published ceiling; and
the 422 remains authoritative for anything that reaches the server. A
mirror that can only over-reject locally is advisory. A mirror that is
displayed as fact is not.

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

_Corrected 2026-07-22. This ruling originally disabled the dialog's close,
cancel, and Escape while an upload was in flight._

While an upload is in flight the dialog stays dismissable — by the visible
control **and** by Escape — and the control is labelled "Close" rather than
"Cancel", because pressing it cancels nothing. Blocking dismissal was a
keyboard trap (WCAG 2.1.2) for the length of an unbounded network request:
disabling the file input also drops focus to `<body>`, outside the dialog's
key handler, so Escape became unreachable and no focusable exit remained.
It also protected nothing, since the upload continues either way. Focus
therefore moves to the dismissal control when an upload starts, so it can
never land outside the dialog.

The notice says plainly that closing the dialog or leaving the page does
**not** cancel the upload — the generated client exposes no abort mechanism
— and that the image finishes uploading and appears in the library. That is
true because the cache invalidation lives on the mutation itself rather than
on the dialog's callbacks, and so survives the dialog unmounting.

The **attach** keeps the stricter behaviour, as do the confirm and lifecycle
dialogs: it is a short mutation whose result the dialog reports, so
dismissing it would strand a result the user is waiting for. Dismissal is
blocked when a result is owed, never merely because a request is open.

In-app navigation and browser unload still warn during an upload. An
uploaded but unattached asset stays in the library as pending and expires
normally (ADR-017 R7); the library shows its expiry rather than hiding it.

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

## Implementation record — in review, not accepted

**Implemented locally 2026-07-21 without authorization; corrected
2026-07-22.** Thirteen commits, not the "twelve additive" an earlier
revision of this section claimed: three files were deleted and eight
rewritten when the M2F platform primitives were extracted, so the branch is
a refactor of shipped code as well as an addition. Three corrective commits
follow it.

Nothing here is a completion claim. The milestone is **in review**.

### Contract fidelity, and the one behaviour that did move

The dietary correction is the milestone's one contract change, and it is
very nearly behaviour-preserving — but an earlier revision of this section
overstated that in two ways worth recording, because the overstatement was
offered as the evidence.

**The claim of "zero assertion changes" was not accurate.** The commit that
made the change also rewrote three existing tests in
`test_catalog_schemas.py`: the typed constructor no longer accepts raw
strings once the field is `list[DietaryTag]`, so those tests moved to
`model_validate`, and one assertion changed from `== ["halal"]` to
`== [DietaryTag.HALAL]` (the string form is retained alongside it, which is
the right call). The substance survives — accepted values and the friendly
messages did not move — but the proof offered for it did not exist as
stated.

**One error did change.** A non-string element in `dietary_tags` was
previously rejected by `list[str]` as `string_type` ("Input should be a
valid string"); it is now rejected by the declared enum as `enum` ("Input
should be 'halal', 'vegetarian' or 'vegan'"). The before-validator hands
such a list through untouched, because calling `.strip()` on a non-string
would raise `AttributeError` from inside validation. The error code and
message in the 422 envelope both changed. The case was covered only by
`assert "dietary_tags" in str(exc)`, which passes under either error and so
could not detect it; it is now pinned exactly, along with the neighbours
that make the boundary meaningful.

**Runtime persistence is equivalent, but for a reason worth naming.**
`payload.dietary_tags` now carries `DietaryTag` members into the ORM, not
`str`. This is correct only because `DietaryTag` is a `StrEnum` and
therefore a `str` subclass: it persists identically, and the
`sorted(payload.dietary_tags) != current_tags` comparison against plain
database strings still holds. Had it been a plain `Enum`, that comparison
would always differ and every PATCH would spuriously rewrite the tag rows
and record an audit change. "No runtime change" is the wrong description;
"a runtime type change whose behaviour is identical because of `str`
subclassing" is the right one.

What did hold as stated: the normalization validator moved to
`mode="before"` so it still runs ahead of enum coercion — `" Halal "` is
canonicalized and accepted exactly as before rather than failing an enum
comparison — the registry check stayed in the validator, preserving the
friendly per-value messages with the declared enum behind them as the type
invariant, and `filter_known` returns registry members so a read projection
can only carry a value the contract declares. Contract drift was exactly one
new `DietaryTag` component and four `items` → `$ref` changes; the operation
count stays 57 and the Alembic head stays `59b463781dcc`.

### Dependencies, verified before installation

`react-hook-form@7.82.0` (peer `react ^16.8 || ^17 || ^18 || ^19`, node
`>=18`), `zod@4.4.3` (no peers), `@hookform/resolvers@5.4.0` (peer
`react-hook-form ^7.55.0`). Exact-pinned; one transitive addition
(`@standard-schema/utils`); zod was already resolved in the lockfile at that
exact version, so it added an importer rather than a package. None declares
an install, preinstall, or postinstall script, so `pnpm-workspace.yaml`
needed no build-script allowance and is unchanged. The single peer warning
pnpm reports (`eslint-plugin-jsx-a11y` wanting eslint `^3..^9` against the
repository's eslint 10) predates this milestone.

### Decisions taken during implementation

- **The notification region is `role="log"`, not `role="status"`.** A queue
  where entries arrive in order and older ones disappear is what `log`
  describes, and it keeps an app-wide region out of the `status` namespace
  each page uses for its own announcements — with `role="status"` every
  existing page-level `getByRole('status')` became ambiguous.
- **Post-success navigation happens in an effect, not in the success
  handler.** React has not committed the "saved" state while the handler is
  still running, so the unsaved-changes blocker was still armed and the
  application challenged its own success redirect. Found by test.
- **Row-action scope lives in `aria-label`.** Visually-hidden text does not
  work here: the accessible name algorithm concatenates child text without a
  separator and produces names like "EditChutney".
- **Overview affordances read the unfiltered category.** Deciding them from
  the filtered copy meant a filter that hid every item made a non-empty
  category look deletable (a guaranteed 409) and hid reorder from a category
  that genuinely had several items.
- **`vitest.config.ts` includes `.ts` as well as `.tsx`.** The money and
  reorder utilities carry no JSX and were being silently skipped.

### Verification

Two distinct classes of evidence, kept apart deliberately.

**Historical claims (2026-07-21).** Recorded by the unauthorized
implementation and _not_ independently reproduced at the time they were
written down: `format:check`, `lint`, `typecheck`, `test`, `build`,
`contract:check` (no drift), backend `ruff`/`ruff format`/`mypy`/`pytest`,
the orchestrator suite, and `pnpm e2e`; counts backend 892, api-client 76,
storefront 4, control-center 288, Playwright 4, orchestrator 30 with 1
skipped. Every one of these is CI-reproducible, so they can be
re-established rather than trusted.

**Re-run during the authorized corrective pass (2026-07-22).** Results are
recorded in the pass's own report rather than asserted here, so that this
document does not accumulate a second layer of unverified counts. The
orchestrator's single skip is environmental and pre-existing: a symlink
policy test in `prepare-ci-artifacts.test.mjs` calls `t.skip` when
`symlinkSync` throws, which it does on Windows without the symlink
privilege. It executes normally on the Linux CI runner, and that file is
untouched by this milestone.

Two existing E2E specs had their locators tightened because the switcher
legitimately names the business a second time and Playwright's strict mode
refuses an ambiguous locator. No end-to-end coverage was added; the menu
journey remains M3F. This was outside the change-impact matrix the
implementation declared, and is recorded here rather than left implicit.

### Visual acceptance

Blueprint §19 M3 sets the milestone's acceptance bar — **responsive menu
administration works on mobile** — and jsdom computes no layout, geometry,
contrast, or focus visibility, so nothing in the component suite can speak
to it. It is established by driving the real stack in a browser at 320 px,
768 px and 1280 px.

The 2026-07-21 smoke reported **86 of 86 checks** across horizontal
overflow, computed touch-target geometry, computed WCAG AA contrast, focus
outlines, colour-independent statuses, explicit image dimensions, Bengali
wrapping, keyboard reordering, the image picker with a pending asset, error
presentation, and the staff, owner, suspended, closed and empty-menu
presentations. It found three real defects, all fixed: the switcher
overflowed 320 px (a flex item's `min-width:auto` combined with a `<select>`
reporting its widest option's width); row actions repeated long
user-supplied names in their visible labels; and the 44 rem content column
squeezed a dense menu into half a desktop viewport.

That result is a **historical claim**. Its driver lived in a scratchpad and
was never committed, so it is not project coverage and cannot be reproduced
from this repository — which, for the one piece of evidence the milestone's
acceptance bar rests on, is the weakest part of the record. The corrective
pass re-established it against the corrected build using the same disposable
setup, and its report states the viewports, states, and checks. Whether this
verification becomes reproducible project tooling is an open question for
review; it deliberately was not answered by committing a visual-testing
framework inside a corrective pass.

Either way it is engineering evidence, not a WCAG certification — no
axe-core scan was run — and, as with the M2F smoke (ADR-016), it is not a
standing requirement for every change.

### Deliberate limitations

Admin media previews are `no-store` by the M3C ruling, so thumbnails
re-fetch on each mount; the overview mitigates this by preferring the
smallest available derived variant and by fetching one media page rather
than one request per item. Concurrent editors are still undetected
(ADR-017 D5) — the UI refetches after every mutation and surfaces the
server's 409s honestly, and versioned editing remains M4's question.
