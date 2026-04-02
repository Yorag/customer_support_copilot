from __future__ import annotations

from src.config import get_settings
from src.tools.service_container import ServiceContainer
from src.tools.service_container import create_default_service_container


def test_service_container_caches_provider_instances():
    calls = {
        "agents": 0,
        "gmail": 0,
        "knowledge": 0,
        "policy": 0,
        "ticket": 0,
    }

    container = ServiceContainer(
        agents_factory=lambda: calls.__setitem__("agents", calls["agents"] + 1) or object(),
        gmail_client_factory=lambda: calls.__setitem__("gmail", calls["gmail"] + 1) or object(),
        knowledge_provider_factory=lambda: calls.__setitem__("knowledge", calls["knowledge"] + 1) or object(),
        policy_provider_factory=lambda: calls.__setitem__("policy", calls["policy"] + 1) or object(),
        ticket_store_factory=lambda: calls.__setitem__("ticket", calls["ticket"] + 1) or object(),
    )

    assert container.agents is container.agents
    assert container.gmail_client is container.gmail_client
    assert container.knowledge_provider is container.knowledge_provider
    assert container.policy_provider is container.policy_provider
    assert container.ticket_store is container.ticket_store
    assert calls == {"agents": 1, "gmail": 1, "knowledge": 1, "policy": 1, "ticket": 1}


def test_service_container_uses_null_gmail_client_when_disabled(monkeypatch):
    monkeypatch.setenv("GMAIL_ENABLED", "false")
    get_settings.cache_clear()

    try:
        container = create_default_service_container()
        gmail_client = container.gmail_client
        assert gmail_client.__class__.__name__ == "NullGmailClient"
        assert gmail_client.fetch_unanswered_emails() == []
        assert gmail_client.create_draft_reply(type("Email", (), {"messageId": "m1"})(), "hi") == {
            "id": "local-draft:m1"
        }
    finally:
        get_settings.cache_clear()
