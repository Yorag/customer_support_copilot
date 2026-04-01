from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260331_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_metadata",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_index(
        "ix_app_metadata_created_at",
        "app_metadata",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_app_metadata_created_at", table_name="app_metadata")
    op.drop_table("app_metadata")
