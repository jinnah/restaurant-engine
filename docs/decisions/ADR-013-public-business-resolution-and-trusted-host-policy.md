# ADR-013: Public Business Resolution and Trusted Host Policy

- **Status:** Accepted
- **Date:** 2026-07-17
- **Deciders:** Product owner, principal architect

## Context

Milestone 2C adds the first public (unauthenticated) surface. A public
request carries no session and no route tenant id, so the platform must
resolve **which Business** it is for from the request itself, and must fail
safely for every request that does not name a live Business. M2B established
the tenant aggregate (`Business`, ADR-012) and its `slug`; this ADR fixes how
a public request is mapped to a Business and how untrusted Hosts are handled.
The Host header is unauthenticated client input: this design validates and
normalizes it, but never treats it as proof of identity.

## Decision

- **Direct-subdomain slug resolution.** The Business is resolved from the
  request **Host only**. The single subdomain label directly under
  `PLATFORM_BASE_DOMAIN` is the candidate slug; a single indexed lookup
  returns the Business with that canonical slug **and** `status = 'active'`.
  No custom-domain resolution, no `business_domains` table, no schema change
  (custom domains remain deferred — blueprint §17.2).
- **No alternative selection mechanism.** No header, query parameter, cookie,
  request body, or forwarded header (`X-Forwarded-*`) can select a Business,
  in any environment. There is no development override. Production and
  development run the identical algorithm; development uses
  `PLATFORM_BASE_DOMAIN=localhost` so `{slug}.localhost` resolves while bare
  `localhost` and IP literals do not.
- **Parser-level Host normalization**, fail-closed (`app/core/hosts.py`):
  handles ports, one trailing root dot, IDNA/punycode, IPv4/bracketed-IPv6
  literals, bare-IPv6 ambiguity, empty/consecutive labels, LDH and length
  limits, and userinfo/control-character/combined values. IP literals and
  bare single-label hosts never resolve a Business; only a direct subdomain
  of the base domain does. Any ambiguity yields no candidate. The Host is
  read from the raw ASGI headers through one shared `sole_host_header`
  helper: zero or multiple Host header values (equal or not) fail closed —
  never first-header selection — and both the guard and the public resolver
  use the same helper, so they cannot disagree.
- **Reserved slugs** (`app/domains/businesses/slugs.py`): `{api, admin, www}`
  are reserved for platform infrastructure hosts. One policy source is
  consumed by both Business creation (rejected at 422, field `slug`, generic
  message) and public resolution (treated as unresolved), so a Business whose
  subdomain could never resolve can never be created.
- **`ResolvedBusiness`** is an explicit, request-scoped DTO (the shape of the
  identity `ActorContext`): `business_id`, `slug`, `name`, `timezone`,
  `currency`. It is **not** a persistent `tenant_id` and **not** an
  ambient/global `TenantContext` (ADR-012 defers both). It carries no
  authorization — a resolved public Business grants no member or platform
  access.
- **Neutral public failure contract.** Unknown, provisioning, suspended,
  closed, reserved, off-apex, deep-subdomain, apex, IP, malformed, and
  missing-Host requests to `GET /api/v1/public/site` all return the **same**
  response: HTTP 404, code `not_found`, the generic message `Not found.`, the
  same `ErrorEnvelope` schema, and `Cache-Control: no-store`, with no
  Business-state-specific fields. The correlation id may differ per request.
  One indexed slug+active lookup, no state-dependent follow-up query — the
  design does not claim constant-time database behavior.
- **Two-scope trusted-host policy** (`app/core/host_guard.py`), not Starlette
  `TrustedHostMiddleware` (which emits a plain-text 400 before routing and
  cannot honor the ADR-008 envelope, the health exemption, or the neutral-404
  contract). A custom ASGI guard rejects **non-exempt** API routes whose Host
  is not a recognized platform host family (base apex, a direct subdomain, or
  in dev/test the loopback/`testserver` hosts) with an ADR-008 `400`. This is
  routing hardening, not authentication. Exactly `/health/live`,
  `/health/ready`, and `GET /api/v1/public/site` are exempt (an exact path
  set, not a prefix — a guard test pins it to the registered probe routes):
  health probes use arbitrary Hosts, and the public resolver owns all of its
  own failures (always a neutral 404, never a 400 from the guard).
  `PLATFORM_BASE_DOMAIN` must be a bare DNS domain — a port fails startup
  validation rather than being silently stripped. Middleware order is
  `NoStore → CorrelationId → RequestLogging → KnownHostGuard`, so the guard's
  400 carries a correlation id, is logged, and stays no-store.
- **`GET /api/v1/public/site`** (`operation_id: public_site_get`,
  unauthenticated, no CSRF) returns the minimal `PublicSiteSummary` —
  `name`, `slug`, `timezone`, `currency`. A 200 already proves the Business
  is active, so no `status`, id, timestamps, or management fields are
  exposed. `client.public.getSite()` takes no tenant argument.
- **Same-origin, no CORS.** The storefront is served same-origin with the
  tenant host and consumes this endpoint without cross-origin requests, so no
  CORS policy is introduced (the already-approved M2 same-origin direction; a
  future cross-origin consumer would revisit it separately).
- **Authenticated behavior is unchanged.** Tenant authorization remains
  session-, CSRF-, membership-, and route-id-based; the M2B suspended-member
  read still returns 200 with visible status, and platform admins receive no
  implicit membership.

## Alternatives considered

