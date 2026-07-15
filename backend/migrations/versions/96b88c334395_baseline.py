"""Baseline: permanent anchor of the migration chain.

Deliberately empty — Milestone 1 ships no product-domain tables. The first
real schema migration (Milestone 2) sets this revision as its
``down_revision``, and `alembic upgrade head` on an empty database is
verified from this point on.

Revision ID: 96b88c334395
Revises:
Create Date: 2026-07-14 23:42:08.572468
"""

from collections.abc import Sequence

revision: str = "96b88c334395"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
