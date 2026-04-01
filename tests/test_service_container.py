from __future__ import annotations

from src.tools.service_container import ServiceContainer


def test_service_container_caches_provider_instances():
    calls = {
        "gmail": 0,
        "knowledge": 0,
        "policy": 0,
        "ticket": 0,
    }

    container = ServiceContainer(
        gmail_client_factory=lambda: calls.__setitem__("gmail", calls["gmail"] + 1) or object(),
        knowledge_provider_factory=lambda: calls.__setitem__("knowledge", calls["knowledge"] + 1) or object(),
        policy_provider_factory=lambda: calls.__setitem__("policy", calls["policy"] + 1) or object(),
        ticket_store_factory=lambda: calls.__setitem__("ticket", calls["ticket"] + 1) or object(),
    )

    assert container.gmail_client is container.gmail_client
    assert container.knowledge_provider is container.knowledge_provider
    assert container.policy_provider is container.policy_provider
    assert container.ticket_store is container.ticket_store
    assert calls == {"gmail": 1, "knowledge": 1, "policy": 1, "ticket": 1}
