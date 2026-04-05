"""add ticket run app metadata

Revision ID: 20260403_0005
Revises: 20260401_0004
Create Date: 2026-04-03 14:55:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260403_0005"
down_revision = "20260401_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")
    op.add_column("ticket_runs", sa.Column("app_metadata", json_type, nullable=True))


def downgrade() -> None:
    op.drop_column("ticket_runs", "app_metadata")
