# ADR-020: Storefront Composition, Versioning, and Publication (Milestone 4)

- **Status:** Accepted (architecture); delivery records filled per
  sub-milestone — **M4A and M4B delivered**, M4C not started
- **Date:** 2026-07-26
- **Deciders:** Product owner, principal architect

## Context

Milestone 3 delivered a manageable catalog, a host-resolved public menu
API, and public media delivery. It delivered no customer-facing site:
`apps/storefront` is still the Milestone 1 shell, and a tenant's menu
exists publicly only as JSON. Blueprint §7.4 and §12 define the missing
piece — a governed composition model where the platform controls structure
and the restaurant controls content, with transactional draft/publish and
immutable history.

Three earlier decisions deliberately deferred work to this milestone and
are closed here:

- **ADR-017 D5** left concurrent-edit detection open: "row locks serialize
  writes but do not detect stale editors… versioned editing is revisited
  with M4's draft/composition architecture."
- **ADR-017** rejected versioned publication inside M3 because
  "draft/publish belongs to storefront composition, M4", and committed that
  "M4's storefront consumes the public menu and media source metadata
  **without media-schema migration**."
- **ADR-013** deferred public caching: "public caching is still deferred
  (M4); when it lands, any cache key must include the resolved Business."

Milestone 4 is also the first milestone whose absence blocks a verification
commitment: mandatory end-to-end journeys 2 and 3 (`docs/06`) cannot be
completed until a storefront publishes and renders.

## Decision

### 1. Scope, and what M4 is not

M4 delivers storefront composition and publication: the section registry,
validated configurations, design governance, draft/publish/history, the
server-rendered storefront, SEO basics, and English/Bengali rendering
verification. Exit criteria (blueprint §19): invalid config cannot save; a
published config always renders; draft is never public; performance and
accessibility budgets pass.

M4 contains **no ordering functionality of any kind** — no cart, checkout,
pricing, order snapshot, or "Order Online" call to action. It contains no
hours or "open now". The boundaries are explicit:

- **M5** owns weekly hours, exceptions, and next-pickup computation. No
  section may carry an hours or opening-times field, including as free
  text: docs/03 requires structured hours plus the tenant timezone, and a
  storefront text field would pre-empt that decision.
- **M6** owns cart, checkout, server-authoritative pricing, and immutable
  order snapshots. M4's only seam is `hero.primary_action`, a closed enum
  containing exactly `none` and `view_menu` in M4. `view_menu` is ordinary
  in-site navigation to the menu — not an ordering action. M6 extends the
  enum with an entitlement-gated ordering member. No `/order` route is
  implemented, and the sitemap emits only routes that exist.
- **M10** owns campaigns and placements. Registering a new section type is
  the extension mechanism; M4 registers none of them.

Also out of scope: custom domains (ADR-013), tenant CSS/JavaScript/HTML
(§12.3), rich text, a general-purpose page builder, `/about` and `/contact`
pages (story and contact are homepage sections), customer accounts, and any
media schema change.

### 2. A `storefront` bounded context with two code-owned registries

Storefront owns design variants, the section registry, composition
configuration, the version lifecycle, publication history, and the public
projection. It references catalog items and media assets **by id** and
copies neither: a storefront must render the _current_ menu. Immutable
transactional snapshots belong to Orders (M6), where frozen history is the
correct behavior; freezing prices into a published page would be a defect.

**The section registry** is a typed discriminated union on `type`, with
`extra="forbid"` throughout. Five types ship: `hero`, `menu`, `story`,
`contact`, `gallery`. A type the registry does not declare cannot be
validated, stored, or rendered. All copy is plain text, Unicode-normalized
to NFC — which matters for the launch market, because Bengali combining
sequences have multiple encodings of the same text and only a normalized
form compares and measures consistently. Control characters are rejected
rather than stripped. At most one section of each type may exist: the
standing guard against drifting into a page builder.

The `menu` section deliberately carries **no** item selection. Which items
appear, in what order, and which are featured is already catalog's answer
through the public menu projection and the centralized featured policy; a
second selection here would be a competing source of truth.

**The design-variant registry** is likewise code-owned and append-only,
with an explicit `PLATFORM_DEFAULT_VARIANT` rather than an implicit
"first member of the enum" rule. Exactly one variant ships in M4A: a
variant is a _renderer_ contract, and no renderer exists until M4D, so
naming more would publish structure nothing can render.

