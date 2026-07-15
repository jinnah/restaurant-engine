# 01 — Product Scope

Summarizes blueprint §2. The blueprint is authoritative.

## Initial market and defaults

Independent Bengali-owned restaurants in Buffalo, NY, then selected NYC
restaurants. Bengali-specific needs are treated as structured, configurable
data — never hard-coded into core domain logic.

- Currency: USD (per-tenant currency remains a tenant attribute).
- Timezone: America/New_York (per-tenant attribute).
- Locales: English first, Bengali-capable presentation.
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
