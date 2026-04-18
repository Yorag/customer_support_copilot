from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterable

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_GMAIL_SCOPES = ("https://www.googleapis.com/auth/gmail.modify",)
RUNTIME_REQUIRED_SETTINGS = ("MY_EMAIL", "LLM_API_KEY",)
INDEX_REQUIRED_SETTINGS = ("EMBEDDING_API_URL", "EMBEDDING_MODEL")


class SettingsError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class GmailSettings:
    enabled: bool
    my_email: str | None
    credentials_path: Path
    token_path: Path
    scopes: tuple[str, ...]
    inbox_lookback_hours: int
    default_fetch_limit: int


@dataclass(frozen=True)
class LLMSettings:
    api_key: str | None
    base_url: str | None
    chat_model: str
    judge_enabled: bool
    judge_model: str
    judge_timeout_seconds: int


@dataclass(frozen=True)
class EmbeddingSettings:
    api_url: str | None
    api_key: str | None
    model: str
    timeout_seconds: int
    api_key_header: str
    api_key_prefix: str


@dataclass(frozen=True)
class KnowledgeSettings:
    source_document_path: Path
    chroma_persist_directory: Path
    retriever_k: int


@dataclass(frozen=True)
class DatabaseSettings:
    url: str | None
    host: str
    port: int
    name: str
    user: str
    password: str | None

    @property
    def dsn(self) -> str:
        if self.url:
            if self.url.startswith("postgresql://"):
                return self.url.replace("postgresql://", "postgresql+psycopg://", 1)
            return self.url

        password_part = f":{self.password}" if self.password else ""
        return (
            f"postgresql+psycopg://{self.user}{password_part}"
            f"@{self.host}:{self.port}/{self.name}"
        )

    @property
    def checkpoint_conn_string(self) -> str:
        if self.url:
            if self.url.startswith("postgresql+psycopg://"):
                return self.url.replace("postgresql+psycopg://", "postgresql://", 1)
            return self.url

        password_part = f":{self.password}" if self.password else ""
        return f"postgresql://{self.user}{password_part}@{self.host}:{self.port}/{self.name}"


@dataclass(frozen=True)
class LangSmithSettings:
    tracing_enabled: bool
    api_key: str | None
    project: str
    endpoint: str


@dataclass(frozen=True)
class ApiSettings:
    host: str
    port: int
    cors_allow_origins: list[str]
    title: str
    version: str
    description: str


@dataclass(frozen=True)
class AppSettings:
    graph_recursion_limit: int


@dataclass(frozen=True)
class Settings:
    project_root: Path
    gmail: GmailSettings
    llm: LLMSettings
    embedding: EmbeddingSettings
    knowledge: KnowledgeSettings
    database: DatabaseSettings
    langsmith: LangSmithSettings
    api: ApiSettings
    app: AppSettings


def _load_env_file() -> None:
    load_dotenv(PROJECT_ROOT / ".env", override=False)


