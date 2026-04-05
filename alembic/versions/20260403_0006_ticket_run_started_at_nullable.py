"""allow queued ticket runs without started_at

Revision ID: 20260403_0006
Revises: 20260403_0005
Create Date: 2026-04-03 18:45:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260403_0006"
down_revision = "20260403_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("ticket_runs", "started_at", existing_type=sa.DateTime(timezone=True), nullable=True)


def downgrade() -> None:
    op.alter_column("ticket_runs", "started_at", existing_type=sa.DateTime(timezone=True), nullable=False)
