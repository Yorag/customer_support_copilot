from __future__ import annotations

from src.bootstrap.container import ServiceContainer, get_service_container
from src.contracts.protocols import TicketStoreProtocol


class TicketApiServiceBase:
    def __init__(
        self,
        store: TicketStoreProtocol,
        container: ServiceContainer | None = None,
    ) -> None:
        self._store = store
        self._container = container or get_service_container()
