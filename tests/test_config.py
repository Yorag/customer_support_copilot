from __future__ import annotations

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
