from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import get_settings

from .errors import register_exception_handlers
from .routes import router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.api.title,
        version=settings.api.version,
        description=settings.api.description,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )
    register_exception_handlers(app)
    app.include_router(router)
    return app
