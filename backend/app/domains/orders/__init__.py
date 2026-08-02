"""Orders domain (M6A, ADR-026).

Owns checkout validation, order numbering, immutable snapshots, totals,
status transitions, idempotency, and the transactional outbox. Depends on
businesses (resolution, lifecycle, currency, timezone), catalog (the
explicit checkout view — never catalog's models), hours (the pure
pickup-slot service and the effective fulfillment policy), and audit.
Catalog, hours, and storefront never import orders.
"""
