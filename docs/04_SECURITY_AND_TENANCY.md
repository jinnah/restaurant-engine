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

Every tenant-owned table contains `restaurant_id` — including grandchildren
such as modifier options and order lines. Required mechanics:

- composite unique constraints beginning with `restaurant_id`;
- composite foreign keys where practical, so a child cannot reference another
  tenant's parent;
- indexes beginning with `restaurant_id` for tenant-scoped access paths;
- repository methods that **require** a tenant identifier — a repository
  method reading tenant-owned data without one is invalid by definition;
- tenant-aware cache keys and tenant-prefixed media keys;
- tenant identity in audit and structured logs.

Platform-global tables are explicitly documented as such. A table is never
assumed global merely because `restaurant_id` was inconvenient.

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

### Sessions and authentication (from Milestone 2)

- Opaque, database-backed sessions in `Secure`, `HttpOnly`, `SameSite=Lax`
  cookies; only a cryptographic hash of the token is stored.
- Absolute and idle expiry; revocable; rotated on login and privilege change.
- No authentication tokens in localStorage, ever.
- CSRF protection (origin check plus token pattern) for unsafe
  cookie-authenticated requests; CORS restricted to exact trusted origins.

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