### 3. One table: `storefront_versions`

Every draft, published, and archived composition lives in one tenant-owned
table. There is no separate publication-events table: `storefront_versions`
already _is_ the version history owners see, and `audit_events` already
records actor activity — a third store would duplicate both.

`design_variant` lives on the version row, never on `businesses`.
Published and archived rows therefore keep the variant they were rendered
with, so reassigning a design never rewrites how history looked. There is
no `businesses.design_variant` column and must not be one.

Database-enforced invariants: two partial unique indexes give the blueprint
§9.2 singletons (at most one `draft` and at most one `published` per
business); a paired CHECK ties "is a draft" to "has no version number" in
both directions; publication timestamp and actor arrive together and never
on a draft; `UNIQUE (business_id, id)` backs a tenant-safe composite self
foreign key so provenance can never cross tenants; and `config` must be a
JSON object.

### 4. The version lifecycle

```text
draft ──publish──▶ published ──(next publish)──▶ archived
  ▲                    │
  └──── seeds new ─────┘
```

Each business has **at most one mutable draft**, carrying
`version_number = NULL`. **Version numbers are minted only during
publication.** Publishing promotes the draft, archives the previous
published version, and seeds a new singleton draft from the published
result — all in one transaction under the `businesses` row lock.

**Restore overwrites the current draft in place** from an archived version,
copying both its configuration and its `design_variant`. It never
publishes, and it requires the current draft's `lock_version` so a
concurrent editor is not silently discarded. The control center must warn
that restoring replaces current draft work and require deliberate
confirmation. Published and archived rows are never mutated; publishing the
restored draft creates the next numbered version.

Owner-facing history contains published and archived versions — not every
draft edit.

There is **no unpublish**. It is not authorized, and adding it needs a
separate decision.

### 5. Lazy initial-draft creation, and the first-draft race

Existing businesses have no `storefront_versions` row after the migration
and are **not** backfilled. Instead:

1. **Storefront reads never create state.** A business with no draft reads
   as absent, and the workspace shows a first-use state.
2. When no draft exists, an authorized owner/manager first draft write may
   create it lazily.
3. The initial draft uses the explicit code-owned default design variant,
   the submitted validated configuration, `state = draft`,
   `version_number = NULL`, `lock_version = 0`, `source_version_id = NULL`,
   and null publication fields.
4. A creation request uses an explicit **create-state concurrency
   representation** — an omitted or null expected lock version — not a
   guessed `0`, so "I believe none exists" and "I believe it is at 0" stay
   distinguishable.
5. If a draft already exists when a create-state request arrives, the
   response is the established stale/conflict response; it never overwrites.
6. An ordinary update to an existing draft requires its exact
   `lock_version`.
7. An authorized platform design-assignment command may also create the
   first draft, using the registry's initial configuration, the explicitly
   requested valid variant, `lock_version = 0`, and recording
   `storefront.design_assigned` with `previous_variant = null`. Creating
   that first default draft **does** count as an effective assignment:
   state came into existence that did not exist before, so the audit event
   is accurate rather than noise.
8. All creation paths take the business row lock first, so concurrent owner
   and platform attempts serialize and only the first creates the draft.
9. Whichever command runs second operates against, or conflicts with, the
   now-existing draft according to its own contract.
10. Owner and manager requests can never supply `design_variant`: the field
    is absent from their schema, so submitting one is a 422 rather than a
    silently ignored value.

### 6. Optimistic concurrency and platform design assignment

`lock_version` is the concurrency token for the mutable draft. Every
effective draft mutation increments it, and a stale write is a `409`
carrying the current value — never a silent overwrite.

The platform design command is serialized by the business row lock. It does
**not** accept an owner-facing `lock_version`, because it changes only the
platform-owned variant field. Every effective assignment still increments
the draft's `lock_version`, so a concurrent owner submission based on the
previous version fails safely. Lifecycle validation happens **before**
no-op suppression: a design request against a closed business is
`409 invalid_state`. On an eligible business, assigning the
already-selected variant is an exact no-op — no mutation, no lock
increment, no audit event — following the M3C exact-no-op-suppression
precedent.

### 7. Authorization

Three capabilities, appended to the registry in the change that first
enforces them. Broad `business.view` is deliberately **insufficient** for
any storefront administration read.

