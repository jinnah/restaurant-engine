# 04 — Security and Tenancy

Summarizes blueprint §§8, 11. The blueprint is authoritative. These contracts
bind every implementation milestone; none is implemented during Milestone 0.

## The multi-tenancy contract

### Tenant resolution

Public resolution order:

1. approved custom-domain exact match, when that capability is enabled;
2. canonical subdomain slug;
3. explicit development-only header or query parameter, never in production.

Administrative tenant selection comes from an authenticated membership plus a
route tenant identifier. The server validates the membership; it never trusts
a tenant header by itself.

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
2. **Single-use token resolution** — invitation/reset tokens (M2D);
   authorized by possession of a high-entropy secret.
3. **Self/session scope** — the session-token lookup, and
   `list_for_user(user_id=actor.id)` which spans the caller's own tenants
   (bound to the authenticated actor's own id, never a supplied id).
4. **Platform-capability-gated queries** — cross-tenant reads (business
   list/get) reachable only through services that first pass
   `platform.businesses.manage`.

M2B uses exceptions 3 and 4. `businesses` is the tenant root; a lookup by
its own primary key is a "which tenant" query, not a tenant-owned-data leak.

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
  **mandatory M8 item before production**.
- Every `/api/v1` response is `Cache-Control: no-store` until the M4
  public-caching decision.

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
