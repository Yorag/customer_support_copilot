"""normalize legacy ticket run trigger types

Revision ID: 20260415_0007
Revises: 20260403_0006
Create Date: 2026-04-15 10:20:00
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260415_0007"
down_revision = "20260403_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE ticket_runs
        SET trigger_type = 'manual_api'
        WHERE trigger_type = 'offline_eval'
        """
    )


def downgrade() -> None:
    # This data normalization is intentionally not reversed because existing
    # `manual_api` rows are indistinguishable from migrated legacy rows.
    pass
