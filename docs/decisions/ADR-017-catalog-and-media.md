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

| Sub | Scope | Depends on |
| --- | ----- | ---------- |
| M3A | Catalog core backend: categories, items, dietary tags, pricing, availability/hidden/featured, reorder, capabilities, admin APIs, audit, isolation matrix | — |
| M3B | Modifiers backend: groups/options, selection rules, satisfiability | M3A |
| M3C | Media backend: media domain, local storage adapter, upload pipeline, responsive variants, lifecycle, sweep, item image attachment | M3A |
| M3D | Public menu API + public media delivery | M3A–M3C |
| M3E | Menu administration UI (control-center business workspace) | M3A–M3C contracts (+ any M3D behavior it directly consumes) |
| M3F | Playwright menu journey, verification, close-out | all earlier |

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

- **M3A — Catalog core backend:** in progress.
- **M3B–M3F:** not started.
