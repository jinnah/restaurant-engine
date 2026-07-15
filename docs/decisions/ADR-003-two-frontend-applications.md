# ADR-003: Two frontend applications — storefront and control center

- **Status:** Accepted
- **Date:** 2026-07-14
- **Deciders:** Product owner, principal architect

## Context

The product serves three audiences: customers, restaurant staff/owners, and
platform operators. The predecessor prototype used **three** separate React
SPAs (storefront, restaurant admin, system admin), which duplicated auth,
navigation, tables, forms, and design-system code — while the customer
storefront, as a client-rendered SPA, could not deliver SEO or
first-paint performance appropriate for a premium public site.

## Decision

Exactly **two** frontend applications:

1. **Storefront** — Next.js App Router with server rendering: tenant-host
   resolution, SEO metadata, structured data, and minimal client JavaScript
   (interactive islands only: cart, modifier dialog, order tracker).
2. **Control center** — one React + Vite + TypeScript SPA with React Router,
   serving restaurant administration and platform administration as
   permission-gated route groups.

## Alternatives considered

- **Three SPAs (prototype):** rejected — duplication without isolation
  benefit; restaurant and platform admin share nearly all operational UX.
- **One application for everything:** rejected — the storefront's SSR/SEO/
  performance needs conflict with SPA admin ergonomics.
- **Full-stack Next.js (no FastAPI):** rejected — existing FastAPI strength,
  typed API tests, and future integrations make a dedicated API lower-risk;
  Next.js handles presentation, not business logic.

## Consequences

Customer pages are indexable and fast; admin surfaces share components,
navigation, and the generated client. Platform routes must be rigorously
permission-gated inside the control center — the API remains the
authorization authority, with route guards as UX only.

## Security and operations impact

Two build artifacts instead of three. The control center must never assume
client-side gating is protection; this is a permanent API test obligation.

## Reconsideration triggers

Evidence that platform administration needs isolation (compliance, separate
operators); storefront interactivity growing to where the islands approach
fights the framework.
