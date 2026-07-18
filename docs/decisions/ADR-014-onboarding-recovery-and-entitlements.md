# ADR-014: Onboarding, Recovery, and Entitlements

- **Status:** Accepted
- **Date:** 2026-07-18
- **Deciders:** Product owner, principal architect

## Context

M2D turns account and membership creation into product flows (until now
only the bootstrap CLI and test fixtures could create them), provides the
interim account-recovery path, introduces the feature-entitlement model
later milestones consume, and opens the audit trail to authorized readers.
The approved architecture went through a full proposal, an addendum
resolving eleven review corrections, and binding product-owner rulings —
all recorded here. One migration (`6fbce030db33`) adds
`business_invitations`, `password_reset_tokens`, and
`feature_entitlements`.

Shared foundations fixed by this ADR:

- **One token policy.** Single-use credentials are 256-bit URL-safe
  random values stored only as SHA-256 hex digests (the session-token
  pattern, ADR-010) with an exact-shape CHECK. The raw value exists in
  exactly two places: the issuance response body and the redeemer's
  request body. Tokens never appear in URLs or query strings, lists,
  logs, audit details, or error responses. Issuance responses return the
  raw **token** (never a URL — the backend does not construct accept/reset
  links; the M2E frontend decides fragment-vs-paste presentation).
  Delivery is **manual and out of band** in M2D: no email provider,
  abstraction, outbox, or delivery job exists (the email channel is an
  M6+ decision), so there is no commit-versus-delivery consistency
  problem to solve.
- **Database-clock lifecycles.** `expires_at` is computed in SQL at
  insert and every validity predicate compares against `now()` in SQL —
  the application clock never participates in an expiry decision.
  Lifetimes are bounded typed settings (invitations 7 days, 1–30; resets
  60 minutes, 5–1440).
- **Two-phase redemption (Argon2 DoS guard).** Flows that set a password
  first run a cheap lock-free prevalidation of the token; only a token
  that appears usable reaches the Argon2 KDF (computed outside any
  transaction); the write transaction then re-locks and revalidates every
  condition authoritatively. Invalid tokens provably never invoke the KDF.
- **Deterministic lock order** `Business → Invitation → User →
  ResetToken`. Every M2D workflow (and the M2B lifecycle transitions)
  acquires row locks in this order, so issuance, replacement, revocation,
  acceptance, reset issuance, reset redemption, and entitlement
  replacement serialize instead of deadlocking. Partial unique indexes
  are backstops; residual races are converted to each surface's uniform
  response, never leaked as raw integrity errors.
- **Uniform public failure.** Every invalid-token condition (unknown,
  expired, revoked, used/accepted, email-registered-since-issuance,
  business-no-longer-joinable, inactive account, wrong authenticated
  account) returns the same neutral 404 for its surface.

## Invitations and recovery

**Invitations** are businesses-domain onboarding state (blueprint §7.2);
identity remains the sole owner of user/membership **writes** through two
narrow no-commit functions (`create_user_from_invitation`,
`memberships.create`) called inside the businesses acceptance transaction.

- Issuance: owners and managers via `business.members.invite`; the
  platform (via `platform.businesses.manage`) bootstraps the **first
  owner** — platform administrators still hold no membership. Role
  ceiling: an actor may only manage invitations whose role does not
  outrank their own, applied to **issue, replacement, and revocation**
  alike (a manager can neither mint an owner nor revoke/replace a pending
  owner invitation). Reissue revokes and replaces the live predecessor in
  one transaction (both events audited). One live invitation per
  business + normalized email (partial unique backstop). Issuable only
  for provisioning/active businesses; **revocable in any status** so
  outstanding credentials can always be invalidated. Issuance never
  discloses whether an account exists for the email.
- Acceptance: public **preview** returns the business name, role, and a
  masked `email_hint` (first character + `***` + domain; the full local
  part is never derivable). New users accept publicly (two-phase,
  atomic user + membership + acceptance in one transaction, **no
  auto-login**); existing users accept through an authenticated,
  CSRF-protected endpoint whose normalized email must match the
  invitation — this is the supported path to multi-business membership
  (ADR-012). Pending-only operational lists (limit/offset, `created_at
  DESC, id DESC`) carry no token material; history lives in the audit
  trail.

