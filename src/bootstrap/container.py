from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Callable, TypeVar

from src.config import get_settings
from src.rag.provider import KnowledgeProviderProtocol
from src.contracts.protocols import (
    GmailClientProtocol,
    MemoryExtractorProtocol,
    PolicyProviderProtocol,
    TicketStoreProtocol,
    TraceExporterProtocol,
)

T = TypeVar("T")


def _build_agents():
    from src.agents import Agents

    return Agents()


def _build_response_quality_judge():
    settings = get_settings()
    if not settings.llm.judge_enabled:
        return None

    from src.evaluation import ResponseQualityJudge

    return ResponseQualityJudge()


def _build_gmail_client() -> GmailClientProtocol:
    settings = get_settings()
    if not settings.gmail.enabled:
        from src.tools.null_gmail_client import NullGmailClient

        return NullGmailClient()

    from src.tools.gmail_client import GmailApiClient

    return GmailApiClient()


def _build_knowledge_provider() -> KnowledgeProviderProtocol:
    from src.rag.local_provider import LocalKnowledgeProvider

    return LocalKnowledgeProvider()


def _build_policy_provider() -> PolicyProviderProtocol:
    from src.tools.policy_provider import StaticPolicyProvider

    return StaticPolicyProvider()


def _build_ticket_store() -> TicketStoreProtocol:
    from src.tools.ticket_store import SqlAlchemyTicketStore

    return SqlAlchemyTicketStore()


def _build_checkpointer():
    from src.orchestration.checkpointing import build_default_checkpointer

    return build_default_checkpointer()


def _build_trace_exporter() -> TraceExporterProtocol:
    from src.telemetry.exporters import LangSmithTraceExporter

    return LangSmithTraceExporter()


def _build_memory_extractor() -> MemoryExtractorProtocol:
    from src.memory.extractor import LlmMemoryExtractor

    return LlmMemoryExtractor()


@dataclass
class ServiceContainer:
    agents_factory: Callable[[], object] = _build_agents
    response_quality_judge_factory: Callable[[], object] = _build_response_quality_judge
    gmail_client_factory: Callable[[], GmailClientProtocol] = _build_gmail_client
    knowledge_provider_factory: Callable[
        [],
        KnowledgeProviderProtocol,
    ] = _build_knowledge_provider
    policy_provider_factory: Callable[[], PolicyProviderProtocol] = _build_policy_provider
    ticket_store_factory: Callable[[], TicketStoreProtocol] = _build_ticket_store
    checkpointer_factory: Callable[[], object] = _build_checkpointer
    trace_exporter_factory: Callable[[], TraceExporterProtocol] = _build_trace_exporter
    memory_extractor_factory: Callable[[], MemoryExtractorProtocol] = _build_memory_extractor
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
    _response_quality_judge: object | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _checkpointer: object | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _trace_exporter: TraceExporterProtocol | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _memory_extractor: MemoryExtractorProtocol | None = field(
        default=None,
        init=False,
        repr=False,
    )

    def _get_or_create(self, attr_name: str, factory: Callable[[], T]) -> T:
        instance = getattr(self, attr_name)
        if instance is None:
            instance = factory()
            setattr(self, attr_name, instance)
        return instance

    @property
    def agents(self):
        return self._get_or_create("_agents", self.agents_factory)

    @property
    def response_quality_judge(self):
        return self._get_or_create(
            "_response_quality_judge",
            self.response_quality_judge_factory,
        )

    @property
    def gmail_client(self) -> GmailClientProtocol:
        return self._get_or_create("_gmail_client", self.gmail_client_factory)

    @property
    def gmail_enabled(self) -> bool:
        return self.gmail_client.__class__.__name__ != "NullGmailClient"

    @property
    def knowledge_provider(self) -> KnowledgeProviderProtocol:
        return self._get_or_create(
            "_knowledge_provider",
            self.knowledge_provider_factory,
        )

    @property
    def policy_provider(self) -> PolicyProviderProtocol:
        return self._get_or_create("_policy_provider", self.policy_provider_factory)

    @property
    def ticket_store(self) -> TicketStoreProtocol:
        return self._get_or_create("_ticket_store", self.ticket_store_factory)

    @property
    def checkpointer(self):
        return self._get_or_create("_checkpointer", self.checkpointer_factory)

    @property
    def trace_exporter(self) -> TraceExporterProtocol:
        return self._get_or_create("_trace_exporter", self.trace_exporter_factory)

    @property
    def memory_extractor(self) -> MemoryExtractorProtocol:
        return self._get_or_create("_memory_extractor", self.memory_extractor_factory)


def create_default_service_container() -> ServiceContainer:
    return ServiceContainer()


@lru_cache(maxsize=1)
def get_service_container() -> ServiceContainer:
    return create_default_service_container()

