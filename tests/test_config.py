from __future__ import annotations

from src.config import get_settings
from src.config import DatabaseSettings, EmbeddingSettings, LLMSettings


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
        judge_model="openai/gpt-4o-mini",
        judge_timeout_seconds=20,
    )

    assert settings.api_key == "test-key"
    assert settings.base_url == "https://openrouter.ai/api/v1"
    assert settings.chat_model == "openai/gpt-4o-mini"
    assert settings.judge_model == "openai/gpt-4o-mini"
    assert settings.judge_timeout_seconds == 20


def test_embedding_settings_support_dedicated_endpoint_configuration():
    settings = EmbeddingSettings(
        api_url="https://embedding.example.com/v1/embeddings",
        api_key="embed-key",
        model="bge-large-zh-v1.5",
        timeout_seconds=20,
        api_key_header="Authorization",
        api_key_prefix="Bearer",
    )

    assert settings.api_url == "https://embedding.example.com/v1/embeddings"
    assert settings.api_key == "embed-key"
    assert settings.model == "bge-large-zh-v1.5"
    assert settings.timeout_seconds == 20


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


def test_gmail_can_be_explicitly_disabled(monkeypatch):
    monkeypatch.setenv("GMAIL_ENABLED", "false")
    get_settings.cache_clear()

    try:
        settings = get_settings()
        assert settings.gmail.enabled is False
    finally:
        get_settings.cache_clear()


def test_judge_settings_default_to_chat_model(monkeypatch):
    monkeypatch.setenv("LLM_CHAT_MODEL", "test-chat-model")
    monkeypatch.setenv("LLM_JUDGE_MODEL", "")
    monkeypatch.setenv("LLM_JUDGE_TIMEOUT_SECONDS", "45")
    get_settings.cache_clear()

    try:
        settings = get_settings()
        assert settings.llm.judge_model == "test-chat-model"
        assert settings.llm.judge_timeout_seconds == 45
    finally:
        get_settings.cache_clear()
