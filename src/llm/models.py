from __future__ import annotations

from typing import cast

import requests
from langchain_core.embeddings import Embeddings
from langchain_openai import ChatOpenAI

from src.config import get_settings


def build_chat_model(*, temperature: float = 0.1) -> ChatOpenAI:
    settings = get_settings()
    return ChatOpenAI(
        api_key=settings.llm.api_key,
        base_url=settings.llm.base_url,
        model=settings.llm.chat_model,
        temperature=temperature,
    )


class HttpEmbeddingClient(Embeddings):
    def __init__(self) -> None:
        settings = get_settings()
        self._api_url = settings.embedding.api_url
        self._api_key = settings.embedding.api_key
        self._model = settings.embedding.model
        self._timeout_seconds = settings.embedding.timeout_seconds
        self._api_key_header = settings.embedding.api_key_header
        self._api_key_prefix = settings.embedding.api_key_prefix

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_single(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed_single(text)

    def _embed_single(self, text: str) -> list[float]:
        if not self._api_url:
            raise ValueError("EMBEDDING_API_URL is required to build the embedding client.")

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            prefix = f"{self._api_key_prefix} " if self._api_key_prefix else ""
            headers[self._api_key_header] = f"{prefix}{self._api_key}".strip()

        response = requests.post(
            self._api_url,
            headers=headers,
            json={"model": self._model, "input": text},
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        return extract_embedding_vector(response.json())


def extract_embedding_vector(payload: dict) -> list[float]:
    if isinstance(payload.get("embedding"), list):
        return cast(list[float], payload["embedding"])

    data = payload.get("data")
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict) and isinstance(first.get("embedding"), list):
            return cast(list[float], first["embedding"])

    raise ValueError("Embedding response did not contain a supported embedding vector.")


def build_embedding_model() -> Embeddings:
    settings = get_settings()
    if not settings.embedding.api_url:
        raise ValueError("EMBEDDING_API_URL is required.")
    return HttpEmbeddingClient()


__all__ = [
    "HttpEmbeddingClient",
    "extract_embedding_vector",
    "build_chat_model",
    "build_embedding_model",
]
