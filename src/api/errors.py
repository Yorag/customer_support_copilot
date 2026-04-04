from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.contracts.core import (
    CoreSchemaError,
    InvalidStateTransitionError,
    LeaseConflictError,
    VersionConflictError,
)

from .schemas import ErrorPayload, ErrorResponse


@dataclass(frozen=True)
class ApiError(Exception):
    code: str
    message: str
    status_code: int
    details: Optional[Dict[str, Any]] = None


def build_error_response(
    *,
    code: str,
    message: str,
    status_code: int,
    details: Optional[Dict[str, Any]] = None,
) -> JSONResponse:
    payload = ErrorResponse(
        error=ErrorPayload(
            code=code,
            message=message,
            details=details,
        )
    )
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json", fallback=lambda value: str(value)),
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return build_error_response(
            code=exc.code,
            message=exc.message,
            status_code=exc.status_code,
            details=exc.details,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return build_error_response(
            code="validation_error",
            message="Request validation failed.",
            status_code=422,
            details={"errors": exc.errors()},
        )

    @app.exception_handler(VersionConflictError)
    async def handle_version_conflict(
        request: Request,
        exc: VersionConflictError,
    ) -> JSONResponse:
        return build_error_response(
            code="ticket_version_conflict",
            message="Ticket version does not match current version.",
            status_code=409,
            details={
                "entity": exc.entity,
                "expected_version": exc.expected,
                "actual_version": exc.actual,
            },
        )

    @app.exception_handler(InvalidStateTransitionError)
    async def handle_invalid_state_transition(
        request: Request,
        exc: InvalidStateTransitionError,
    ) -> JSONResponse:
        return build_error_response(
            code="invalid_state_transition",
            message=str(exc),
            status_code=409,
            details={
                "entity": exc.entity,
                "current_status": exc.current_status,
                "target_status": exc.target_status,
                "allowed_transitions": list(exc.allowed_transitions),
            },
        )

    @app.exception_handler(LeaseConflictError)
    async def handle_lease_conflict(
        request: Request,
        exc: LeaseConflictError,
    ) -> JSONResponse:
        return build_error_response(
            code="lease_conflict",
            message=str(exc),
            status_code=409,
            details={
                "ticket_id": exc.ticket_id,
                "lease_owner": exc.lease_owner,
            },
        )

    @app.exception_handler(CoreSchemaError)
    async def handle_core_schema_error(
        request: Request,
        exc: CoreSchemaError,
    ) -> JSONResponse:
        return build_error_response(
            code="validation_error",
            message=str(exc),
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        return build_error_response(
            code="external_dependency_failed",
            message="The request failed because a required dependency call did not succeed.",
            status_code=502,
        )
