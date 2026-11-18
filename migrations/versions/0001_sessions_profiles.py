"""Anonymous sessions and basic profiles."""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "anonymous_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_anonymous_sessions_expires_at", "anonymous_sessions", ["expires_at"])
    op.create_table(
        "profiles",
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("anonymous_sessions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("age", sa.Integer(), nullable=True),
        sa.Column("region", sa.String(50), nullable=True),
        sa.Column("employment_status", sa.String(30), nullable=True),
        sa.Column("housing_status", sa.String(30), nullable=True),
        sa.Column("interests", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("profiles")
    op.drop_index("ix_anonymous_sessions_expires_at", table_name="anonymous_sessions")
    op.drop_table("anonymous_sessions")