def _clean_env_value(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None

    value = value.strip()
    return value or None


def _get_int_env(name: str, default: int) -> int:
    value = _clean_env_value(name)
    if value is None:
        return default

    try:
        return int(value)
    except ValueError as exc:
        raise SettingsError(f"Setting `{name}` must be an integer.") from exc


def _get_bool_env(name: str, default: bool) -> bool:
    value = _clean_env_value(name)
    if value is None:
        return default

    lowered = value.lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False

    raise SettingsError(f"Setting `{name}` must be a boolean.")


def _get_list_env(name: str, default: list[str]) -> list[str]:
    value = _clean_env_value(name)
    if value is None:
        return list(default)

    items = [item.strip() for item in value.split(",") if item.strip()]
    return items or list(default)


def _resolve_path(value: str | None, default: Path) -> Path:
    candidate = Path(value) if value else default
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate

    return candidate.resolve()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_env_file()

    return Settings(
        project_root=PROJECT_ROOT,
        gmail=GmailSettings(
            enabled=_get_bool_env("GMAIL_ENABLED", True),
            my_email=_clean_env_value("MY_EMAIL"),
            credentials_path=_resolve_path(
                _clean_env_value("GMAIL_CREDENTIALS_PATH"),
                PROJECT_ROOT / "credentials.json",
            ),
            token_path=_resolve_path(
                _clean_env_value("GMAIL_TOKEN_PATH"),
                PROJECT_ROOT / "token.json",
            ),
            scopes=DEFAULT_GMAIL_SCOPES,
            inbox_lookback_hours=_get_int_env("GMAIL_INBOX_LOOKBACK_HOURS", 8),
            default_fetch_limit=_get_int_env("GMAIL_DEFAULT_FETCH_LIMIT", 50),
        ),
        llm=LLMSettings(
            api_key=_clean_env_value("LLM_API_KEY"),
            base_url=_clean_env_value("LLM_BASE_URL"),
            chat_model=_clean_env_value("LLM_CHAT_MODEL") or "gpt-4o-mini",
            judge_enabled=_get_bool_env("LLM_JUDGE_ENABLED", True),
            judge_model=(
                _clean_env_value("LLM_JUDGE_MODEL")
                or _clean_env_value("LLM_CHAT_MODEL")
                or "gpt-4o-mini"
            ),
            judge_timeout_seconds=_get_int_env("LLM_JUDGE_TIMEOUT_SECONDS", 20),
        ),
        embedding=EmbeddingSettings(
            api_url=_clean_env_value("EMBEDDING_API_URL"),
            api_key=_clean_env_value("EMBEDDING_API_KEY"),
            model=(
                _clean_env_value("EMBEDDING_MODEL")
                or _clean_env_value("LLM_EMBEDDING_MODEL")
                or "text-embedding-3-small"
            ),
            timeout_seconds=_get_int_env("EMBEDDING_TIMEOUT_SECONDS", 30),
            api_key_header=_clean_env_value("EMBEDDING_API_KEY_HEADER")
            or "Authorization",
            api_key_prefix=_clean_env_value("EMBEDDING_API_KEY_PREFIX") or "Bearer",
        ),
        knowledge=KnowledgeSettings(
            source_document_path=_resolve_path(
                _clean_env_value("KNOWLEDGE_SOURCE_PATH"),
                PROJECT_ROOT / "data" / "customer_support_knowledge_zh.txt",
            ),
            chroma_persist_directory=_resolve_path(
                _clean_env_value("KNOWLEDGE_DB_PATH"),
                PROJECT_ROOT / ".artifacts" / "knowledge_db",
            ),
            retriever_k=_get_int_env("KNOWLEDGE_RETRIEVER_K", 3),
        ),
        database=DatabaseSettings(
            url=_clean_env_value("DATABASE_URL"),
            host=_clean_env_value("POSTGRES_HOST") or "localhost",
            port=_get_int_env("POSTGRES_PORT", 5432),
            name=_clean_env_value("POSTGRES_DB") or "customer_support_copilot",
            user=_clean_env_value("POSTGRES_USER") or "postgres",
            password=_clean_env_value("POSTGRES_PASSWORD"),
        ),
        langsmith=LangSmithSettings(
            tracing_enabled=_get_bool_env("LANGSMITH_TRACING", False),
            api_key=_clean_env_value("LANGSMITH_API_KEY"),
            project=_clean_env_value("LANGSMITH_PROJECT")
            or "customer-support-copilot",
            endpoint=_clean_env_value("LANGSMITH_ENDPOINT")
            or "https://api.smith.langchain.com",
        ),
        api=ApiSettings(
            host=_clean_env_value("API_HOST") or "0.0.0.0",
            port=_get_int_env("API_PORT", 8000),
            cors_allow_origins=_get_list_env("CORS_ALLOW_ORIGINS", ["*"]),
            title=_clean_env_value("API_TITLE") or "Customer Support Copilot API",
            version=_clean_env_value("API_VERSION") or "1.0",
            description=_clean_env_value("API_DESCRIPTION")
            or "Business API for the Customer Support Copilot ticket workflow",
        ),
        app=AppSettings(
            graph_recursion_limit=_get_int_env("GRAPH_RECURSION_LIMIT", 100)
        ),
    )


def validate_required_settings(required_names: Iterable[str]) -> Settings:
    settings = get_settings()
    accessors: dict[str, Callable[[Settings], object]] = {
        "MY_EMAIL": lambda current: current.gmail.my_email,
        "GMAIL_CREDENTIALS_PATH": lambda current: current.gmail.credentials_path,
        "GMAIL_TOKEN_PATH": lambda current: current.gmail.token_path,
        "LLM_API_KEY": lambda current: current.llm.api_key,
        "EMBEDDING_API_URL": lambda current: current.embedding.api_url,
        "EMBEDDING_API_KEY": lambda current: current.embedding.api_key,
        "EMBEDDING_MODEL": lambda current: current.embedding.model,
        "DATABASE_URL": lambda current: current.database.url,
        "POSTGRES_HOST": lambda current: current.database.host,
        "POSTGRES_PORT": lambda current: current.database.port,
        "POSTGRES_DB": lambda current: current.database.name,
        "POSTGRES_USER": lambda current: current.database.user,
        "LANGSMITH_API_KEY": lambda current: current.langsmith.api_key,
    }

    missing: list[str] = []
    for name in required_names:
        if name not in accessors:
            raise SettingsError(f"Unsupported required setting `{name}`.")
        value = accessors[name](settings)
        if value in (None, "", []):
            missing.append(name)

    if missing:
        missing_text = ", ".join(missing)
        raise SettingsError(f"Missing required settings: {missing_text}")

    return settings
