# 01 — Product Scope

Summarizes blueprint §2. The blueprint is authoritative.

## Positioning (clarified 2026-07-29; see ADR-021)

Restaurant Engine is an **English-first, universal U.S. restaurant
platform** for restaurants across cuisines, cultures, ownership
communities, and geographic markets. The initial go-to-market segment —
independent Bengali-owned restaurants in Buffalo, NY, then selected NYC
restaurants — is a sales strategy, not a product boundary or architectural
identity. No market segment's specifics are hard-coded into domain logic,
branding, defaults, themes, routes, or business rules; community- or
cuisine-specific needs are expressed as structured, configurable data.
The platform remains **restaurant-specific**: it is not a general website
builder for retail, service, or other non-restaurant businesses.

## Initial market and defaults

- Currency: USD (per-tenant currency remains a tenant attribute).
- Timezone: America/New_York (per-tenant attribute).
- Presentation: English-first, Unicode-capable, for U.S. restaurants across
  cuisines and communities. Rendering is verified against complex-script
  fixtures — Bengali is the required initial complex-script fixture
  (conjuncts, matras, ZWNJ/ZWJ, NFC) — as an engineering test, never as
  product positioning, seed data, or a production default.
- US address and phone formats.
- Halal and dietary attributes are structured menu data.
- Pickup ordering first; cash or pay-at-store first.
- One location per tenant in the first commercial release.

## Users

| User                  | Primary jobs                             | Surface                      |
| --------------------- | ---------------------------------------- | ---------------------------- |
| Guest customer        | Browse, customize, order, track          | Storefront                   |
| Returning customer    | Reorder, history, details                | Storefront (later phase)     |
| Restaurant staff      | Advance orders, mark items unavailable   | Restaurant workspace         |
| Restaurant manager    | Menu, hours, content, staff              | Restaurant workspace         |
| Restaurant owner      | Publish storefront, configure operations | Restaurant workspace         |
| Platform operator     | Onboard, suspend, support, entitlements  | Control center               |
| Platform support user | Constrained, auditable diagnosis         | Control center (later phase) |

## First commercial release

Tenant onboarding · premium multi-tenant storefront · menu with categories,
modifiers, availability, and media · hours and pickup availability · guest
cart and pickup checkout · cash/pay-at-store order placement · customer
order-status page · restaurant order board · role-based restaurant
administration · system administration, feature entitlements, and audit
events · subdomain hosting · production backup, monitoring, and recovery.

## Explicitly deferred

Delivery logistics · POS integrations · online card payments · native mobile
apps · loyalty, gift cards, subscriptions · AI assistants · reservations ·
SMS campaigns · marketplace/directory · multi-location tenants · automatic
custom-domain provisioning · custom CSS or arbitrary HTML · microservices.

Deferral preserves a clean architectural seam. It does **not** mean creating
placeholder implementations or empty modules now.
