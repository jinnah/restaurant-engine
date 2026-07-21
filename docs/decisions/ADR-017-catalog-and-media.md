# ADR-017: Catalog and Media (Milestone 3)

- **Status:** Accepted (architecture); delivery records filled per
  sub-milestone
- **Date:** 2026-07-19
- **Deciders:** Product owner, principal architect

## Context

Milestone 3 delivers the roadmap's catalog and media scope: categories,
items, modifiers, integer minor-unit money, availability, sorting, the
featured policy, safe media adapter/upload, restaurant menu administration
UI, and the public menu API (blueprint §19 M3, §7.3, §7.5; docs/03). The
architecture went through a source-grounded proposal, a corrections
addendum, and binding product-owner rulings — all recorded here before
implementation. This ADR is the milestone's architecture record; each
sub-milestone appends its delivery record as it lands.

## Decision: delivery decomposition

Six independently reviewed sub-milestones, one gated PR each:

| Sub | Scope                                                                                                                                                    | Depends on                                                  |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| M3A | Catalog core backend: categories, items, dietary tags, pricing, availability/hidden/featured, reorder, capabilities, admin APIs, audit, isolation matrix | —                                                           |
| M3B | Modifiers backend: groups/options, selection rules, satisfiability                                                                                       | M3A                                                         |
| M3C | Media backend: media domain, local storage adapter, upload pipeline, responsive variants, lifecycle, sweep, item image attachment                        | M3A                                                         |
| M3D | Public menu API + public media delivery                                                                                                                  | M3A–M3C                                                     |
| M3E | Menu administration UI (control-center business workspace)                                                                                               | M3A–M3C contracts (+ any M3D behavior it directly consumes) |
| M3F | Playwright menu journey, verification, close-out                                                                                                         | all earlier                                                 |

## Decision: binding architectural rulings

The following rulings are fixed for all of M3. Later sub-milestones
implement them without re-deciding.

### Naming and scope (D2, D10)

Domain module `catalog`; blueprint §9 table vocabulary (`menu_categories`,
`menu_items`, `modifier_groups`, `modifier_options`); administrative paths
under `/catalog/...`; the public projection at `/public/menu`. No generic
commerce/SKU/inventory abstractions. Modifier groups belong to exactly one
menu item; options to exactly one group; no reusable cross-item modifier
library in M3.

### Featured policy (R1)

Maximum **6** featured items per business — a centralized code policy
constant, not tenant-configurable in M3. The limit counts every item with
`is_featured = true`, including hidden items. Hidden featured items keep
the flag (hiding never silently clears it) and are excluded from the
public menu; unavailable items may remain featured. Enforcement runs under
the business-row lock; exceeding the limit returns the existing `conflict`
code (409) with a stable message and `details.limit = 6`. No
`featured_limit_reached` code.

### Product and payload bounds (R2)

Code policy constants (only the media-upload byte limit is a deployment
setting): 50 categories/business · 300 items/business · 100 items/category
· 10 modifier groups/item · **600 modifier groups/business** · 30 options/
group · **3000 options/business** · 3 dietary tags/item · media-list page
limit 100 · upload default 10 MiB, configurable maximum 20 MiB · decoded
image maximum 25 megapixels · maximum dimension 8000 px/side · name 120 ·
category description 500 · item description 1000 · contextual image alt
300 · sanitized original filename 160 · reorder payloads bounded by their
scope limit. Count-dependent checks run under the business-row lock. M3A
implements the category/item/dietary/featured/text/reorder bounds; the
modifier and media bounds land with M3B/M3C.

### Item price bound (F1 post-review ruling, 2026-07-19)

`price_minor` is bounded to **0 ≤ price_minor ≤ 10,000,000** minor units
(replacing an unapproved 1,000,000 ceiling found in independent review).
Rationale: the bound keeps public and audit representations bounded;
prevents unrealistic or accidental extreme values; still permits every
realistic restaurant and catering price; and remains a product-policy
constant, never a tenant setting. Enforcement is layered: the schemas
reject out-of-range values with the standard 422, and the named database
CHECKs (`ck_menu_items_price_nonnegative`, `ck_menu_items_price_maximum`)
are the final integrity boundary. The audit price extractor shares the
same constant, so every valid price — including the exact maximum — is
faithfully retained by audit projections.

### Media encoding and responsive images (R3, R4 — M3C)

