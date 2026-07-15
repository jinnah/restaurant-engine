# ADR-001: Modular monolith with explicit extraction criteria

- **Status:** Accepted
- **Date:** 2026-07-14
- **Deciders:** Product owner, principal architect

## Context

Restaurant Engine is a multi-tenant platform (storefront, restaurant
workspace, platform control center) built by a very small team that values
learning, stability, and low operational burden. The predecessor prototype
proved the product concept but also showed that structural mistakes get
expensive once orders, payments, and messaging multiply the surfaces.

## Decision

The backend is a **modular monolith**: one FastAPI deployable and one
PostgreSQL database, organized into domain modules (identity, tenants,
catalog, storefront, media, hours, orders, audit) with clear public
interfaces. Modules communicate through in-process service calls and domain
events. Network boundaries are not introduced speculatively.

## Alternatives considered

- **Microservices:** rejected — no independent scaling, failure-isolation,
  team-ownership, or regulatory pressure exists; would multiply operational
  cost on a one-VPS topology.
- **Single unstructured application (prototype style):** rejected — the
  prototype demonstrated that router-to-ORM logic without service boundaries
  accumulates hidden coupling.

## Consequences

Simple deployment and transactions; refactoring stays cheap. The discipline
cost: dependency direction (HTTP → services → repositories) and cross-domain
rules must be enforced in review, since the process boundary will not do it.

## Security and operations impact

One deployable and one database simplify backup, restore, monitoring, and
the tenant-isolation story. No inter-service auth surface exists.

## Reconsideration triggers

A workload needing independent scaling or failure isolation (e.g. media
processing, notification fan-out at volume); a second team taking ownership
of a domain; a regulatory boundary requiring separation.