- **Custom-domain / `business_domains` table now:** rejected — custom domains
  are deferred (blueprint §17.2); a speculative table violates YAGNI.
- **Starlette `TrustedHostMiddleware`:** rejected — plain-text 400, runs
  before routing (breaks the health exemption), cannot deliver the ADR-008
  envelope or neutral-404 contract.
- **Ambient/contextvar tenant context:** rejected — hidden and hard to test;
  the exact complexity §8.4 flags for RLS. An explicit DTO is testable and
  hard to bypass.
- **A development override header/query:** rejected — a second selection path
  is a standing risk; `{slug}.localhost` and explicit test Host headers cover
  development without one. A future override needs a demonstrated need and a
  security review.
- **Distinct status/branded page for suspended or closed:** rejected — it
  discloses existence; the neutral 404 is uniform.
- **Exposing `business_id`/`status` publicly:** rejected — least disclosure;
  the storefront addresses by host, and 200 already implies active.

## Consequences

Every later public surface (menu, storefront composition) resolves the
Business through the same host-based dependency and inherits the neutral-404
contract; tenant-owned public reads will take `business_id` from
`ResolvedBusiness`. No schema change ships; the Alembic head is unchanged.
The isolation matrix in `tests/security/` gains permanent resolution
controls: it fails if the slug or active-status predicate is dropped, and
proves that only the Host selects a Business.

## Security and operations impact

Host-header spoofing cannot cross Businesses (only the Host is read, and it
is validated against the base-domain family; unknown → neutral 404).
Forwarded headers are never trusted (that remains an M8 reverse-proxy
decision). Public resolution misses are not audited (they would amplify
audit writes and enable enumeration); structured logs record only normalized,
bounded values, never raw malformed Host input or secrets. Public caching is
still deferred (M4); when it lands, any cache key must include the resolved
Business.

## Reconsideration triggers

Custom-domain support (adds ownership verification, certificate issuance,
duplicate protection, and the `business_domains` table); the M8 reverse-proxy
topology (finalizes forwarded-header handling and wildcard TLS); a
cross-origin public consumer (revisits the same-origin/no-CORS decision); a
demonstrated need for a development host override (with a security review).

---

## Amendment — 2026-07-21: method-scoped public host-guard exemption (M3D, ADR-017)

Approved at the M3D architecture gate, before implementation.

### Why the exact `/public/site` exemption no longer works

This ADR exempted **exactly one path** from `KnownHostGuardMiddleware`
(`_PUBLIC_SITE_PATH = "/api/v1/public/site"`), on the reasoning that the
public resolver owns all of its own Host failures and must always answer
with the neutral 404 rather than the guard's 400. M3D adds two more public
routes, one of them templated (`/api/v1/public/media/{asset_id}/{variant}`).
An exact-path set cannot express a templated path at all — the guard reads
the raw ASGI `scope["path"]` **before** routing, so no path parameter has
been matched yet. Left unamended, the new routes would answer an off-apex,
IP-literal, malformed, or missing Host with a **400** while `/public/site`
answers the identical request with a **404**: two sibling endpoints on one
router with two different public contracts, and a storefront forced to
handle both. The exemption therefore moves from an exact path to the
`/api/v1/public/` **prefix**, which is safe here because that prefix is
used by exactly one router — the host-resolved public router. The other
unauthenticated surfaces (`/api/v1/password-resets`,
`/api/v1/invitations`) sit outside it and keep their guard protection
unchanged.

### Why the exemption is method-scoped

Only `GET` and `HEAD` are exempt. The justification for exempting a public
route is that its handler resolves the tenant itself and owns its failure
contract; that argument applies solely to the safe, read-only methods the
public surface actually serves. A `POST`, `PUT`, `PATCH`, or `DELETE` under
`/api/v1/public/` matches no public route, so there is no resolver to own
the failure and no neutral-404 contract to honor — such a request keeps the
guard's ADR-008 400 from an unrecognized Host, and a 405 from a recognized
one. Scoping by method also means a future unsafe public route cannot
silently inherit a Host exemption it was never reviewed for.

### Why this remains routing hardening, not tenant authentication

Unchanged from the original decision: the guard is coarse input validation
over an unauthenticated client-supplied header. It never selects a
Business, never grants access, and never substitutes for authorization —
which continues to rest on the session cookie, CSRF checks, membership, and
route identifiers. Widening the exemption removes a **400** for requests
that were already going to be rejected by the resolver with a **404**; it
grants no read that the resolver would not otherwise permit, because the
resolver still requires a Host that names an active Business by canonical
slug. Tenant selection remains Host-only, with no header, query, cookie, or
forwarded-header alternative.

### How CI prevents a future public route from omitting tenant resolution

The exemption's safety rests on every exempt route resolving the tenant
itself, so that property is now a permanent test rather than a convention.
A unit test composes the real application and, for **every** registered
route under `/api/v1/public/` whose methods include `GET` or `HEAD`,
recursively walks the FastAPI `Dependant` graph (`route.dependant`, its
`.dependencies`, and each `.call`) and asserts that
`resolve_public_business` appears in it. The walk covers schema-hidden
routes, so the M3D companion `HEAD` routes are checked exactly like their
`GET` counterparts. A companion test asserts that only `GET`/`HEAD` are
exempt and that the non-public unauthenticated routers remain guarded.
Adding a public route without the resolver dependency therefore fails the
suite in plain `uv run pytest` and in CI — it cannot reach a reviewer as a
silent omission.
