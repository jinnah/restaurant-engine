# 07 — Deployment Runbook

> **Status: future-facing skeleton.** Nothing in this document is operational
> yet. It records the deployment architecture the project is building toward
> (blueprint §17) so earlier milestones make compatible choices. It becomes a
> real runbook in Milestone 8, and every section below is completed and
> drill-tested before the first pilot restaurant.

## Target production topology

One appropriately sized Ubuntu VPS running Docker Compose:

- Nginx reverse proxy (TLS, host routing, compression, request limits);
- storefront container (Next.js);
- API container (FastAPI);
- control-center static assets;
- PostgreSQL on a private container network with a persistent volume;
- worker container once outbox processing begins;
- scheduled encrypted backup job.

Only ports 80 and 443 are public. SSH is key-only and restricted. PostgreSQL
is never exposed publicly.

## Domain strategy

Launch tenants on `{slug}.platform-domain.com` with a wildcard DNS record and
wildcard certificate. Custom domains are a later capability with a defined
verification, issuance, renewal, and abuse-control design before automation.

## Backups (to be implemented and drilled in Milestone 8)

- Automated encrypted PostgreSQL logical backups to an off-VPS destination.
- Retention tiers (daily/weekly/monthly), checksums, and failure alerts.
- Media backup aligned with database backup semantics.
- Documented full restore to a clean host, verified by restore tests that
  check tenant, menu, storefront, and order data.
- Reliability targets: no acknowledged order may disappear; documented RPO
  and RTO; quarterly restore drills initially.

## Deployment workflow (target)

Build immutable images in CI, tag by commit SHA, deploy a reviewed release,
apply forward migrations once, run health checks, execute a smoke test, and
retain the previous image for rollback. Database rollback uses forward-fix
migrations, never unsafe down-migration assumptions. Production artifacts are
never built manually on the VPS from an unverified working tree.

## Checklist placeholders (completed in Milestone 8)

- [ ] Provisioning and hardening steps for a clean VPS
- [ ] Secret provisioning procedure (no committed secrets, no defaults)
- [ ] TLS issuance and renewal procedure
- [ ] Deploy, verify, and rollback procedure
- [ ] Backup, restore, and drill procedure
- [ ] Monitoring, alerting, and on-call notes
- [ ] Incident and support runbook for pilot restaurants
