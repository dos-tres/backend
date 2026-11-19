"""Add catalog_items: policies and youth-center programs for recommendation."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "catalog_items",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("age_min", sa.Integer(), nullable=True),
        sa.Column("age_max", sa.Integer(), nullable=True),
        sa.Column("region_cds", postgresql.ARRAY(sa.String(length=10)), nullable=False),
        sa.Column("sido_cds", postgresql.ARRAY(sa.String(length=2)), nullable=False),
        sa.Column("domains", postgresql.ARRAY(sa.String(length=1)), nullable=False),
        sa.Column("situations", postgresql.ARRAY(sa.String(length=20)), nullable=False),
        sa.Column("access_type", sa.String(length=10), nullable=True),
        sa.Column("deadline", sa.Date(), nullable=True),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_catalog_items")),
    )
    op.create_index("ix_catalog_items_kind_status", "catalog_items", ["kind", "status"], unique=False)
    op.create_index("ix_catalog_items_region_cds", "catalog_items", ["region_cds"], unique=False,
                    postgresql_using="gin")
    op.create_index("ix_catalog_items_sido_cds", "catalog_items", ["sido_cds"], unique=False,
                    postgresql_using="gin")


def downgrade() -> None:
    op.drop_index("ix_catalog_items_sido_cds", table_name="catalog_items", postgresql_using="gin")
    op.drop_index("ix_catalog_items_region_cds", table_name="catalog_items", postgresql_using="gin")
    op.drop_index("ix_catalog_items_kind_status", table_name="catalog_items")
    op.drop_table("catalog_items")
