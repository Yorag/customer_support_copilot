from __future__ import annotations

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import validate_required_settings


def main() -> None:
    validate_required_settings(
        ("POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_DB", "POSTGRES_USER")
    )
    alembic_config = Config("alembic.ini")
    command.upgrade(alembic_config, "head")
    print("Database migrations applied successfully.")


if __name__ == "__main__":
    main()