| Action                  | Owner                            | Manager | Staff  | Platform admin                  |
| ----------------------- | -------------------------------- | ------- | ------ | ------------------------------- |
| View config and history | ✅ `business.storefront.read`    | ✅      | ❌ 403 | ❌ 404                          |
| Preview draft           | ✅ `business.storefront.read`    | ✅      | ❌ 403 | ❌ 404                          |
| Edit draft              | ✅ `business.storefront.write`   | ✅      | ❌ 403 | ❌ 404                          |
| Publish                 | ✅ `business.storefront.publish` | ❌ 403  | ❌ 403 | ❌ 404                          |
| Restore                 | ✅ `business.storefront.publish` | ❌ 403  | ❌ 403 | ❌ 404                          |
| Assign design variant   | ❌ 403                           | ❌ 403  | ❌ 403 | ✅ `platform.businesses.manage` |

The two failure modes stay distinct, per the established contract: a
**non-member** — including a platform administrator, who holds no
membership — receives the non-disclosure **404**; an **authenticated
same-tenant member lacking the capability** receives **403**, because
existence is already known to them and concealment would be theatre.
Platform administrators gain no tenant publication authority.

### 8. Business lifecycle

Storefront administration and publication are permitted while a business is
`provisioning`, `active`, or `suspended`, so an owner may prepare and
publish before go-live or while hidden. Public resolution keeps returning
the established neutral 404 until the business is publicly eligible, and
suspension hides the storefront without modifying its published version.

`closed` is terminal and immutable, and the guard applies to **every**
storefront mutation — initial draft creation, draft update, publication,
restoration, and platform design assignment — returning
`409 invalid_state`. Administrative reads and history remain readable under
the capabilities above. This preserves the shipped M3 rule rather than
inventing an exception: `app/domains/catalog/service_support.py` already
refuses to "modify the catalog of a closed business", and extending
storefront writes to closed businesses would make storefront the only
domain that mutates a closed tenant.

### 9. Draft privacy and preview

Draft content is never reachable anonymously. Preview is an **authenticated
control-center endpoint** that shares the public projection assembler and
differs only in which version row it reads and which media URL builder it
injects. Preview responses are `no-store` and non-indexable. **No public
preview tokens or tokenized preview URLs exist**, in M4 or by later
convenience.

### 10. Media: the M3D authorization predicate is extended, the schema is not

**M4 extends the M3D public-media authorization predicate without changing
the media schema.** No media table, column, or migration is added.

This is necessary because the M3D rules make hero and gallery imagery
impossible on their own: `pending → active` promotion happens only in
`claim_for_attachment`, called only by the catalog item-image command, so a
storefront-only asset would expire 48 hours after upload; and delivery
additionally requires a non-hidden menu item in a visible category to
reference the asset, which a dining-room photo never satisfies.

The decision:

- A successful storefront-draft update may **claim** eligible same-business
  pending media through a storefront attachment operation.
- Claiming and the accepted draft mutation are **transactional**: validation
  precedes claiming, and failed validation leaves nothing claimed.
- Claiming makes the asset active but does **not** make it anonymously
  public.
- Public delivery becomes eligible when **either** the existing
  catalog-public predicate succeeds **or** the asset is referenced by the
  **currently published** storefront version of the same resolved business.
- Draft-only, archived-only, unpublished, cross-business, missing, and
  removed references authorize nothing.
- If the published version still references an image while a newer draft
  removes it, the image stays public until that newer draft is published.
- Once publication removes the final qualifying reference, anonymous
  delivery returns the established neutral 404 unless another valid catalog
  or published-storefront reference remains.
- **Cross-business references fail storefront validation with 422 before
  any claim occurs.** Missing or unusable same-business media may degrade
  under the approved warning behavior, but degradation removes a reference
  and can never grant access.
- No automatic deletion or demotion of active assets is introduced;
  retention continues under the existing M3 media lifecycle.

Draft-only media is previewed through the **existing** authenticated route
`GET /api/v1/businesses/{business_id}/media/{asset_id}/file/{variant}`,
which already serves pending assets with `no-store` and `nosniff`. No new
media delivery surface is created.

### 11. Audit uses the existing administrative stream

Three actions are appended to the existing append-only registry:
`storefront.published`, `storefront.version_restored`, and
`storefront.design_assigned`. Detail payloads are bounded typed schemas
with **scalar** fields only — a `section type → count` map would introduce
dynamic keys and break the closed-key-set guarantee that
`tests/unit/test_audit_details.py` enforces.

