from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Callable
from src.config import get_settings
from src.tools.types import (
    GmailClientProtocol,
    KnowledgeProviderProtocol,
    PolicyProviderProtocol,
    TicketStoreProtocol,
)


def _build_agents():
    from src.agents import Agents

    return Agents()


def _build_gmail_client() -> GmailClientProtocol:
    settings = get_settings()
    if not settings.gmail.enabled:
        from src.tools.null_gmail_client import NullGmailClient

        return NullGmailClient()

    from src.tools.gmail_client import GmailApiClient

    return GmailApiClient()


def _build_knowledge_provider() -> KnowledgeProviderProtocol:
    from src.tools.knowledge_provider import LocalKnowledgeProvider

    return LocalKnowledgeProvider()


def _build_policy_provider() -> PolicyProviderProtocol:
    from src.tools.policy_provider import StaticPolicyProvider

    return StaticPolicyProvider()


def _build_ticket_store() -> TicketStoreProtocol:
    from src.tools.ticket_store import SqlAlchemyTicketStore

    return SqlAlchemyTicketStore()


@dataclass
class ServiceContainer:
    agents_factory: Callable[[], object] = _build_agents
    gmail_client_factory: Callable[[], GmailClientProtocol] = _build_gmail_client
    knowledge_provider_factory: Callable[
        [],
        KnowledgeProviderProtocol,
    ] = _build_knowledge_provider
    policy_provider_factory: Callable[[], PolicyProviderProtocol] = _build_policy_provider
    ticket_store_factory: Callable[[], TicketStoreProtocol] = _build_ticket_store
    _gmail_client: GmailClientProtocol | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _knowledge_provider: KnowledgeProviderProtocol | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _policy_provider: PolicyProviderProtocol | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _ticket_store: TicketStoreProtocol | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _agents: object | None = field(
        default=None,
        init=False,
        repr=False,
    )

    @property
    def agents(self):
        if self._agents is None:
            self._agents = self.agents_factory()
        return self._agents

    @property
    def gmail_client(self) -> GmailClientProtocol:
        if self._gmail_client is None:
            self._gmail_client = self.gmail_client_factory()
        return self._gmail_client

    @property
    def knowledge_provider(self) -> KnowledgeProviderProtocol:
        if self._knowledge_provider is None:
            self._knowledge_provider = self.knowledge_provider_factory()
        return self._knowledge_provider

    @property
    def policy_provider(self) -> PolicyProviderProtocol:
        if self._policy_provider is None:
            self._policy_provider = self.policy_provider_factory()
        return self._policy_provider

    @property
    def ticket_store(self) -> TicketStoreProtocol:
        if self._ticket_store is None:
            self._ticket_store = self.ticket_store_factory()
        return self._ticket_store


def create_default_service_container() -> ServiceContainer:
    return ServiceContainer()


@lru_cache(maxsize=1)
def get_service_container() -> ServiceContainer:
    return create_default_service_container()
