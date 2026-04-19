from __future__ import annotations

from typing import Any, ContextManager, Protocol

from sqlalchemy.orm import Session

from src.db.repositories import RepositoryBundle


class GmailClientProtocol(Protocol):
    def scan_inbox(
        self,
        max_results: int | None = None,
    ) -> dict[str, Any]:
        ...

    def fetch_unanswered_emails(
        self,
        max_results: int | None = None,
    ) -> list[dict[str, Any]]:
        ...

    def create_draft_reply(self, initial_email: Any, reply_text: str) -> Any:
        ...

    def send_reply(self, initial_email: Any, reply_text: str) -> Any:
        ...


class PolicyProviderProtocol(Protocol):
    def get_policy(self, category: str | None = None) -> str:
        ...


class TicketStoreProtocol(Protocol):
    def ping(self) -> bool:
        ...

    def session_scope(self) -> ContextManager[Session]:
        ...

    def repositories(self, session: Session) -> RepositoryBundle:
        ...


class TraceExporterProtocol(Protocol):
    def create_root_run(
        self,
        *,
        run: Any,
        ticket: Any,
        inputs: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> Any | None:
        ...

    def create_child_run(
        self,
        *,
        parent: Any | None,
        event: Any,
        inputs: dict[str, Any] | None = None,
        outputs: dict[str, Any] | None = None,
    ) -> Any | None:
        ...

    def finalize_run(
        self,
        *,
        root: Any | None,
        ended_at: Any,
        outputs: dict[str, Any],
        error: str | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> None:
        ...


class MemoryExtractorProtocol(Protocol):
    def extract(self, *, case_context: dict[str, Any]) -> Any:
        ...