`storefront.draft_updated` is **not** recorded: it would fire on every save
and turn high-volume operational telemetry into administrative audit
records. Configuration JSON, restaurant copy, tokens, and any other
unbounded content are never recorded. Version mutations and their audit
events commit atomically. Public reads write no audit events, per the
ADR-013 amplification and enumeration rationale.

### 12. Public caching

`GET /api/v1/public/storefront` 200 responses carry
`Cache-Control: public, max-age=60`. Errors, unknown and unpublished
tenants, and preview are `no-store`; storefront HTML is `no-store`.

Because server rendering may consume a public API response that remains
usable for up to 60 seconds, the **effective maximum visitor-visible
staleness and post-suspension exposure is 60 seconds**. No smaller figure
is claimed, and none may be claimed unless an implementation proves that
server rendering bypasses every client, framework, intermediary, and origin
cache. Cache identity includes the resolved Business, with a permanent
isolation test and a recorded M8 requirement that any reverse-proxy cache
key include the Host. Caching is granted by route identity through the
existing middleware; no caching dependency is introduced.

## Alternatives considered

- **A separate `storefront_publication_events` table** — rejected: it would
  duplicate both the version history owners already read and the audit
  stream that already records actor activity.
- **`businesses.design_variant`** — rejected: it breaks historical
  rendering stability (reassigning a design would silently change how an
  archived version renders) and duplicates state the version row holds.
- **A new draft row per restore** — rejected: it burns version numbers and
  needs a rule for discarding the superseded draft. The draft is a working
  copy, not history; history is what must never be mutated.
- **Tokenized public preview URLs** — rejected: a public attack surface in
  exchange for owner convenience, when an authenticated preview is
  available.
- **A media schema change to mark storefront attachments** — rejected: the
  predicate extension achieves the same outcome with no migration, honoring
  the ADR-017 commitment.
- **Restricting hero and gallery to menu-attached images only** — rejected:
  it would reduce a gallery to menu photos and make the section pointless.
- **Runtime JSON-Schema validation** — rejected: Pydantic discriminated
  unions validate at least as strongly, reach OpenAPI, and are checked by
  mypy.
- **Rich text, Markdown, or tenant CSS** — rejected by blueprint §12.3.
- **A general-purpose page builder** — rejected: the governance split
  between platform structure and tenant content is the product.
- **Seeding the initial draft with placeholder copy** — rejected: it would
  fabricate tenant content in code, in one language, for a market the
  product documents as Bengali-capable.

## Consequences

M4 lands as six reviewable slices (M4A–M4F) with one additive migration and
no change to any existing table. Mandatory end-to-end journeys 2 and 3
become completable for the first time.

Composition gains optimistic concurrency while catalog keeps its row-lock
semantics — a deliberate asymmetry, justified because composition has a
long-lived editing session and catalog does not.

Public media delivery gains a second authorization path, so the isolation
matrix must prove each path independently, and must prove that a draft-only
reference authorizes nothing.

The public storefront becomes the first unauthenticated expensive surface;
bounded caching mitigates it and the full rate-limit regime remains M8.

New obligations created: M4B must implement the claim/validation ordering
in §10 and the authorization matrix in §7; M4C must extend the delivery
predicate and prove cache isolation; M4D must render an empty published
configuration coherently, because the default draft has no sections.

## Security and operations impact

Every new row is tenant-leading, with a composite tenant-safe self foreign
key so provenance cannot cross tenants. Draft content and draft-only media
are unreachable anonymously. Capability denial (403) and non-membership
(404) stay deliberately distinguishable, matching the established contract.
No tenant HTML, CSS, or JavaScript is accepted anywhere. Control characters
in copy are refused rather than stripped, so stored text is exactly what the
owner can see. No customer personal data and no money values exist in any
storefront table. Publication, restoration, and design assignment are
audited with bounded payloads; draft edits are not audited.

One operational detail found during M4A and worth keeping: PostgreSQL
truncates identifiers at 63 bytes, and the naming convention would have
generated a 70-character name for the composite self foreign key, leaving
the model and the database disagreeing about it. The constraint is named
explicitly, and a permanent test now bounds every generated identifier
across the whole schema.

## Reconsideration triggers

