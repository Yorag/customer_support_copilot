from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import Header

from src.bootstrap.container import ServiceContainer, get_service_container


@dataclass(frozen=True)
class RequestContext:
    actor_id: Optional[str]
    request_id: Optional[str]
    idempotency_key: Optional[str]


def get_request_context(
    x_actor_id: Optional[str] = Header(default=None, alias="X-Actor-Id"),
    x_request_id: Optional[str] = Header(default=None, alias="X-Request-Id"),
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
) -> RequestContext:
    return RequestContext(
        actor_id=x_actor_id,
        request_id=x_request_id,
        idempotency_key=idempotency_key,
    )


def get_container() -> ServiceContainer:
    return get_service_container()
