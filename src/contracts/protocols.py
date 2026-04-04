from __future__ import annotations

from typing import Any, ContextManager, Protocol

from sqlalchemy.orm import Session

from src.db.repositories import RepositoryBundle


class GmailClientProtocol(Protocol):
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
