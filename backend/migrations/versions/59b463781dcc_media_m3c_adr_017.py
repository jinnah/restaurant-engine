"""Media (M3C, ADR-017).

Two tenant-owned tables plus the menu-item attachment:

* ``media_assets`` — one processed image asset per row (kind
  CHECK-limited to ``image``; video is a later additive migration).
  Status ``pending``/``active`` with the pairing CHECK binding
  ``pending_expires_at`` to pending rows (48-hour TTL on the database
  clock, set in SQL at insert). Canonical facts only: post-processing
  WebP dimensions (1-2560), BIGINT byte size, SHA-256 (lowercase hex)
  of the canonical stored object. ``UNIQUE (business_id, id)`` is the
  attachment composite-FK target; the partial pending-expiry index
  serves the sweep.
* ``media_asset_variants`` — relational 320/640/1280 renditions, each
  with the size and checksum of the bytes actually retained; variants
  CASCADE with their asset; one row per logical variant.
* ``menu_items`` gains ``image_media_id``/``image_alt_text``: the
  composite tenant-safe FK (RESTRICT — referenced media cannot be
  deleted) plus the alt-requires-image pairing and 300-char CHECKs
  (added by hand: autogenerate does not detect CHECKs on existing
  tables).

Value columns carry application-side defaults only (server defaults on
timestamps alone). The downgrade drops the attachment and both tables
(dev/scratch only; production policy is forward-fix, blueprint §17.4).

Revision ID: 59b463781dcc
Revises: f8ad809962f8
Create Date: 2026-07-20 16:49:25.642387
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "59b463781dcc"
down_revision: str | Sequence[str] | None = "f8ad809962f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "media_assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("pending_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("declared_content_type", sa.Text(), nullable=False),
        sa.Column("source_format", sa.Text(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("checksum_sha256", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(status = 'pending') = (pending_expires_at IS NOT NULL)",
            name=op.f("ck_media_assets_pending_expiry_pairing"),
        ),
        sa.CheckConstraint(
            "checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_media_assets_checksum_sha256_format"),
        ),
        sa.CheckConstraint("kind IN ('image')", name=op.f("ck_media_assets_kind_known")),
        sa.CheckConstraint(
            "source_format IN ('jpeg', 'png', 'webp')",
            name=op.f("ck_media_assets_source_format_known"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'active')", name=op.f("ck_media_assets_status_known")
        ),
        sa.CheckConstraint("byte_size > 0", name=op.f("ck_media_assets_byte_size_positive")),
        sa.CheckConstraint(
            "char_length(declared_content_type) BETWEEN 1 AND 160",
            name=op.f("ck_media_assets_declared_content_type_length"),
        ),
        sa.CheckConstraint(
            "char_length(original_filename) BETWEEN 1 AND 160",
            name=op.f("ck_media_assets_original_filename_length"),
        ),
        sa.CheckConstraint("height BETWEEN 1 AND 2560", name=op.f("ck_media_assets_height_range")),
        sa.CheckConstraint(
            "updated_at >= created_at", name=op.f("ck_media_assets_updated_after_creation")
        ),
        sa.CheckConstraint("width BETWEEN 1 AND 2560", name=op.f("ck_media_assets_width_range")),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            name=op.f("fk_media_assets_business_id_businesses"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media_assets")),
        sa.UniqueConstraint("business_id", "id", name=op.f("uq_media_assets_business_id_id")),
    )
    op.create_index(
        "ix_media_assets_business_id_created_at",
        "media_assets",
        ["business_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_media_assets_pending_expiry",
        "media_assets",
        ["business_id", "pending_expires_at"],
        unique=False,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_table(
        "media_asset_variants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("business_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("variant", sa.Text(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("checksum_sha256", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "checksum_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_media_asset_variants_checksum_sha256_format"),
        ),
        sa.CheckConstraint(
            "variant IN ('w320', 'w640', 'w1280')",
            name=op.f("ck_media_asset_variants_variant_known"),
        ),
        sa.CheckConstraint(
            "byte_size > 0", name=op.f("ck_media_asset_variants_byte_size_positive")
        ),
        sa.CheckConstraint(
            "height BETWEEN 1 AND 2560", name=op.f("ck_media_asset_variants_height_range")
        ),
        sa.CheckConstraint(
            "width BETWEEN 1 AND 2560", name=op.f("ck_media_asset_variants_width_range")
        ),
        sa.ForeignKeyConstraint(
            ["business_id", "asset_id"],
            ["media_assets.business_id", "media_assets.id"],
            name=op.f("fk_media_asset_variants_business_id_asset_id_media_assets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["business_id"],
            ["businesses.id"],
            name=op.f("fk_media_asset_variants_business_id_businesses"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media_asset_variants")),
        sa.UniqueConstraint(
            "business_id",
            "asset_id",
            "variant",
            name=op.f("uq_media_asset_variants_business_id_asset_id_variant"),
        ),
    )
    op.add_column("menu_items", sa.Column("image_media_id", sa.Uuid(), nullable=True))
    op.add_column("menu_items", sa.Column("image_alt_text", sa.Text(), nullable=True))
    op.create_foreign_key(
        op.f("fk_menu_items_business_id_image_media_id_media_assets"),
        "menu_items",
        "media_assets",
        ["business_id", "image_media_id"],
        ["business_id", "id"],
        ondelete="RESTRICT",
    )
    # Hand-added: autogenerate does not detect CHECK constraints on
    # existing tables (the M3A/M3B tables carried theirs in create_table).
    op.create_check_constraint(
        op.f("ck_menu_items_image_alt_requires_image"),
        "menu_items",
        "image_alt_text IS NULL OR image_media_id IS NOT NULL",
    )
    op.create_check_constraint(
        op.f("ck_menu_items_image_alt_text_length"),
        "menu_items",
        "image_alt_text IS NULL OR char_length(image_alt_text) <= 300",
    )


def downgrade() -> None:
    # Exact reverse of creation (attachment first, children before
    # parents). Dev/scratch only; production policy is forward-fix.
    op.drop_constraint(op.f("ck_menu_items_image_alt_text_length"), "menu_items", type_="check")
    op.drop_constraint(op.f("ck_menu_items_image_alt_requires_image"), "menu_items", type_="check")
    op.drop_constraint(
        op.f("fk_menu_items_business_id_image_media_id_media_assets"),
        "menu_items",
        type_="foreignkey",
    )
    op.drop_column("menu_items", "image_alt_text")
    op.drop_column("menu_items", "image_media_id")
    op.drop_table("media_asset_variants")
    op.drop_index(
        "ix_media_assets_pending_expiry",
        table_name="media_assets",
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.drop_index("ix_media_assets_business_id_created_at", table_name="media_assets")
    op.drop_table("media_assets")
