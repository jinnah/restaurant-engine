# ADR-012: Business is the tenant aggregate

- **Status:** Accepted
- **Date:** 2026-07-17
- **Deciders:** Product owner, principal architect

## Context

The platform direction was deliberately reconsidered before M2B was
published: Restaurant Engine remains one modular monolith with strict
tenant isolation, launching with independent restaurants — but the same
reusable capabilities (catalog, storefront, ordering, and a future AI
assistant) fit other very small businesses: home-based cake and clothing
businesses, small online sellers. M2B had just established the
foundational tenant vocabulary under the name `Restaurant`. Renaming after
publication would have been a breaking-change process across the API
contract (operation ids are permanent, ADR-009), the generated client,
the schema, and every later milestone; renaming before publication was
free. An independent review had verified M2B's behavior, so the rename
could be executed as a pure-vocabulary change.

## Decision

- **One Business is one tenant.** The tenant aggregate, its table, and its
  key are `Business` / `businesses` / `business_id`. There is no separate
  persistent `tenant_id` — one concept, one name. A future `TenantContext`
  application abstraction may _wrap_ `business_id`; it is not built until
  a consumer exists.
- **One Business has one storefront** in version one. Multiple locations,
  multiple storefronts, parent organizations, and business groups are
  deferred.
- **Users may belong to multiple Businesses** through identity-owned
  memberships (unchanged from ADR-011).
- **Vocabulary:** capabilities are `platform.businesses.manage` and
  `business.view`; API routes are `/api/v1/businesses/{business_id}` and
  `/api/v1/platform/businesses…`; audit lifecycle actions are
  `business.created/activated/suspended/reactivated/closed`; the session
  projection fields are `business_id/business_slug/business_name/role/
business_status`. The M2A-created `audit_events.restaurant_id` column
  and its cursor index were renamed to `business_id` by the (unmerged,
  revised-in-place) M2B migration; merged M2A history is untouched.
- **No `business_type` yet.** M2B's schema, lifecycle, and capabilities
  are already type-agnostic; business type/presets belong to a later
  onboarding/configuration milestone where a consumer exists.
- **"Tenant/tenancy" remains the mechanism vocabulary** (tenant isolation,
  tenant-scoped repositories, the docs/04 exception taxonomy). Business is
  the thing; tenancy is how it is isolated.
- **Restaurants remain the first vertical and launch market** (Bengali-
  owned restaurants in Buffalo, then NYC — docs/01 is unchanged).
- **Branding is unchanged:** the product, repository, packages, container,
  and database keep the Restaurant Engine name until a deliberate branding
  decision with real customers.
- **Vertical differences must be expressed through reusable platform
  capabilities and configuration — never customer-specific code**: no
  checks against a particular business id, slug, or customer name; no
  per-customer deployments or code branches; no plugin framework.

## Alternatives considered

- **Keep `Restaurant` and generalize later:** rejected — every later
  milestone (catalog, orders, entitlements) would compound the rename, and
  after the first push the API contract makes it a breaking change.
- **Separate `tenant_id` alongside `business_id`:** rejected — two
  persistent names for one concept guarantees drift and confusion.
- **Introduce `business_type` now:** rejected — configuration with no
  consumer; nothing in M2B branches on vertical.
- **Abstract naming (`Tenant`, `Organization`, `Account`):** rejected —
  the strict design principles prefer simple explicit domain language;
  "business" is what the customers actually are.

## Consequences

M2C and every later milestone inherit Business vocabulary from the start.
The `businesses` domain (`app/domains/businesses/`) will absorb
entitlements, domains, and onboarding as planned for the businesses domain.
ADR-011 was amended in place (it was unmerged) rather than superseded; its
authorization, lifecycle, and isolation decisions are unchanged. The
governing blueprint and project prompt carry a short amendment pointing
here; their original restaurant-specific text remains valid as
first-vertical product context.

## Security and operations impact

None to behavior — the rename was executed with the independent review's
verification matrix re-run in full (schema parity, isolation matrix,
lifecycle guards, contract determinism). The development database was
migrated via a verified downgrade-to-M2A / re-upgrade procedure with a
preflight backup; production policy remains forward-fix.

## Reconsideration triggers

Multi-location or multi-storefront tenants; a parent-organization model;
the first feature that genuinely needs `business_type`; a customer-facing
platform brand decision.
