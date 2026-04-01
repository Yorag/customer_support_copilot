from __future__ import annotations

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from src.config import get_settings


def build_chat_model(*, temperature: float = 0.1) -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        api_key=settings.llm.api_key,
        base_url=settings.llm.base_url,
        model=settings.llm.chat_model,
        temperature=temperature,
    )


def build_embedding_model() -> OpenAIEmbeddings:
    settings = get_settings()
    return OpenAIEmbeddings(
        api_key=settings.llm.api_key,
        base_url=settings.llm.base_url,
        model=settings.llm.embedding_model,
    )
