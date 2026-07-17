# ADR-011: Capability authorization and the tenancy model

- **Status:** Accepted
- **Date:** 2026-07-16
- **Deciders:** Product owner, principal architect

## Context

Milestone 2B introduces the first tenant domain and the authorization model
every later milestone inherits: how platform versus restaurant authority is
expressed, where it is enforced, and how the restaurant lifecycle and its
invariants are protected. The blueprint fixes the direction (capability-based
permissions, tenant-scoped repositories, a restaurant state machine); this
ADR records the concrete contract fixed in the approved M2B proposal, its
addendum, and the four rulings.

## Decision

### Domain ownership (blueprint §7.1/§7.2)

**Identity** owns users, sessions, **memberships**, roles, and the capability
policy. **Tenants** owns restaurants and the lifecycle state machine.
`memberships.restaurant_id` references `restaurants` by table name only, so
identity imports no tenants persistence. The dependency graph is acyclic:
`app/api → identity + tenants`, `tenants → identity`, `identity → core`.
Where a response needs both domains — the enriched session view — the join
is composed in the application layer (`app/api/session_view`), not inside a
domain.

### Capabilities, not roles

One policy module (`identity/policies.py`) maps roles to named capabilities.
Two authorities, deliberately separate:

- **Platform capabilities** (`platform.restaurants.manage`) are conferred by
  `users.is_platform_admin` — never by a membership. Platform admins hold no
  membership rows.
- **Restaurant capabilities** (`restaurant.view`) are conferred by a
  membership `role` (owner/manager/staff). M2B enforces exactly these two
  capabilities; catalog/order/entitlement capabilities arrive with their
  milestones.

### Enforcement in services, resolution in HTTP

HTTP dependencies resolve context (`current_actor` → `ActorContext`) and
nothing more. Application services enforce: `require_platform_capability`
(pure) and `require_membership_capability` (DB-backed) run inside the
service before work, so a non-HTTP caller is enforced identically. Domain
errors render through the central `ApiError` handler.

### Failure semantics (existence non-disclosure)

- Restaurant-scoped routes: no membership row (nonexistent restaurant **or**
  nonmember, including a membership-less platform admin) → **404**; a member
  whose role lacks the capability → **403**.
- Platform routes: any non-platform-admin → **403**; a nonexistent
  restaurant, after the capability passes, → **404**.

### Restaurant lifecycle

State machine (blueprint §7.2): `provisioning → active → suspended → active`,
`suspended → closed`; `closed` terminal. **Closure is reachable only through
`suspended → closed`** (ruling 1). Each lifecycle command declares its exact
source state, so a command cannot reach a target through the wrong source.
Every transition runs under `SELECT … FOR UPDATE` on the restaurant row,
validates, audits, and commits in one transaction; illegal transitions →
409 `invalid_state`.

Owner invariant (ruling/decision 6): `provisioning` may have zero owners;
**entering `active` requires at least one owner** (enforced under the lock
for both activate and reactivate); `suspended` retains its owners; `closed`
retains its historical memberships. The removal/demotion-side guard ships
with whichever future milestone first introduces membership removal — not
M3 (catalog), which has no membership operations.

### Data and constraints

`restaurants`: UUID PK, unique canonical `slug` (3–63 lowercase, CHECK),
`status`/`currency` (`VARCHAR(3)`) CHECKs, `updated_at >= created_at` CHECK,
explicit `updated_at` bump on every transition. `memberships`: tenant-leading
`UNIQUE (restaurant_id, user_id)`, `user_id` index, partial owner index; FKs
to restaurants and users `ON DELETE RESTRICT`. The deferred
`audit_events.restaurant_id` FK is added here `ON DELETE RESTRICT`; its
migration downgrade nulls tenant-scoped audit ids first so audit rows
survive (never deleted, never dangling). Downgrade is a scratch/dev
operation only; production policy is forward-fix.

### Session projection

`login` returns the lean `SessionResponse` (user + CSRF token, identity
only). `auth_session` returns `SessionView` (adds `memberships`), composed
in the application layer from identity's self-scoped membership list and
tenant summaries, sorted `restaurant_name ASC, restaurant_id ASC`, including
all statuses. The membership list is always bound to the authenticated
actor's own id.

## Alternatives considered

- **`platform_admin` as a null-`restaurant_id` membership:** rejected — a
  nullable tenant key wrecks every composite constraint; the flag is cleaner.
- **Memberships in the tenants domain:** rejected — blueprint §7.1 assigns
  memberships to identity; an earlier proposal deviated and was corrected.
- **Enriching `auth_session` inside identity via a tenants query:** rejected
  — it inverts domain layering; the application layer owns cross-domain
  composition.
- **Native PostgreSQL enums for status/role:** rejected — `VARCHAR` + CHECK
  avoids `ALTER TYPE` churn when the value set grows.
- **Idempotent lifecycle transitions:** rejected — explicit 409 on illegal
  or same-state transitions is clearer for operators.
- **A shared transition table without per-endpoint source states:** rejected
  after review — it let `reactivate` activate a `provisioning` tenant,
  bypassing the owner guard.

## Consequences

Every later tenant-scoped domain inherits `require_membership_capability` and
the 404/403 contract; every platform operation inherits
`require_platform_capability`. Auth/tenancy tests require PostgreSQL. The
isolation matrix in `tests/security/` is permanent: tenant boundaries cannot
regress silently.

## Security and operations impact

Existence non-disclosure holds for restaurant-scoped access; platform
authority never leaks through membership. The owner guard prevents a
zero-owner active tenant. RESTRICT foreign keys prevent orphaning tenants
that have memberships or audit history. Public tenant resolution and the
neutral public 404 are **M2C** — M2B exposes no public surface.

## Reconsideration triggers

The first membership removal/demotion path (adds the removal-side owner
guard); a read-only platform role (splits `platform.restaurants.manage`);
RLS adoption (blueprint §8.4); a lifecycle needing direct
`provisioning`/`active` closure.
