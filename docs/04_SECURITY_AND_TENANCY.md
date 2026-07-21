# 04 — Security and Tenancy

Summarizes blueprint §§8, 11. The blueprint is authoritative. These contracts
bind every implementation milestone; none is implemented during Milestone 0.

## The multi-tenancy contract

### Tenant resolution

**Implemented in M2C (ADR-013).** A public request is resolved to a Business
from the request **Host only** — the single subdomain label directly under
`PLATFORM_BASE_DOMAIN` is the candidate slug, matched to an **active**
Business by canonical slug. Host normalization is parser-level and
fail-closed; IP literals and the bare apex never resolve; there is **no**
development header/query/cookie override, in any environment (development
uses `{slug}.localhost`). Approved custom-domain exact match is the eventual
first step in the resolution order but remains **deferred** (blueprint §17.2)
until domain-ownership verification and certificate automation exist.

The reserved labels `api`, `admin`, and `www` are platform infrastructure
hosts and are never tenants: one policy source rejects them at Business
creation (422) and treats them as unresolved during public resolution.

Administrative tenant selection comes from an authenticated membership plus a
route tenant identifier. The server validates the membership; it never trusts
a tenant header by itself.

Forwarded headers (`X-Forwarded-*`) are never consulted for resolution
(proxy trust remains an M8 decision). A non-exempt API route whose Host is
not a recognized platform host family is rejected with an ADR-008 400 — Host
validation is routing hardening, not tenant authentication.

### Data rules

Every tenant-owned table contains `business_id` (ADR-012: Business is the
tenant aggregate) — including grandchildren such as modifier options and
order lines. Required mechanics:

- composite unique constraints beginning with `business_id`;
- composite foreign keys where practical, so a child cannot reference another
  tenant's parent;
- indexes beginning with `business_id` for tenant-scoped access paths;
- repository methods that **require** a tenant identifier — a repository
  method reading tenant-owned data without one is invalid by definition;
- tenant-aware cache keys and tenant-prefixed media keys;
- tenant identity in audit and structured logs.

Platform-global tables are explicitly documented as such. A table is never
assumed global merely because `business_id` was inconvenient.

### Failure behavior

- Public unknown, suspended, or unconfigured tenants return the same neutral
  not-found behavior — no existence leaks.
- Administrative authorization failures return 403 after authentication,
  without exposing other-tenant object details.
- Tenant-owned object lookup returns 404 when the object is not in the
  current tenant.

### Defense in depth

PostgreSQL Row-Level Security is deferred (ADR direction, blueprint §8.4):
the first release relies on explicit tenant-scoped repositories, tenant-aware
database relationships, and exhaustive isolation tests. RLS is revisited as a
hardening ADR once access patterns and the platform-support model are stable.

### Tenant-scoped repositories and sanctioned exceptions (M2B, ADR-011)

Every repository read of tenant-owned data takes `business_id`. Any
tenant-unscoped query must name which sanctioned exception it belongs to,
or be rejected in review:

1. **Public slug/host resolution** — establishes tenant identity (M2C).
2. **Single-use token resolution** — invitation/reset tokens (implemented
   in M2D, ADR-014); authorized by possession of a high-entropy secret.
   Tokens are 256-bit, stored only as SHA-256 digests, travel only in
   POST bodies, expire on the database clock, and are single-use under
   row locks; password-setting flows prevalidate the token before any
   Argon2 work, and every invalid-token condition returns one uniform
   neutral 404 per surface.
