from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage

from .models import build_chat_model


TOKEN_SOURCE_PROVIDER_ACTUAL = "provider_actual"
TOKEN_SOURCE_PROVIDER_MAPPED = "provider_mapped"
TOKEN_SOURCE_ESTIMATED = "estimated"
TOKEN_SOURCE_UNAVAILABLE = "unavailable"
_TOKEN_SOURCE_VALUES = {
    TOKEN_SOURCE_PROVIDER_ACTUAL,
    TOKEN_SOURCE_PROVIDER_MAPPED,
    TOKEN_SOURCE_ESTIMATED,
    TOKEN_SOURCE_UNAVAILABLE,
}


@dataclass(frozen=True)
class LlmUsage:
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    token_source: str


@dataclass(frozen=True)
class LlmInvocationResult:
    parsed_output: Any
    raw_text: str
    model: str
    provider: str
    usage: LlmUsage
    request_id: str | None
    finish_reason: str | None


class LlmRuntime:
    def __init__(self, *, temperature: float = 0.1) -> None:
        self._model = build_chat_model(temperature=temperature)
        self._model_name = getattr(self._model, "model_name", None) or getattr(
            self._model, "model", "unknown"
        )
        self._provider = "openai-compatible"

    @property
    def model_name(self) -> str:
        return str(self._model_name)

    @property
    def provider(self) -> str:
        return self._provider

    def invoke_structured(
        self,
        prompt,
        *,
        schema,
        inputs: Any,
    ) -> LlmInvocationResult:
        runnable = prompt | self._model.with_structured_output(schema, include_raw=True)
        response = runnable.invoke(inputs)
        parsed_output = response["parsed"]
        parsing_error = response.get("parsing_error")
        raw_message = response.get("raw")
        raw_text = _extract_raw_text(raw_message)
        _raise_if_missing_structured_output(
            parsed_output=parsed_output,
            parsing_error=parsing_error,
            raw_text=raw_text,
        )
        usage = extract_usage(
            raw_message,
            prompt_texts=_collect_prompt_texts(inputs),
            completion_text=raw_text,
        )
        return LlmInvocationResult(
            parsed_output=parsed_output,
            raw_text=raw_text,
            model=self.model_name,
            provider=self.provider,
            usage=usage,
            request_id=_extract_request_id(raw_message),
            finish_reason=_extract_finish_reason(raw_message),
        )

    def invoke_structured_text(
        self,
        text: str,
        *,
        schema,
    ) -> LlmInvocationResult:
        runnable = self._model.with_structured_output(schema, include_raw=True)
        response = runnable.invoke(text)
        parsed_output = response["parsed"]
        parsing_error = response.get("parsing_error")
        raw_message = response.get("raw")
        raw_text = _extract_raw_text(raw_message)
        _raise_if_missing_structured_output(
            parsed_output=parsed_output,
            parsing_error=parsing_error,
            raw_text=raw_text,
        )
        usage = extract_usage(
            raw_message,
            prompt_texts=[text],
            completion_text=raw_text,
        )
        return LlmInvocationResult(
            parsed_output=parsed_output,
            raw_text=raw_text,
            model=self.model_name,
            provider=self.provider,
            usage=usage,
            request_id=_extract_request_id(raw_message),
            finish_reason=_extract_finish_reason(raw_message),
        )


def extract_usage(
    response: Any,
    *,
    prompt_texts: list[str] | None = None,
    completion_text: str | None = None,
) -> LlmUsage:
    usage = _extract_provider_usage(response)
    if usage is not None:
        return usage

    usage = _extract_mapped_usage(response)
    if usage is not None:
        return usage

    prompt_payloads = prompt_texts or []
    completion_payload = completion_text or ""
    if prompt_payloads or completion_payload:
        prompt_tokens = sum(
            _estimate_token_usage(text=text, multiplier=1.2) for text in prompt_payloads if text
        )
        completion_tokens = _estimate_token_usage(text=completion_payload, multiplier=1.1)
        total_tokens = prompt_tokens + completion_tokens
        return LlmUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            token_source=TOKEN_SOURCE_ESTIMATED,
        )

    return LlmUsage(
        prompt_tokens=None,
        completion_tokens=None,
        total_tokens=None,
        token_source=TOKEN_SOURCE_UNAVAILABLE,
    )


