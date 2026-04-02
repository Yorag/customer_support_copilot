from __future__ import annotations

from src.config import get_settings
from src.config import DatabaseSettings, LLMSettings


def test_database_dsn_uses_psycopg_driver_for_postgres_url():
    settings = DatabaseSettings(
        url="postgresql://user:pass@localhost:5432/app",
        host="localhost",
        port=5432,
        name="app",
        user="user",
        password="pass",
    )

    assert settings.dsn == "postgresql+psycopg://user:pass@localhost:5432/app"


def test_database_dsn_builds_postgres_url_from_parts():
    settings = DatabaseSettings(
        url=None,
        host="db.internal",
        port=5432,
        name="copilot",
        user="postgres",
        password="secret",
    )

    assert settings.dsn == "postgresql+psycopg://postgres:secret@db.internal:5432/copilot"


def test_llm_settings_support_openai_compatible_configuration():
    settings = LLMSettings(
        api_key="test-key",
        base_url="https://openrouter.ai/api/v1",
        chat_model="openai/gpt-4o-mini",
        embedding_model="text-embedding-3-small",
    )

    assert settings.api_key == "test-key"
    assert settings.base_url == "https://openrouter.ai/api/v1"
    assert settings.chat_model == "openai/gpt-4o-mini"
    assert settings.embedding_model == "text-embedding-3-small"


def test_api_settings_defaults_match_customer_support_copilot_naming(monkeypatch):
    monkeypatch.setenv("API_TITLE", "")
    monkeypatch.setenv("API_DESCRIPTION", "")
    get_settings.cache_clear()

    try:
        settings = get_settings()
        assert settings.api.title == "Customer Support Copilot API"
        assert (
            settings.api.description
            == "Business API for the Customer Support Copilot ticket workflow"
        )
    finally:
        get_settings.cache_clear()


def test_langsmith_settings_ignore_legacy_langchain_env_vars(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "")
    monkeypatch.setenv("LANGSMITH_API_KEY", "")
    monkeypatch.setenv("LANGSMITH_ENDPOINT", "")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2", "true")
    monkeypatch.setenv("LANGCHAIN_API_KEY", "legacy-key")
    monkeypatch.setenv("LANGCHAIN_ENDPOINT", "https://legacy.example.com")
    get_settings.cache_clear()

    try:
        settings = get_settings()
        assert settings.langsmith.tracing_enabled is False
        assert settings.langsmith.api_key is None
        assert settings.langsmith.endpoint == "https://api.smith.langchain.com"
    finally:
        get_settings.cache_clear()