The canonical stored asset is not the untouched upload: EXIF orientation
is applied, then the image is downscaled to at most 2560 px on the longest
side, re-encoded to WebP with metadata stripped (alpha preserved).
Responsive variants at widths 320/640/1280 are generated only where the
variant width is smaller than the canonical width — never upscaled.
Storage keys are internal and never appear in URLs, responses, audit, or
logs; delivery uses opaque asset ids and logical variant names.

### Error codes (R5)

`payload_too_large` (HTTP 413) is the only approved new M3 error code,
added in M3C with its first use. M3A uses the existing registry honestly:
`validation_error` (422), `not_found` (404), `permission_denied` (403),
`conflict` (409), `invalid_state` (409).

### Name normalization and uniqueness (R6)

Names are normalized on write: trim → collapse internal whitespace runs →
Unicode NFC; empty rejected. Case-insensitive uniqueness is DB-backed via
unique expression indexes on `lower(name)`: category names unique per
business; item names unique per category (the same normalized name may
exist in different categories); group/option uniqueness follows in M3B.
Service prechecks give friendly errors but the index is the invariant;
integrity races convert to the same safe 409 `conflict`.

### Media retention (R7 — M3C)

Uploads begin `pending` (48-hour TTL, database clock). First valid
attachment promotes to `active`. Ever-attached active assets are never
automatically deleted merely for being unreferenced — explicit deletion
only; referenced media cannot be deleted. Public delivery never serves
pending media; authorized admin preview may. Sweep follows the approved
cleanup matrix (storage-only orphans and expired pending are deletable;
rows-without-objects are report-only).

### Upload handling (binding M3C correction)

Authenticate, CSRF-validate, authorize the capability, and validate the
business lifecycle **before** application-controlled multipart parsing
(the endpoint declares no body parameters, so the framework cannot
pre-parse). Require and validate `Content-Length`; enforce a running
streamed-byte cap regardless; stream into a bounded spooled temporary
file (small in-memory threshold) — never an unbounded or multi-MiB
in-memory buffer; guarantee temporary-data cleanup on success, rejection,
exception, and disconnect; parse only after the bounded body is received;
accept exactly one expected file field.

### Concurrency (D5)

No version columns in M3. Mutations run in transactions under
`SELECT … FOR UPDATE` with deterministic lock ordering (Business first);
reorders are full-set, atomic, set-validating, and position-normalizing;
the control center invalidates and refetches after every mutation.
**Row locks serialize writes but do not detect stale editors:** concurrent
valid edits use last-committed-write semantics unless a structural
invariant produces a 409. Versioned editing is revisited with M4's
draft/composition architecture.

### Authorization (D4)

Append-only capabilities: `business.catalog.write` (owner, manager) and
`business.catalog.availability` (owner, manager, **staff**). Reads use the
existing `business.view`. The availability toggle is a separate workflow
command, never part of the general item PATCH. `business.media.write`
(owner, manager) follows in M3C. Platform administrators hold no
membership and receive the established non-disclosure 404 on business
catalog routes. Lifecycle: provisioning/active/suspended businesses allow
authorized administration; closed businesses are immutable
(`invalid_state`). Public visibility (active-only) is M3D behavior.

### Dietary tags (D6)

Append-only registry seeded `halal`, `vegetarian`, `vegan` — allergens,
nutrition, and tenant-created tags are out of scope. Tags are stored
canonical lowercase (DB CHECK); writes reject unknown values; reads fail
closed on unexpected stored values.

### Category deletion (D7)

A category is deletable only when empty; a non-empty category returns 409
`conflict`. Items are never cascade-deleted through category deletion.

### Business lifecycle and currency (D8, source-verified)

Item prices are integer minor units with no per-item currency; the
authoritative currency is `businesses.currency` (ISO 4217 shape, set at
creation, no API edit path exists). Any future currency-edit API must
decide price reconciliation first — out of M3 scope.

## Alternatives considered

Recorded in the approved architecture proposal and addendum: generic
commerce engine now (rejected — premature abstraction, ADR-012); native
enums (rejected — ADR-011 precedent); versioned catalog publication in M3
(rejected — draft/publish belongs to storefront composition, M4); S3 or a
storage emulator now (rejected — blueprint §7.5 local-first adapter);
storage-key-based delivery URLs (rejected — keys are internal);
per-row position PATCH (rejected — corruption-prone vs full-set reorder);
`featured_limit_reached` code (rejected — `conflict` + `details.limit`
carries the same information).

## Consequences

Catalog and media land as six reviewable slices over the M2 authorization,
audit, and contract foundations with no backend rework between slices;
M4's storefront consumes the public menu and media source metadata without
media-schema migration. Storage growth from retained media is bounded by
upload caps and managed by explicit deletion plus the sweep.