M5 hours sections; M6 ordering entry points (the first extension of
`HeroAction`); M10 campaign placements; custom-domain support (ADR-013);
S3/CDN adoption, which changes both media URL strategy and caching;
evidence that archived-version retention needs pruning; a demonstrated need
for per-locale composition versions; or a second `schema_version`, which
must decide how the first is migrated or rejected.

## Delivery record

### M4A — Storefront foundation: delivered, 2026-07-26 (merged 2026-07-27)

One migration (`a41d9c7e5b30`, revises `59b463781dcc`) creates
`storefront_versions` and nothing else: no `businesses` alteration, no
media-schema change, no backfill, no existing row rewritten.

The domain module ships the section registry (`sections.py`), the
composition contract (`composition.py`), the design-variant registry
(`variants.py`), policy constants and text normalization (`policies.py`),
and persistence (`models.py`). No routers, services, commands, media
claiming, preview, public projection, or caching — those are M4B and M4C.

Verification at delivery: backend **937** tests (895 at the Milestone 3
head, +42 for storefront), ruff lint and format clean, mypy strict clean
across 166 source files. The migration is proved against disposable scratch
databases only: upgrade from the pre-M4A head over **real M3 rows** with a
byte-identical before/after snapshot, fresh install to head, the stepwise
walk, the ORM-metadata-versus-migrated-schema diff, single-field
perturbation tests for every named CHECK, both partial-unique singletons,
tenant-safe provenance rejection, RESTRICT in both directions, and
downgrade/re-upgrade with earlier data intact.

Merged to `main` via PR #19:

- Reviewed feature head: `6beeffbbd183b50537cead22c99eebdc0962fef0`.
- Merge commit: `aa30361e8b3c5ef334134996b341642b828d7aa8` — ordered
  parents `02827903a3e886ce381beaa24889fdaef78d5147` then
  `6beeffbbd183b50537cead22c99eebdc0962fef0`; the merge tree equals the
  reviewed feature-head tree.
- Branch CI run `30233128216` (pull_request) and post-merge push CI run
  `30233615592` (on the merge SHA) both completed successfully — all five
  jobs (repository-contract, backend, frontend, contract, e2e) green, zero
  artifacts.

**M4B remains the boundary and is not started.** Services, endpoints, the
capability registry additions, audit-event emission, media claiming, the
public predicate extension, preview, caching, and all UI are outside this
sub-milestone.

### M4B — Administrative API, publication, restore, design assignment: delivered, 2026-07-28 (merged 2026-07-29)

Approved architecture (the M4B discovery report and its restore
correction addendum: rulings D-1–D-8 plus two recorded completions),
fixed before implementation:

- **D-1 — Preview belongs to M4C**, beside the public projection
  assembler it shares. No preview endpoint exists in M4B.
- **D-2 — Administrative read surface.** The overview is the draft's
  **only** read representation, with `draft: null` as the valid
  first-use absence (reads never create state, §5.1); the version
  history is the current published row plus archived rows, newest
  first, limit/offset paged; the version detail exposes published and
  archived rows only — the draft's id there is the same 404 as an
  unknown or cross-tenant one.
- **D-3 — Publication requires `expected_lock_version`.** An owner
  approves content, not a row id: a draft that changed since it was
  read is a 409 carrying the current value, exactly like restore's
  guard.
- **D-4 — Restore accepts archived sources only.** Restoring the
  current published row is deliberately unsupported; a same-business
  source in any other state is 409 `invalid_state`, an unknown or
  cross-tenant id the indistinguishable 404, a missing draft 409
  `invalid_state` (defensive — unreachable through the API), and the
  ordering is fixed: capability → Business lock → lifecycle gate →
  source resolution → source state → draft existence → lock match →
  fail-closed source validation → mutation + audit.
- **D-5 — Draft writes** are full-document create-or-update at one PUT
  with the §5.4 intent representation (omitted/null
  `expected_lock_version` = create; an integer = update), canonical-dump
  no-op comparison, and exact-no-op suppression (no write, no claim, no
  increment, no `updated_at`, no audit).
- **D-6 — Media-reference failures.** Unknown, cross-business, and
  non-image references are one indistinguishable 422 raised **before**
  any claim; an expired same-business pending asset is the established
  409 `invalid_state` from the shared `claim_for_attachment` path.
