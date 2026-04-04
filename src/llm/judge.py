from __future__ import annotations

from langchain_openai import ChatOpenAI

from src.config import get_settings


def build_judge_chat_model() -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        api_key=settings.llm.api_key,
        base_url=settings.llm.base_url,
        model=settings.llm.judge_model,
        temperature=0,
        timeout=settings.llm.judge_timeout_seconds,
    )


__all__ = ["build_judge_chat_model"]