## Security and operations impact

Tenant isolation extends to every catalog/media table (tenant-leading
constraints, composite FKs, scoped repositories, permanent matrix tests).
Upload hardening (authorization before parsing, byte/pixel caps,
re-encoding, key privacy) is fixed by ruling before any media code exists.
The persistent development database is never migrated implicitly; media
persistence and backup obligations are recorded in the deployment runbook
in M3C.

## Reconsideration triggers

M4 draft/composition (versioned editing); first cross-item modifier reuse
need (shared library design); S3/CDN adoption (delivery URL strategy);
per-tenant featured-count configurability; a real ISO 4217 currency list
requirement; catalog scale exceeding the approved bounds.

## Delivery record

### M3A — Catalog core backend: delivered (local), 2026-07-19

One migration (`0c31eebbac66`) creates `menu_categories`, `menu_items`,
and `menu_item_dietary_tags`: tenant-owned (`business_id` FK RESTRICT on
every table), composite tenant-safe FKs (items → categories RESTRICT;
tags → items CASCADE) over `UNIQUE (business_id, id)` targets,
DEFERRABLE INITIALLY DEFERRED dense-position uniques, case-insensitive
name uniqueness via `lower(name)` expression indexes, the
canonical-lowercase dietary CHECK, price-range CHECKs (0–10,000,000, F1
ruling) and the non-negative position CHECK,
and the partial featured index serving the R1 count guard. Stepwise
upgrade/downgrade proven; ORM metadata and migrated schema diff empty.

The catalog service owns every transaction behind one write preamble —
membership capability, then the businesses-owned
`lock_business_status` `FOR UPDATE` (Business is the first lock), then
the lifecycle gate — so count limits are race-safe and closed businesses
are immutable while remaining readable. Positions stay dense 0..n-1:
creation appends, deletion closes the gap, item movement appends at the
destination and renormalizes the source, reorders are full-set,
set-validating (inexact sets → 409), atomic, and naturally idempotent.
Behavioral clarifications delivered as tested rules: sold-out
(`is_available`) and hidden are independent states; hiding clears
nothing (featured stays, inert publicly); no-op updates and same-value
availability commands change nothing and record no audit event;
uniqueness/limit/reorder violations and the DEFERRED-constraint commit
window all convert to safe 409 `conflict` responses.

Eleven admin routes under `/businesses/{business_id}/catalog` with the
approved permanent operation ids (`catalog_admin_menu_get`,
`catalog_category_create/update/delete`, `catalog_categories_reorder`,
`catalog_item_create/get/update/delete`, `catalog_items_reorder`,
`catalog_item_availability_set`); the aggregate menu read returns
categories + items + dietary tags only (no modifier or media data).
Capabilities landed per D4; audit landed as the nine registered actions
with typed bounded details and read-time projections
(`changed_fields` is a closed-set comma-joined string; price old/new
recorded exactly on price change; audit rows commit and roll back with
their mutation — proven through the deferred-constraint failure path).
OpenAPI/client regenerated; `client.catalog` facade group added.
Delivered with unit, migration/constraint, API, policy-boundary, and
isolation-matrix coverage (cross-tenant 404s, staff/manager/platform
role matrix, CSRF, no mutation or audit side effects on rejection), the
full local gate, the existing Playwright suite, and clean-copy
verification.

### M3B — Modifiers backend: delivered, 2026-07-20

Approved architecture (proposal + addendum rulings), recorded before
implementation:

- Option `price_delta_minor` range **0 ≤ delta ≤ 10,000,000** sharing
  `MAX_PRICE_MINOR` and the `_price_int` audit extractor; named CHECKs
  `ck_modifier_options_price_delta_nonnegative` / `_maximum`; no currency
  column; no new error code.
- Selection bounds are **database-enforced numeric domain**, in three
  separately named CHECKs: `ck_modifier_groups_min_select_range`
  (0–30), `ck_modifier_groups_max_select_range` (NULL or 1–30), and
  `ck_modifier_groups_min_le_max`. The 30 mirrors the options-per-group
  policy cap. Active-option **satisfiability stays computed and
  report-only** (`active_option_count`, `is_satisfiable` on every group
  representation; never stored; never a write gate) — a legal but
  unsatisfiable configuration is always storable.
- Admin read contract: one dedicated bounded per-item tree,
  `catalog_item_modifier_groups_get`; `AdminMenu`, `ItemSummary`,
  `catalog_item_get`, and every existing operation stay byte-stable
  (the audit-action filter enum growth is the only additive change).