- **D-7 — Seven operations, 57 → 64:** `storefront_get`,
  `storefront_draft_put`, `storefront_publish`,
  `storefront_versions_list`, `storefront_version_get`,
  `storefront_version_restore`, `platform_business_design_set`.
- **D-8 — Bounded scalar audit details:** `storefront.published`
  {version_number, design_variant, schema_version, section_count};
  `storefront.version_restored` {restored_from_version_number,
  design_variant}; `storefront.design_assigned` {previous_variant?,
  new_variant} with `previous_variant` **absent** exactly on the
  first-draft creation path (§5.7) — creation is encoded without a
  boolean, keeping the projection value union string/int.
- **Completion 1:** a persisted config or variant that fails fail-closed
  re-validation (publish, restore, or any read projection) propagates to
  the existing opaque `500 internal_error` boundary — no new public
  error code, no mutation, no audit event.
- **Completion 2:** every successful restore is an intentional,
  effective mutation — a repeated restore from the same archived source
  still increments `lock_version`, refreshes provenance, and emits a
  new audit event.

**Delivered, 2026-07-28.** No migration: the Alembic head stays
`a41d9c7e5b30` and no backfill runs — lazy first-draft creation (§5) is
the compatibility mechanism. The storefront domain gained
`service_support.py` (the capability → Business-lock → lifecycle
preamble), `repository.py` (tenant-scoped throughout; the history query
carries `version_number IS NOT NULL` literally, the form the partial
index declares), `schemas.py`, `service.py` (draft, publish, restore,
history, design assignment), and the two routers. Three capabilities
appended per §7 (`business.storefront.read`/`.write` owner+manager,
`.publish` owner only; `business.view` remains insufficient for any
storefront read, so staff receive 403 on reads). Three audit actions
appended per §11 with typed read-time projections whose design-variant
extractor follows the live append-only registry; publication statement
order is fixed against the partial-unique singletons (archive → flush →
promote → flush → seed). Media claiming implements the §10 ordering
under the Business lock, which media mutations also take first, so
validate-then-claim cannot race a delete. The api-client gained the
`storefront` facade group and `platform.setDesign`; both committed
contract artifacts were regenerated through the pinned toolchain.

One deliberate implementation note: the design-assignment no-op check
compares the stored variant string rather than enum members, because
with the registry at exactly one entry a member comparison is provably
constant; the effective-reassignment branch is the seam the second
registered variant (M4D+) will use, and its mechanics — increment,
audit, the §6 stale-owner conflict — are proven with an explicit
stand-in that bypasses only the request schema's enum and the strict
acknowledgment construction, never the service.

Verification at delivery: backend **1014** tests (937 at the M4A head,
+77 for M4B), ruff lint and format clean, mypy strict clean; workspace
TypeScript strict, ESLint, and Prettier clean; api-client Vitest **88**
(76 + 12); `contract:check` byte-current at exactly 64 operations.
Coverage spans the first-draft and owner-versus-platform creation races
(two sessions on the Business lock), the complete draft/publish/restore
failure matrices including commit-failure audit atomicity and
corrupt-source fail-closed behavior, the claim-ordering story, and the
full HTTP authorization/isolation matrix (anonymous, CSRF, staff 403 on
reads, manager 403 on publish/restore, nonmember and platform-admin
404, cross-tenant version-id indistinguishability, the opaque 500).

Merged to `main` via PR #21:

- Reviewed feature head: `a3728296fa069a1d5dc332e20c2d5291b490a06c`.
- Merge commit: `4359df2aad94a8cb67241bc849aee72adfb79e6d` — ordered
  parents `b1215e0f5a8dda674255b470616de954cd5652ea` then
  `a3728296fa069a1d5dc332e20c2d5291b490a06c`; the merge tree equals the
  reviewed feature-head tree.
- Branch CI run `30414469507` (pull_request, on the reviewed head) and
  post-merge push CI run `30414948826` (on the merge SHA) both completed
  successfully — all five jobs (repository-contract, backend, frontend,
  contract, e2e) green, zero artifacts. The e2e job in each run executed
  the full nine-test Playwright suite against its disposable database;
  the preserved development and UAT environments were untouched
  throughout.

**M4C remains the boundary and is not started.** The public projection,
the media delivery-predicate extension, preview, and caching are outside
this sub-milestone.

### M4C — Public projection, media predicate extension, and caching

Not started.
