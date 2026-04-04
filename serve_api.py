from __future__ import annotations

import uvicorn

from src.api.app import create_app
from src.config import get_settings


settings = get_settings()
app = create_app()


def main() -> None:
    uvicorn.run(app, host=settings.api.host, port=settings.api.port)


if __name__ == "__main__":
    main()