- Option availability is `is_available` inside the general option PATCH
  (no separate command, no separate audit action); staff hold **no**
  modifier authority of any kind; owner/manager use
  `business.catalog.write`; reads use `business.view`; no new
  capability.
- Eight audit actions with explicit **`max_select_mode`**
  (`finite`/`unlimited`) fields on group create/update — mode fields
  always present when the maximum changes, finite values only when the
  respective side is finite; option updates record
  `availability_old`/`availability_new` (`available`/`unavailable`)
  exactly when availability changes; projections use a closed-set
  `_choice` extractor (no booleans in the audit value union). Cascade
  deletions never fan out child events: item deletion emits only
  `catalog.item_deleted`; group deletion emits one
  `modifier_group_deleted` carrying its `option_count`.
- **No-op full-set reorders return current state with no position
  writes and no audit event** — and by explicit ruling R-1 the merged
  M3A `reorder_categories`/`reorder_items` are aligned to the same rule
  in this sub-milestone (a deliberate, tested change to M3A behavior).
- Shared internal module `catalog/service_support.py` carries the
  authorization preamble, flush/commit conversion, and the single
  known-conflict constraint map, **moved** from `service.py` so M3A and
  M3B cannot drift; `modifier_service.py` holds the modifier workflows
  inside the catalog domain.
- Value-column defaults are application-side only (server defaults only
  on timestamps): a direct SQL insert omitting a required value fails
  explicitly rather than acquiring a divergent default.