**Recovery** is identity-domain. Self-service reset stays deferred to the
first email channel (M6+); the M2D path is a **platform-administrator-
issued** single-use token. `platform.users.recover` is explicitly
**account-takeover-equivalent authority**: there is no public or silent
issuance path, every issuance is audited (issuing admin as actor, target
user id, correlation id, no token), admin-on-admin resets are allowed
(with the same trail) so a locked-out administrator needs no special
case, and the bootstrap CLI remains the documented break-glass. Issuance
revokes the live predecessor under the user lock (one live token per
user); inactive accounts are refused on both surfaces. Successful
redemption atomically sets the password, clears the login-backoff pair,
**revokes every session**, and consumes the token.

## Entitlements

Entitlements answer *which product capability a Business has enabled* —
deliberately separate from identity capabilities (*what an actor may
do*). The registry is an append-only code enum seeded with exactly
`online_ordering` (enforcement arrives with checkout, M6 — **no unused
enforcement helper or error code ships now**; that design happens with
its first real consumer). Presence-model table, tenant-leading unique,
default disabled. Platform-only mutation via idempotent full-set `PUT`
under the business row lock with a per-key audited diff; closed
businesses are immutable (409) while provisioning/active/suspended may be
configured; members of any role read their effective set. **Fail-closed
unknown keys:** a stored key missing from the registry (manual SQL,
drift) is excluded from every read, raises a structured error-level
operational alarm, and is deleted (audited) by the next replacement —
never silently enabled or legitimized.

## Audit access

The audit domain gains pure parameterized read queries; **authorization
and projection live in the application layer** (an audit→identity import
would create a cycle). Platform stream: `platform.audit.read`.
Business trail: `business.audit.read` (owner and manager; staff denied);
the query applies both tenant predicates unconditionally —
`business_id = <path id>` **and** `business_id IS NOT NULL` — so
platform-level events (logins, admin actions) are structurally invisible
in business scope. Cursor pagination on the BIGINT id (`id DESC`,
exclusive `before_id`, limit 1–100 default 50 — the design the M2A
schema reserved for this); UTC-aware time filters with range validation;
action filters must name a registered action (unknown → 422). Actors are
projected as bare `actor_user_id` (name/email enrichment deferred with
the user-list API). The API is GET-only: records are immutable.

**Stored `details` are never trusted.** Every recognized action maps to a
**typed read-time projection**: each permitted key has a value extractor
admitting only the expected bounded primitive type, so nested objects,
wrong types, oversized strings, extra keys, and unregistered actions all
project away; a sensitive-key sweep (password/token/hash/secret/cookie/
credential/authorization/session) is a final structural guarantee.
Adversarial tests insert hostile payloads directly into
`audit_events.details` and prove they never reach a response.

## Alternatives considered

- **Email delivery now** (provider interface, dev sink, or outbox):
  rejected — zero implementations/consumers until M6; the outbox arrives
  with orders; manual out-of-band delivery removes the
  commit-versus-delivery problem entirely.
- **Backend-constructed accept/reset URLs:** rejected — a URL puts the
  token at risk of referrer/history/log exposure and prematurely couples
  the backend to M2E routing; the raw token in a `no-store` response body
  does neither.
- **Rejecting invitations to existing emails:** rejected (revised ruling)
  — it would leave ADR-012's multi-business membership without a creation
  path; the authenticated, email-bound acceptance endpoint supports it
  safely.
- **A universal token framework/table:** rejected — invitations and
  resets share one policy and column conventions but are separate domain
  concepts with different lifecycles.
- **Key-name-allowlist audit projection copying stored values verbatim:**
  rejected (binding clarification) — a stored *value* can smuggle nested
  secrets; only typed extractors are acceptable.
- **`require_feature` helper + `feature_not_enabled` code in M2D:**
  rejected (revised ruling) — dead security code exercised only by tests.
- **Audit authorization inside the audit domain:** rejected — cycle.

## Consequences

Platform admins can onboard a business end to end (create → invite owner
→ accept → activate) and recover any account; owners grow their teams
within the role ceiling; a user can belong to multiple businesses; M6
checkout will consume `online_ordering`; M2E builds its accept/reset
pages on the preview/accept/redeem contracts. The M2 exit criteria
("platform admin can onboard; owner logs in only to assigned business")
are now satisfiable through the product.

## Reconsideration triggers

The first email channel (M6+: self-service reset, invitation delivery);
membership removal/demotion (adds the removal-side owner guard and
invitation-management interactions); the first entitlement enforcement
(M6: designs the check helper and its error semantics); a user-list API
(audit actor enrichment); audit retention/export requirements.