def _extract_provider_usage(response: Any) -> LlmUsage | None:
    if isinstance(response, AIMessage) and response.usage_metadata:
        metadata = dict(response.usage_metadata)
        prompt_tokens = _as_int(
            metadata.get("input_tokens") or metadata.get("prompt_tokens")
        )
        completion_tokens = _as_int(
            metadata.get("output_tokens") or metadata.get("completion_tokens")
        )
        total_tokens = _sum_tokens(prompt_tokens, completion_tokens)
        if total_tokens is None:
            total_tokens = _as_int(metadata.get("total_tokens"))
        if prompt_tokens is not None and completion_tokens is not None and total_tokens is not None:
            return LlmUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                token_source=TOKEN_SOURCE_PROVIDER_ACTUAL,
            )
    return None


def _extract_mapped_usage(response: Any) -> LlmUsage | None:
    metadata = {}
    if isinstance(response, AIMessage):
        metadata = dict(response.response_metadata or {})
    elif isinstance(response, dict):
        metadata = dict(response)
    usage_payload = _find_usage_payload(metadata)
    if not isinstance(usage_payload, dict):
        return None
    prompt_tokens = _as_int(
        usage_payload.get("prompt_tokens") or usage_payload.get("input_tokens")
    )
    completion_tokens = _as_int(
        usage_payload.get("completion_tokens") or usage_payload.get("output_tokens")
    )
    total_tokens = _sum_tokens(prompt_tokens, completion_tokens)
    if total_tokens is None:
        total_tokens = _as_int(usage_payload.get("total_tokens"))
    if prompt_tokens is None or completion_tokens is None or total_tokens is None:
        return None
    return LlmUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        token_source=TOKEN_SOURCE_PROVIDER_MAPPED,
    )


def _find_usage_payload(metadata: dict[str, Any]) -> dict[str, Any] | None:
    candidates = (
        metadata.get("usage"),
        metadata.get("token_usage"),
        metadata.get("usage_metadata"),
    )
    for candidate in candidates:
        if isinstance(candidate, dict):
            return candidate
    return None


def _extract_request_id(response: Any) -> str | None:
    if isinstance(response, AIMessage):
        metadata = dict(response.response_metadata or {})
        for key in ("request_id", "x_request_id"):
            value = metadata.get(key)
            if value:
                return str(value)
    return None


def _extract_finish_reason(response: Any) -> str | None:
    if isinstance(response, AIMessage):
        metadata = dict(response.response_metadata or {})
        value = metadata.get("finish_reason")
        if value is not None:
            return str(value)
    return None


def _extract_raw_text(response: Any) -> str:
    if isinstance(response, AIMessage):
        content = response.content
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            texts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    texts.append(item)
                elif isinstance(item, dict) and isinstance(item.get("text"), str):
                    texts.append(item["text"])
            return "\n".join(texts).strip()
    if response is None:
        return ""
    return str(response)


def _raise_if_missing_structured_output(
    *,
    parsed_output: Any,
    parsing_error: Any,
    raw_text: str,
) -> None:
    if parsed_output is not None:
        return
    if isinstance(parsing_error, Exception):
        raise parsing_error

    detail = str(parsing_error).strip() if parsing_error is not None else "parsed output is null"
    suffix = f" Raw text: {raw_text}" if raw_text else ""
    raise ValueError(f"Structured output parsing failed: {detail}.{suffix}")


def _collect_prompt_texts(inputs: Any) -> list[str]:
    if isinstance(inputs, str):
        return [inputs]
    if isinstance(inputs, dict):
        texts: list[str] = []
        for value in inputs.values():
            if isinstance(value, str):
                texts.append(value)
            elif isinstance(value, list):
                texts.extend(str(item) for item in value if isinstance(item, str))
        return texts
    return [str(inputs)] if inputs is not None else []


def _sum_tokens(
    prompt_tokens: int | None,
    completion_tokens: int | None,
) -> int | None:
    if prompt_tokens is None or completion_tokens is None:
        return None
    return prompt_tokens + completion_tokens


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _estimate_token_usage(*, text: str, multiplier: float = 1.0) -> int:
    normalized = (text or "").strip()
    if not normalized:
        return 0
    return max(1, int(len(normalized.split()) * multiplier))


def normalize_usage_payload(usage: LlmUsage) -> dict[str, Any]:
    if usage.token_source not in _TOKEN_SOURCE_VALUES:
        raise ValueError(f"Unsupported token_source `{usage.token_source}`.")
    return {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "total_tokens": usage.total_tokens,
        "token_source": usage.token_source,
    }


__all__ = [
    "TOKEN_SOURCE_ESTIMATED",
    "TOKEN_SOURCE_PROVIDER_ACTUAL",
    "TOKEN_SOURCE_PROVIDER_MAPPED",
    "TOKEN_SOURCE_UNAVAILABLE",
    "LlmInvocationResult",
    "LlmRuntime",
    "LlmUsage",
    "extract_usage",
    "normalize_usage_payload",
]
