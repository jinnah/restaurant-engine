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
- API container (FastAPI) — with `MEDIA_STORAGE_ROOT` on a persistent
  named volume or host bind mount, **never a path inside the ephemeral
  container filesystem** (M3C obligation; enforced when the production
  compose file is authored in Milestone 8);
- control-center static assets;
- PostgreSQL on a private container network with a persistent volume;
- worker container once outbox processing begins;
- scheduled encrypted backup job.

Only ports 80 and 443 are public. SSH is key-only and restricted. PostgreSQL
is never exposed publicly.

## Media storage root (M3C, ADR-017)

Production requires an explicit, durable, absolute `MEDIA_STORAGE_ROOT`
outside every publicly served static directory; the API process is its
only reader and writer. Startup fails fast unless the root exists, is a
directory, and passes a write/stat/delete probe; `/health/ready` repeats
a cheap collision-safe probe as the `media_storage` check. Ownership and
permissions: the root and its subdirectories are owned by the API process
user, directories `0750`, files `0640`, no execute bits, no other
account writes there (Windows development machines rely on default
inherited ACLs). The development default `backend/var/media` is
gitignored and development-only.

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

### One logical backup set: PostgreSQL + media root (M3C, ADR-017)

From M3C onward a `pg_dump` alone is **not** a complete backup:
PostgreSQL and `MEDIA_STORAGE_ROOT` form one logical backup set and are
never backed up or restored separately. Required sequence (a short
maintenance window that quiesces media mutations is acceptable at
first-VPS scale):

1. Quiesce API/media mutations (stop the API for the window).
2. Run the pre-backup verification (`sweep_media.py --verify`): it
   recomputes every stored object's SHA-256 and byte size against the
   database rows and flags every storage-only object regardless of age.
   It never mutates and exits non-zero on any inconsistency.
3. **If verification reports any finding, do not proceed.** Repair first:
   delete eligible storage-only orphans (`sweep_media.py --apply`),
   restore or explicitly delete via the API any asset rows whose objects
   are missing, and investigate every size/checksum mismatch and every
   `unreadable` or malformed/unknown storage entry (these are never
   auto-deleted). Then **re-run `--verify`**.
4. Proceed only after a verification run reports **zero** findings and
   exits `0`. A backup taken with unresolved findings must never be
   labeled a verified complete backup — do not continue past this gate on
   an unresolved condition.
5. Create the `pg_dump` (custom format).
6. Archive the media root.
7. Write the shared-set manifest: one backup-set id embedded in both
   artifact filenames, plus SHA-256 of each artifact and asset/object/
   byte counts.
8. Restore only as one matching logical set: database first, then the
   media root, from the same set id.
9. Repeat the checksum/inventory verification after restore and require a
   clean `0` result again (a consistent pair reports zero findings).

## Deployment workflow (target)

Build immutable images in CI, tag by commit SHA, deploy a reviewed release,
apply forward migrations once, run health checks, execute a smoke test, and
retain the previous image for rollback. Database rollback uses forward-fix
migrations, never unsafe down-migration assumptions. Production artifacts are
never built manually on the VPS from an unverified working tree.

## Checklist placeholders (completed in Milestone 8)

- [ ] Provisioning and hardening steps for a clean VPS
- [ ] Persistent mount (volume or bind) for `MEDIA_STORAGE_ROOT` in the
      production compose topology (M3C obligation)
- [ ] Secret provisioning procedure (no committed secrets, no defaults)
- [ ] TLS issuance and renewal procedure
- [ ] Deploy, verify, and rollback procedure
- [ ] Backup, restore, and drill procedure
- [ ] Monitoring, alerting, and on-call notes
- [ ] Incident and support runbook for pilot restaurants
