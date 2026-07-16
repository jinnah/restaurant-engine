# ADR-010: Session, cookie, CSRF, and login-throttling contract

- **Status:** Accepted
- **Date:** 2026-07-16
- **Deciders:** Product owner, principal architect

## Context

Milestone 2A implements the first authentication surface. The blueprint
locks the direction — opaque database-backed browser sessions, no tokens in
localStorage (§11.1) — but the concrete contract (token storage, cookie
attributes, CSRF mechanics, failure disclosure, throttling) shapes every
later milestone and was fixed in the approved M2 architecture review and
its final addendum.

## Decision

### Sessions

Opaque 256-bit tokens (`secrets.token_urlsafe(32)`); PostgreSQL stores only
the SHA-256 digest (deterministic lookup; a KDF adds nothing against a
256-bit random value). Validity requires all of: not revoked, inside the
absolute bound (30 days), inside the idle window (24 hours, tracked by
`last_used_at`, refreshed at most once per 60 s), and the owning user still
active. Every login creates a fresh session (rotation by construction);
logout revokes; `revoke_all_sessions` exists for privilege changes
(password reset and deactivation wire it in M2D). Authorization state is
read fresh from the database per request — sessions cache nothing, so
privilege changes take effect immediately.

### Cookie

`HttpOnly; SameSite=Lax; Path=/`, **persistent** with `Max-Age` equal to
the absolute session lifetime; the server-side checks are always
authoritative. Production uses the `__Host-` prefix plus `Secure`
(`__Host-session`); development uses `session` over plain HTTP. Deletion
repeats the exact name/Path/Secure attributes with `Max-Age=0`, and is
also sent when a presented cookie turns out invalid. Settings fail fast in
production when trusted origins are missing or non-HTTPS or when
`DATABASE_URL` carries a known placeholder password.

### CSRF — two independent layers, fail closed

1. **Browser-context check** on every browser-facing unsafe request:
   `Sec-Fetch-Site` present → only `same-origin` passes; else `Origin`
   present → exact allowlist match; else `Referer` present → its origin
   must match; else **reject** (403 `csrf_rejected`). Non-browser clients
   must send an allowlisted `Origin` explicitly.
2. **Synchronizer token** on cookie-authenticated unsafe requests: a
   per-session random token, delivered by login/`auth_session`, required in
   `X-CSRF-Token`, compared constant-time.

All `/api/v1` responses are `Cache-Control: no-store` until a deliberate
public-caching decision (M4).

### Passwords

Argon2id with explicit reviewed parameters (`t=3, m=64 MiB, p=1, hash 32,
salt 16` — RFC 9106 low-memory profile; `p=1` suits the 1–2 vCPU VPS).
Acceptance criterion: verification 100–500 ms on the production VPS,
measured by `scripts.benchmark_password_hashing` (re-run in the M8
runbook); out-of-window results trigger a parameter-change ADR, absorbed
via `check_needs_rehash` on login. Password policy (12–128 chars, no
composition rules) applies when setting passwords, never when verifying.

### Login failure and throttling

Every failure path — unknown email, wrong password, inactive account,
throttled — returns an identical `401 invalid_credentials` envelope, sets
no cookie, and performs real Argon2 work (a dummy verification where no
account hash applies) so neither body nor timing discloses account state.
Per-account exponential backoff replaces lockout: after 5 consecutive
failures, a minimum interval (1 s doubling to a 60 s cap) is required
between attempts; inside the window the real hash is never consulted and
the counter is not touched (attempts can neither extend the window nor
lock anyone out). Counter updates are single-statement atomic increments;
the success path resets them. Failed attempts commit their counter and
audit side effects _before_ the 401 is raised — a rejected login is a
domain outcome, not a rolled-back transaction. KDF work always runs
outside open database transactions.

**Scope honesty:** atomic counters prevent lost updates, but this design
is deliberately **not a strict global concurrency rate limit** — N
concurrent requests can each pass the window check before any failure
commits, so short bursts can exceed the nominal one-guess-per-interval
bound. Per-IP/per-connection rate limiting at the reverse proxy is a
**mandatory Milestone 8 item before production**, recorded in the M8
scope.

### Audit

`audit_events` is platform-global (optional tenant scope), append-only by
application discipline (single `record` path; DB-role hardening at M8),
BIGINT identity PK as the cursor for the M2D read API. Events commit in
the same transaction as the change they record. `details` payloads are
built only from per-action typed schemas — a closed, denylist-tested key
set that can never carry secrets.

### Bootstrap

`scripts.create_platform_admin` is the only M2A account-creation path:
password via hidden prompt or `--password-stdin`; a `--password` argument
deliberately does not exist. No seed credentials exist in the repository.

## Alternatives considered

- **JWTs / signed cookies:** locked out by the blueprint — revocation and
  reasoning favor database sessions; no signing secret needs to exist.
- **Hard lockout after N failures:** rejected in review — trivially
  exploitable denial-of-service against known owner accounts, and its
  distinct response disclosed account existence.
- **Session-scoped (non-persistent) cookie:** rejected — for an
  operational tool, forced daily re-login adds friction without adding
  security the server-side idle bound doesn't already provide.
- **Fail-open origin check (reject only when a header is present and
  wrong):** rejected in review — absence of evidence must be rejection.
- **KDF-hashing session tokens:** pointless for 256-bit random values and
  adds per-request cost.
- **Redis-backed rate limiting:** no Redis in the architecture (ADR-001);
  durable per-account state plus M8 proxy limits cover the need.

## Consequences

Every future authenticated endpoint inherits the two CSRF layers and the
no-store policy without per-router work. Auth API tests require
PostgreSQL (sessions are rows); the fast `-m "not integration"` loop
remains for pure logic. The `tests/security/` suite is permanent: session,
CSRF, and disclosure behavior can not regress silently.

## Security and operations impact

No plaintext tokens or passwords at rest, in logs, or in audit details
(tested). Uniform failure responses remove account enumeration through
this surface. The backoff design bounds legitimate-user impact under
attack at 60 s per attempt. Production misconfiguration (non-HTTPS
origins, placeholder DB password) prevents startup entirely.

## Reconsideration triggers

Multi-process deployment (the in-window dummy-verification CPU cost and
burst behavior deserve re-measurement); a real cross-origin API consumer
(revisits the origin allowlist and CORS, ADR-012 at M2C); MFA for
platform admins (pre-launch, blueprint §11.2); evidence the backoff
parameters are wrong on real traffic.