3. **Self/session scope** — the session-token lookup, and
   `list_for_user(user_id=actor.id)` which spans the caller's own tenants
   (bound to the authenticated actor's own id, never a supplied id).
4. **Platform-capability-gated queries** — cross-tenant reads (business
   list/get, entitlement assignment, reset issuance, the platform audit
   stream) reachable only through services that first pass the named
   platform capability. `platform.users.recover` is documented
   account-takeover-equivalent authority: audited on every issuance, no
   public path (ADR-014).
5. **Operator maintenance queries (M3C, ADR-017)** — the media sweep CLI
   selects expired-pending candidates and inventory rows across tenants.
   It has no API surface, runs only as an operator command on the host,
   re-validates every candidate per business under the Business row lock
   before acting, and audits deletions with system attribution.

M2B uses exceptions 3 and 4; M2D adds exception 2 and extends 4; M3C
adds exception 5.
`businesses` is the tenant root; a lookup by its own primary key is a
"which tenant" query, not a tenant-owned-data leak. Business-scoped audit
reads apply both tenant predicates explicitly (`business_id = ?` AND
`business_id IS NOT NULL`) so platform-level events are structurally
excluded, and audit `details` pass through typed read-time projections —
stored JSON is never returned verbatim (ADR-014).

### Permanent isolation test matrix

For every tenant-owned resource, tests must prove:

- tenant A can list and read its own records;
- tenant A cannot list, read, update, delete, reorder, publish, or attach
  media to tenant B records;
- guessed IDs do not disclose existence;
- cross-tenant parent/child relationships are rejected by the database;
- platform actions require a platform capability;
- suspended tenants disappear publicly while their data remains intact;
- cache and generated storefront output do not cross tenants.

## Security baseline

### Sessions and authentication (implemented in M2A — ADR-010)

- Opaque, database-backed sessions in `HttpOnly`, `SameSite=Lax` cookies
  (`Secure` + `__Host-` prefix in production); only the SHA-256 digest of
  the token is stored. The cookie is persistent (`Max-Age` = absolute
  lifetime); server-side checks are always authoritative.
- Absolute (30 d) and idle (24 h) expiry; revocable; every login opens a
  fresh session; `revoke_all_sessions` backs privilege changes (wired to
  password reset/deactivation in M2D). Authorization state is read fresh
  per request — sessions cache nothing.
- No authentication tokens in localStorage, ever.
- **Fail-closed CSRF, two independent layers** (ADR-010): a
  browser-context check (`Sec-Fetch-Site` same-origin, else exact `Origin`
  allowlist, else `Referer` origin, else reject) on every browser-facing
  unsafe request, plus a per-session synchronizer token in `X-CSRF-Token`
  on cookie-authenticated unsafe requests.
- Login failures are uniform `401 invalid_credentials` — unknown email,
  wrong password, inactive account, and throttled attempts are
  indistinguishable in body and timing (dummy Argon2 verification).
  Per-account exponential backoff (5 failures → 1 s doubling to a 60 s
  cap) replaces lockout; attempts inside the window neither count nor
  extend it. Per-IP limiting belongs to the reverse proxy and is a
  **mandatory M8 item before production** — this includes the M3D public
  surface, which deliberately ships **no** application-level rate limiter
  because no trusted deployment boundary exists yet (forwarded headers are
  untrusted, so an application limiter would key on a spoofable source).
- Every `/api/v1` response is `Cache-Control: no-store`, with exactly one
  approved exception (M3D, ADR-017): a **successful** public media
  delivery (`GET`/`HEAD` under `/api/v1/public/media/`, status 200 or 304) is `public, max-age=3600, immutable`. Every media error — 404,
  405, 5xx, storage failure, business-resolution failure — is `no-store`,
  as is the public menu. The policy is decided by `NoStoreApiMiddleware`
  from path, method, and status; it deliberately does **not** respect a
  route-provided `Cache-Control`, so no authenticated route can grant
  itself caching. The unhandled-exception 500 sets the header itself,
  because Starlette renders it outside the middleware stack.
- **Stale-publicity window (one hour).** The bytes at a media URL are
  immutable, but that URL's _authorization_ is not: an image can be
  detached from its item, hidden, deleted, or taken offline with the whole
  Business through suspension. `max-age=3600` is the bound on how long a
  browser or shared cache may keep serving something that is no longer
  public. Anything requiring immediate public removal must also account
  for caches already holding the representation.

### Public surface (implemented in M3D — ADR-017)

The public menu and public media delivery are unauthenticated, host-
resolved reads with no session and no CSRF. Beyond the ADR-013 resolution
rules they add:

- **Method-scoped host-guard exemption.** `GET`/`HEAD` under
  `/api/v1/public/` bypass the known-Host guard so the resolver can own
  its own neutral 404; unsafe methods stay guarded (ADR-013 amendment). A
  permanent test proves every public read route carries
  `resolve_public_business` in its dependency graph.
- **Public media authorization.** `status = 'active'` is necessary but
  **not sufficient**: promotion is one-way, so delivery additionally
  requires at least one non-hidden menu item in a visible category to
  reference the asset right now. A detached asset, or one attached only
  through hidden content, returns the same neutral 404 as an unknown or
  foreign one — otherwise a retained URL would stay retrievable forever.
  Sold-out and non-orderable items still authorize their image.
- **No public-read audit.** `GET`, `HEAD`, and `304` write no audit
  events (the ADR-013 amplification and enumeration rationale). Storage
  anomalies are _logged_ — and only after the database has established
  eligibility, so expected public misses cannot be used to amplify logs.
  Warnings carry a reason code plus business, asset, and variant ids;
  never a Host, storage key, path, filename, checksum, or exception text.
- **Bounded, opaque, non-disclosing responses.** Public schemas are
  separate from administrative ones; identifiers are opaque asset ids and
  logical variant names; `Range` is ignored and `Accept-Ranges` is never
  advertised; delivery detects a missing object and a byte-size
  disagreement, and never hashes per request (same-size corruption is the
  sweep's and the backup preflight's job).

### Proxy trust (fixed now, revisited at M8)

The API trusts **no** forwarded headers: `X-Forwarded-For/-Host/-Proto`
are ignored and uvicorn runs without `--proxy-headers`. Honoring them is
an explicit Milestone 8 decision coupled to the Nginx topology — do not
enable it earlier.

### Password and account policy

Argon2id via a maintained library · rate-limited login and reset · no
account-existence disclosure during reset · single-use, short-lived, hashed
reset tokens · reauthentication for destructive platform operations · MFA for
platform administrators before commercial launch · seed credentials only in
development/test · production startup fails on detected example secrets.

### Application controls

Centralized authorization policies · strict input schemas rejecting extra
fields on commands · upload allowlist and image re-encoding · output encoding
and no arbitrary HTML · Content Security Policy on both frontends ·
trusted-host validation and host normalization · request size limits at proxy
and application · per-route throttling for login, checkout, tracking, and
uploads · secrets via environment/secret files, never committed · dependency
and container scanning in CI · structured security audit events ·
privacy-minimized logs.

### Destructive action policy

Suspend and close are normal operations. Permanent deletion is delayed,
requires typed confirmation and recent authentication, produces an audit
event, and follows a documented retention policy. Cross-tenant support
impersonation is deferred until an explicit, auditable support-access design
exists.

## Security expectations during Milestone 0

Even with no runtime code, the following are enforced now:

- no secrets or real credentials anywhere in the repository;
- `.env` is gitignored; `.env.example` carries safe placeholders only;
- CI never receives deployment credentials;
- every future milestone inherits this document as acceptance criteria, not
  as a cleanup list.