**Delivered (local) 2026-07-20, in review.** One migration
(`f8ad809962f8`) creates `modifier_groups` and `modifier_options`
exactly as ruled: composite tenant-safe FKs (groups CASCADE with their
item; options CASCADE with their group over the new
`uq_modifier_groups_business_id_id` target; deliberately no such target
on options), the three named selection-domain CHECKs, the price-delta
range CHECKs, DEFERRABLE dense-position uniques, case-insensitive name
expression indexes, and application-side value defaults (a direct SQL
insert omitting a value column fails explicitly). Nine operations landed
(`catalog_item_modifier_groups_get` + eight mutations; pinned
operation-id total 49); option mutations return the recomputed parent
`ModifierGroupView`; no existing M3A operation or schema changed. The
modifier workflows live in `catalog/modifier_service.py` over the shared
`service_support` preamble; R-1 landed (M3A category/item reorders now
no-op-suppress identical permutations, tests updated). Eight audit
actions recorded with the explicit max-mode convention; the D6
field-presence rules bind at **both layers** — the modifier detail
schemas omit inapplicable optional fields from the stored payload via
their own serializer (`ModifierAuditDetails`; the shared M2A recorder
and every earlier schema, including M3A's price details, are untouched)
and the typed read-time projection omits them independently; tests
assert stored absence and projected absence separately. Delivered with unit,
migration/constraint (five named selection-CHECK rejections, both
cross-tenant FK rejections, cascade chains), API, satisfiability-
transition, count-limit, authorization/isolation, audit-atomicity, and
two-session concurrency coverage, plus the full local gate and
exact-head clean-copy verification.

### M3C — Media backend: delivered, 2026-07-21

Approved architecture (discovery proposal → addendum → final binding
corrections), recorded before implementation:

- **Domain and model.** `app/domains/media` owns media; one general
  `media_assets` model (kind CHECK-limited to `image`; extending to video
  later is an additive migration) plus relational `media_asset_variants`
  rows. Consumers store media identifiers through composite tenant-safe
  FKs over `UNIQUE (business_id, id)`; M3C attaches **menu-item images
  only** (`menu_items.image_media_id` RESTRICT + contextual
  `image_alt_text`, alt requires image, ≤ 300). Logos, category images,
  promotional media, hero composition, and video are later milestones;
  nothing here forecloses them, and hero overlay content (headings,
  buttons, CTAs) remains separately rendered storefront metadata — never
  pixels in a video file.
- **Storage protocol (supersedes the blueprint §7.5 illustrative
  snippet; blueprint amended same date).** Runtime `MediaStorage`:
  `put` / `open` / `delete` (idempotent) / `stat`; maintenance extension
  `MaintenanceStorage` adds `iter_objects` (operator tooling only).
  `stat`/`iter_objects` return internal key, byte size, and
  last-modified. **No `public_url`**: M3C exposes no storage-provider
  URL; application URLs are opaque asset ids + logical variant names;
  a signed-URL/CDN resolver is a later delivery-layer concern. Keys are
  derived (`{business_id}/{asset_id}/{variant}.webp`), tenant-prefixed,
  never stored, and never appear in responses, audit, logs, or URLs.
- **Persistence.** `MEDIA_STORAGE_ROOT` (dev default `backend/var/media`,
  gitignored, development only). Production requires an explicit durable
  absolute root outside any static-served directory, validated by a
  startup write/stat/delete probe, mounted persistently when the M8
  production compose is authored (runbook obligation recorded now);
  `/health/ready` gains a collision-safe `media_storage` probe.
  PostgreSQL and the media root form **one logical backup set**
  (docs/07: quiesce → verify inventory/checksums → dump → archive →
  shared-set manifest; restore only as a pair; re-verify after restore).
- **Upload pipeline.** Authenticate → CSRF → `business.media.write` →
  non-locking lifecycle gate (closed → 409 **before any body parse**) →
  Content-Length required (over-cap 413 `payload_too_large`, the one new
  error code) → async stream into a bounded spooled temp (request cap =
  file cap + 64 KiB overhead; file cap default 10 MiB, deployment max
  20 MiB — the only deployment-tunable media limit) → AnyIO worker
  thread (sessions never cross threads; the worker opens its own session
  and repeats capability + lifecycle under the Business `FOR UPDATE`
  lock): strict one-`file`-part multipart parse → magic bytes + decoded
  `Image.format` agreement (static JPEG/PNG/WebP only; GIF, SVG, HEIC,
  AVIF, TIFF, animated WebP, APNG rejected) → 8000 px/side + 25 MP
  before full decode, bomb guard promoted to rejection, `verify()` then
  reopen, truncation rejected → EXIF orientation → mode normalization →
  ≤ 2560 canonical + strictly-smaller 320/640/1280 variants (LANCZOS,
  deterministic rounding, no upscaling) → WebP quality 82 method 4 lossy,
  alpha preserved, all metadata dropped; the original upload is not
  retained. **Worker isolation (correction 2):** multipart extraction,
  scratch-file creation, Pillow work, object storage, and the final
  transaction all run in the worker thread; only the bounded async body
  streaming stays on the event loop; the processing scratch directory is
  supplied through composition (`app.state.media_scratch_dir`), not read
  off the storage object, so `MediaStorage` stays exactly the four-method
  protocol. **Commit/compensation boundary (correction 1):** every
  fallible database operation _and_ the response projection run before
  commit, and the commit is the final database step. A failure that
  definitely precedes commit deletes every written object; once the
  commit has been attempted the outcome is treated as ambiguous — objects
  are deleted only when a separate transaction positively proves the
  asset row is absent, otherwise retained for reconciliation (a committed
  row never loses its objects). A partial encode/variant/put failure
  cleans its own scratch and compensates written objects; compensation
  failure leaves a sweep-visible orphan and never masks the original
  error. Deletion after commit attempts every object independently and a
  storage failure never turns an already-committed row delete into a 500.
  The local adapter writes atomically (temp + `os.replace`) and fsyncs the
  target directory on POSIX so the rename is durable before the row
  commits; admin preview streams through a generator that always closes
  the handle (completion, error, disconnect).
- **Limits.** Product-policy constants: 500 assets/business (pending +
  active), 1 GiB stored bytes/business (canonical + variants), 32 MiB
  combined encoded output/asset (a processing 422, not a quota 409).
  Exact usage is computed under the lock from authoritative rows via
  separate non-multiplying aggregates (assets sum + variants sum) —
  deliberately **no stored `total_bytes`** denormalization. Count/byte
  quota rejections are 409 `conflict` with `details.limit`; every
  rejection leaves no row, object, or audit event.
- **Lifecycle (DB clock).** Uploads start `pending`
  (`pending_expires_at = now() + 48 h` in SQL; active assets have NULL).
  Attachable iff `pending_expires_at > now()`; at equality it is
  expired: still visible to authorized admin reads/preview, still
  explicitly deletable, still quota-counted, never attachable (409
  `invalid_state`, decided under the Business lock), never publicly
  deliverable. First valid attachment promotes to `active` (one-way);
  ever-attached assets are never auto-deleted; referenced assets cannot
  be deleted (menu_items RESTRICT FK mapped to 409).
- **Authorization.** New capability `business.media.write`
  (owner/manager). Staff read/list/preview via `business.view`, no
  mutation. Platform admins 404; anonymous 401; cross-tenant 404;
  provisioning/active/suspended writable; closed readable, immutable.
  Attach/replace/clear/alt is one catalog command
  (`catalog_item_image_set`, `business.catalog.write`) with exact no-op
  suppression (no write, no `updated_at`, no promotion, no audit).
- **API (49 → 55).** `media_asset_upload` (multipart documented via
  `openapi_extra`; the endpoint declares no body params),
  `media_assets_list` (limit/offset ≤ 100), `media_asset_get`,
  `media_asset_file_get` (authorized admin preview incl. pending;
  fixed `image/webp`, nosniff, inline server-composed filename),
  `media_asset_delete`, `catalog_item_image_set`.
- **Audit.** Four actions: `media.asset_uploaded`, `media.asset_deleted`,
  `catalog.item_image_changed` (`change` ∈ attached/replaced/cleared/
  alt_updated with exact old/new-id presence rules; alt text itself never
  recorded), and `media.asset_expired` — NULL-actor **system**
  attribution (supported by the M2A schema by design), recorded
  atomically with sweep row deletion. Optional inapplicable fields are
  omitted from stored and projected payloads (the M3B D6 rule). Objects
  deleted without a database row (orphans, stale temps) are reported by
  the CLI only — deliberately uneventful.
- **Sweep** (`scripts/sweep_media.py`; operator CLI, dry-run default,
  `--apply`, bounded keyset batches, `--batch-size` validated 1..100000;
  scheduling M8). Lifecycle-independent system maintenance: expired
  pending is cleaned for provisioning, active, suspended, **and closed**
  businesses — the Business `FOR UPDATE` lock is acquired and candidates
  re-read (status, expiry, existence). **Expiry selection uses the
  PostgreSQL clock (`func.now()`), never the application clock
  (correction 4);** the missing-object walk is likewise batched, not an
  unbounded load. Rows + `media.asset_expired` events delete atomically;
  objects only after commit. Object-level orphan identity: an object is
  expected only when it is the canonical of an existing asset row or the
  exact logical variant of an existing variant row; validly-shaped
  unreferenced objects older than 24 h (storage last-modified, never
  filename assumptions) are deletable; malformed or unknown key shapes
  are report-only; rows without required objects are report-only, never
  auto-deleted. Dry run counts eligible stale temps without deleting.
  Output reports business/asset ids, variants, and counts — never keys or
  paths; one failed object deletion never stops the batch report. Exit
  codes: `0` clean, `1` a failure (verify inconsistency or an `--apply`
  object-delete failure), `2` invalid arguments, `3` work remains.
- **Backup verification (correction 3; round-2 hardening).** `--verify`
  (never mutates) enumerates every expected canonical and variant object
  in bounded batches, compares stored byte size and a recomputed SHA-256
  against the database rows, and flags **every** storage-only object
  regardless of age (a quiesced backup set must contain none);
  malformed/unknown key shapes get an explicit non-success disposition.
  Storage I/O is failure-safe: a missing object at either `stat` or
  `open` becomes a `missing` finding, and any other stat/open/read
  failure becomes an `unreadable` finding — no exception ever escapes.
  Findings carry business/asset/variant and a kind
  (`missing`/`size_mismatch`/`checksum_mismatch`/`orphan`/`unreadable`)
  only — never a key, path, checksum value, or exception message. The
  runbook preflight requires a clean re-verification after any repair
  before dump/archive. Malformed/unknown storage entries also count as
  unresolved work in the sweep exit code (`3`).
- **Dependencies (D11).** `pillow==12.3.0`, `python-multipart==0.0.32`
  (exact-pinned; backend only).

### M3D — Public menu API and public media delivery: in progress (2026-07-21)

Approved architecture (discovery proposal → architecture-gate rulings
R1–R15 → addendum → authorization refinements), recorded before
implementation:

- **Surface.** Two schema-visible operations (55 → 57):
  `public_menu_get` (`GET /public/menu`) and `public_media_file_get`
  (`GET /public/media/{asset_id}/{variant}`), each with a **schema-hidden
  companion `HEAD` route** (`include_in_schema=False`) sharing its
  handler, dependencies, and behavior. FastAPI does **not** auto-register
  HEAD (`APIRoute` sets `methods = {"GET"}`; Starlette's HEAD addition
  applies only to plain `Route`), so HEAD is added deliberately and, being
  schema-hidden, adds no operation id and no OpenAPI operation.
  `/public/site` deliberately gains no HEAD in M3D.
- **Resolution and disclosure.** Both families resolve the Business from
  the request Host through the existing `resolve_public_business`
  (ADR-013) — no path, query, header, or cookie tenant selector, no
  authentication, session, or CSRF. Every ineligible input renders as the
  identical neutral 404 (`not_found` / `Not found.`).
- **Host guard.** The exact-path `/api/v1/public/site` exemption is
  replaced by a **method-scoped prefix exemption**: `GET` and `HEAD` under
  `/api/v1/public/` only. Other methods stay guarded and receive the
  ADR-008 400 from an unrecognized Host. A permanent invariant test walks
  each route's `dependant` tree (schema-hidden routes included) and fails
  if any public GET/HEAD route omits `resolve_public_business`. See the
  ADR-013 amendment of the same date.
- **Public catalog projection.** Separate `Public*` schemas — never
  administrative schema reuse, so `position`, `is_hidden`, `is_featured`,
  `image_media_id`, `active_option_count`, `is_satisfiable`, and
  timestamps never leave the admin surface. `PublicMenu` carries a nested
  `business: PublicSiteSummary` (the sole currency source), `categories`,
  and `featured_item_ids` — ids only, referring to the one canonical item
  representation in the category tree (no duplicated item objects).
  Visibility: invisible categories and hidden items are excluded;
  categories with no publicly eligible item are suppressed; unavailable
  modifier options are omitted; an unsatisfiable **optional** group is
  omitted harmlessly; an unsatisfiable **required** group is omitted and
  makes the item `is_orderable = false`; a sold-out item stays listed with
  `is_available = false` and `is_orderable = false`. Satisfiability reuses
  `catalog.policies.is_group_satisfiable` exactly — one formula, two
  projections. M6 remains the authority for order-time revalidation.
- **Public media eligibility (seven conditions, all current).** Active
  host-resolved business; same-business asset; asset `status='active'`;
  the requested canonical or derived representation present in the
  authoritative database inventory; **at least one current same-business
  menu item references the asset**; that item is not hidden; its category
  is visible. Sold-out and non-orderable items still authorize their
  images. Detached assets, hidden-only attachments, and hidden-category-
  only attachments return the same neutral 404 as unknown or foreign ones.
  The attachment predicate is a bounded tenant-scoped `EXISTS`; attachment
  information never appears in a response. `status='active'` alone is
  deliberately **not** sufficient: promotion is one-way, so an asset
  detached after promotion would otherwise stay retrievable forever by
  anyone holding its URL.
- **Composition and dependency direction.** The eligibility predicate is
  catalog's (`catalog.public_service`) and the asset/variant inventory and
  storage access are media's (`media.public_service`); they are joined by
  an application-layer router (`app/api/public_media_router.py`) following
  the M2D audit-list precedent. **Media never imports catalog**, so the
  recorded catalog → media direction (M3C final correction M) is
  preserved.
- **Caching.** The public menu is `no-store`. A successful media `200` and
  a validator-matching `304` are
  `Cache-Control: public, max-age=3600, immutable`; **every** media error
  — 404, 405, 5xx, storage failure, resolution failure — is `no-store`.
  One hour, not a day: the bytes at a URL are immutable, but that URL's
  _authorization_ can change through detachment, hiding, deletion, or
  business suspension, so the stale-publicity window is bounded (recorded
  in docs/04 and docs/07). `NoStoreApiMiddleware` remains the single
  authority and decides from (path prefix, method, status) — deliberately
  **not** a general "trust any downstream `Cache-Control`" change, which
  could let an authenticated route escape the global policy.
- **Validators.** Strong ETag = the full quoted SHA-256 hex digest of a
  versioned tuple (`rem1|asset_id|variant|checksum`) over the checksum of
  the **exact delivered representation** (asset row for `canonical`,
  variant row for `w320`/`w640`/`w1280`). The stored checksum itself is
  never returned; the ETag is opaque. `If-None-Match` supports `*`,
  comma-separated lists, and weak comparison for GET/HEAD; a nonmatching
  or unusable header falls through to 200. A matching validator still
  performs full eligibility, inventory lookup, `storage.stat`, and the
  byte-size check — it must never 304 a missing or size-mismatched object
  — and never calls `storage.open`. A 304 carries the ETag and the
  approved `Cache-Control`, with no body and no `Content-Length`.
- **Corruption detection, exactly bounded.** Synchronous delivery detects
  a **missing object** and a **byte-size disagreement** between storage
  and the database. It does **not** hash the object per request, so
  same-size corruption is detected by `sweep_media.py --verify` and the
  docs/07 backup gate — never claimed as a delivery-time guarantee.
- **Stat/open race.** A nonmatching GET establishes eligibility, stats,
  verifies the size, and **opens the object before any response header is
  committed**; an object that disappears or fails to open between stat and
  open yields the neutral 404 with `no-store` and one structured warning,
  never a truncated 200. Once streaming has begun the M3C close
  guarantees apply, and ordinary completion or a client disconnect emits
  no corruption warning.
- **Range, HEAD, and conditional headers.** `Range` is ignored and the
  complete representation is returned; `Accept-Ranges` is never
  advertised. `Last-Modified`/`If-Modified-Since` are deliberately absent
  — filesystem mtime is rewritten by the docs/07 media-root restore, so it
  is not a sound validator for this system. HEAD returns the
  representation headers with no body and never opens the object.
- **Queries and concurrency.** Existing READ COMMITTED; no
  transaction-isolation infrastructure. Child rows load only for currently
  relevant public parents (tags/groups for eligible item ids, options for
  loaded group ids, assets/variants for referenced image ids), so hidden
  items' modifier and media data are never read. Defensive assembly —
  children attach only to parents present in the same projection —
  guarantees no cross-tenant row, no dangling nested reference, no parent
  lookup exception, and no image block for an asset not confirmed active
  during assembly.
- **Audit, logging, and abuse.** Public GET/HEAD/304 create **no** audit
  events (the ADR-013 amplification/enumeration rationale). A warning is
  emitted only after full database eligibility is established and the
  physical object is then missing, size-mismatched, or unopenable, and
  carries only a reason code plus business id, asset id, and logical
  variant — never a Host, key, path, checksum, filename, or exception
  text. Expected public misses are never logged, so the surface is not an
  unauthenticated log-amplification vector. No application rate limiter:
  per-IP limiting requires a trusted deployment boundary and remains the
  mandatory M8 reverse-proxy item (docs/04).
- **No migration, no dependency, no configuration.** Every field the
  projection and delivery need already exists; the Alembic head stays
  `59b463781dcc`.

**Delivered (local) 2026-07-21, in review.** Two schema-visible
operations landed exactly as ruled (`public_menu_get`,
`public_media_file_get`; pinned total 57) with schema-hidden `HEAD`
companions on the same handlers, and no migration, dependency, or
configuration change — the Alembic head is unchanged. The public menu
lives in `catalog/router_public.py` over `catalog/public_service.py` and
`catalog/public_schemas.py`; public delivery composes
`catalog.public_service.media_is_publicly_visible` with
`media.public_service` in `app/api/public_media_router.py`, so media
still imports no catalog. `NoStoreApiMiddleware` gained the narrow
public-media exception decided from path, method, and status.

Two source realities were discovered during implementation and are
recorded because they change how the rulings are met:

1. **FastAPI does not auto-register `HEAD`.** `APIRoute` sets
   `methods = {"GET"}` (Starlette's HEAD addition applies only to plain
   `Route`), so `HEAD` reached no route before M3D and had to be added
   deliberately. Declaring it as a method would emit a second OpenAPI
   operation reusing the GET's id, so the companions are
   `include_in_schema=False` and the operation count is unaffected.
2. **`assert_contract_operation_ids` was inspecting nothing.** This
   FastAPI version does not flatten `include_router` into `APIRoute`
   objects on the application, so the old `app.routes` walk found zero
   routes and the ADR-009 boot-time guarantee was vacuous for the
   composed app (the OpenAPI export test still enforced the same contract
   from the other side, so no operation id was actually wrong). Route
   enumeration now follows the included-router structure, and a
   regression test pins the walked operation-id set to the documented
   OpenAPI set.

One related pre-existing gap was closed: an unhandled-exception 500
carried no `Cache-Control` at all, because Starlette renders the
`Exception` handler in its outermost `ServerErrorMiddleware`, outside the
middleware that stamps the policy. The handler now sets `no-store`
itself, which the binding M3D requirement (every media error including
5xx is uncacheable) needs and which every other route inherits.

Coverage landed for the full approved matrix: resolution and neutral-404
uniformity with a menu seeded behind each failing host as a negative
control, per-host isolation, visibility and suppression rules, modifier
projection and orderability, deterministic ordering, images and featured
ids, the seven-condition media eligibility (including the detach-stops-
delivery case that motivates it), conditional requests with `*`,
comma-separated and weak validators, the 304-never-for-a-broken-object
rule, the stat/open race, HEAD and Range policy, the cache matrix
including error statuses, warning discipline for expected misses,
bounded-query stability, concurrent-edit structural validity, response
and log hygiene, and the absence of audit events for public reads.

### M3E–M3F

Not started.
