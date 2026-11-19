"""Add catalog_item_changes: history of created/updated/reopened/closed catalog items."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "catalog_item_changes",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("item_id", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("change_type", sa.String(length=10), nullable=False),
        sa.Column("old_hash", sa.String(length=64), nullable=True),
        sa.Column("new_hash", sa.String(length=64), nullable=True),
        sa.Column("changed_fields", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("old_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("changed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("change_type IN ('created', 'updated', 'reopened', 'closed')",
                           name=op.f("ck_catalog_item_changes_change_type")),
        sa.ForeignKeyConstraint(["item_id"], ["catalog_items.id"], ondelete="CASCADE",
                                name=op.f("fk_catalog_item_changes_item_id_catalog_items")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_catalog_item_changes")),
    )
    op.create_index("ix_catalog_item_changes_item_id_changed_at", "catalog_item_changes",
                    ["item_id", "changed_at"], unique=False)
    op.create_index("ix_catalog_item_changes_changed_at", "catalog_item_changes", ["changed_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_catalog_item_changes_changed_at", table_name="catalog_item_changes")
    op.drop_index("ix_catalog_item_changes_item_id_changed_at", table_name="catalog_item_changes")
    op.drop_table("catalog_item_changes")
