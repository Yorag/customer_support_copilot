from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict

from src.contracts.core import RunFinalAction, TicketRoute, utc_now
from src.llm.judge import build_judge_chat_model
from src.llm.runtime import (
    TOKEN_SOURCE_UNAVAILABLE,
    _extract_finish_reason,
    _extract_raw_text,
    _extract_request_id,
    extract_usage,
)
from src.prompts.loader import load_prompt_template
from src.telemetry.metrics import duration_ms


@dataclass(frozen=True)
class JudgeResult:
    relevance: int
    correctness: int
    intent_alignment: int
    clarity: int
    reason: str

    @property
    def overall_score(self) -> float:
        return round(
            (
                self.relevance
                + self.correctness
                + self.intent_alignment
                + self.clarity
            )
            / 4,
            2,
        )

    def as_response_quality(self) -> dict[str, Any]:
        return {
            "overall_score": self.overall_score,
            "subscores": {
                "relevance": self.relevance,
                "correctness": self.correctness,
                "intent_alignment": self.intent_alignment,
                "clarity": self.clarity,
            },
            "reason": self.reason,
        }


class JudgeSchemaError(ValueError):
    pass


class ResponseQualityJudgeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    relevance: int
    correctness: int
    intent_alignment: int
    clarity: int
    reason: str


@dataclass(frozen=True)
class JudgeEvaluationResult:
    response_quality: dict[str, Any] | None
    llm_metadata: dict[str, Any]


def validate_judge_output(payload: dict[str, Any]) -> JudgeResult:
    required_keys = {
        "relevance",
        "correctness",
        "intent_alignment",
        "clarity",
        "reason",
    }
    actual_keys = set(payload.keys())
    if actual_keys != required_keys:
        raise JudgeSchemaError(
            "Judge output must use fixed keys "
            f"{sorted(required_keys)}, got {sorted(actual_keys)}."
        )

    numeric_fields = ("relevance", "correctness", "intent_alignment", "clarity")
    normalized: dict[str, Any] = {}
    for field in numeric_fields:
        value = payload[field]
        if not isinstance(value, int) or value < 1 or value > 5:
            raise JudgeSchemaError(f"Judge field `{field}` must be an integer in [1, 5].")
        normalized[field] = value

    reason = str(payload["reason"]).strip()
    if not reason:
        raise JudgeSchemaError("Judge field `reason` must not be blank.")

    return JudgeResult(reason=reason, **normalized)


class RuleBasedResponseQualityBaseline:
    def evaluate(
        self,
        *,
        email_subject: str | None,
        email_body: str | None,
        draft_text: str | None,
        evidence_summary: str | None,
        policy_summary: str | None,
        primary_route: str | None,
        final_action: str | None,
    ) -> dict[str, Any]:
        draft = (draft_text or "").strip()
        body = (email_body or "").strip()
        route = primary_route or TicketRoute.UNRELATED.value
        action = final_action or RunFinalAction.NO_OP.value

        relevance = 5 if draft else 1
        correctness = 4
        intent_alignment = 4
        clarity = 4
        reasons: list[str] = []

        if not draft:
            relevance = correctness = intent_alignment = clarity = 1
            reasons.append("No customer-facing draft was produced.")
        else:
            reasons.append("Draft exists and can be evaluated against the run outcome.")

        if route == TicketRoute.COMMERCIAL_POLICY_REQUEST.value:
            correctness = (
                5 if "policy" in ((draft + " " + (policy_summary or "")).lower()) else 3
            )
            reasons.append(
                "Commercial-policy replies are checked for explicit policy boundaries."
            )
        elif (
            route == TicketRoute.TECHNICAL_ISSUE.value
            and action == RunFinalAction.REQUEST_CLARIFICATION.value
        ):
            detail_text = (draft + " " + body).lower()
            coverage = sum(
                phrase in detail_text
                for phrase in ("error", "steps", "environment", "expected")
            )
            correctness = 5 if coverage >= 3 else 4 if coverage >= 2 else 3
            intent_alignment = correctness
            reasons.append(
                "Clarification drafts are checked for required troubleshooting asks."
            )
        elif route == TicketRoute.UNRELATED.value:
            clarity = 5 if len(draft) < 240 else 4
            reasons.append(
                "Out-of-scope replies should stay concise and avoid over-committing."
            )

        if evidence_summary and route in {
            TicketRoute.KNOWLEDGE_REQUEST.value,
            TicketRoute.TECHNICAL_ISSUE.value,
        }:
            correctness = min(5, correctness + 1)
            reasons.append("Knowledge or troubleshooting evidence is available.")

        if len(draft) < 40 and draft:
            clarity = min(clarity, 3)
            reasons.append("Draft is short and may not be sufficiently clear.")

        result = validate_judge_output(
            {
                "relevance": relevance,
                "correctness": correctness,
                "intent_alignment": intent_alignment,
                "clarity": clarity,
                "reason": " ".join(reasons),
            }
        )
        return result.as_response_quality()


class ResponseQualityJudge:
    prompt_version = "response_quality_judge_v1"
    judge_name = "response_quality_judge"

    def __init__(self, *, runtime=None) -> None:
        self._runtime = runtime or _ResponseQualityJudgeRuntime()

    def evaluate(
        self,
        *,
        email_subject: str | None,
        email_body: str | None,
        draft_text: str | None,
        evidence_summary: str | None,
        policy_summary: str | None,
        primary_route: str | None,
        final_action: str | None,
    ) -> JudgeEvaluationResult:
        result = self._runtime.evaluate(
            email_subject=email_subject,
            email_body=email_body,
            draft_text=draft_text,
            evidence_summary=evidence_summary,
            policy_summary=policy_summary,
            primary_route=primary_route,
            final_action=final_action,
        )
        return JudgeEvaluationResult(
            response_quality=result["response_quality"],
            llm_metadata=result["llm_metadata"],
        )


class _ResponseQualityJudgeRuntime:
    def __init__(self) -> None:
        self._model = build_judge_chat_model()
        self._model_name = getattr(self._model, "model_name", None) or getattr(
            self._model, "model", "unknown"
        )
        self._provider = "openai-compatible"

    def evaluate(
        self,
        *,
        email_subject: str | None,
        email_body: str | None,
        draft_text: str | None,
        evidence_summary: str | None,
        policy_summary: str | None,
        primary_route: str | None,
        final_action: str | None,
    ) -> dict[str, Any]:
        prompt = self._build_prompt(
            email_subject=email_subject,
            email_body=email_body,
            draft_text=draft_text,
            evidence_summary=evidence_summary,
            policy_summary=policy_summary,
            primary_route=primary_route,
            final_action=final_action,
        )
        started_at = utc_now()
        raw_text = ""
        request_id = None
        finish_reason = None
        usage_payload = {
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "token_source": TOKEN_SOURCE_UNAVAILABLE,
        }
        last_error: Exception | None = None

        runnable = self._model.with_structured_output(
            ResponseQualityJudgeOutput,
            include_raw=True,
        )
        for _ in range(3):
            try:
                response = runnable.invoke(prompt)
                parsed_output = response["parsed"]
                raw_message = response.get("raw")
                raw_text = _extract_raw_text(raw_message)
                usage = extract_usage(
                    raw_message,
                    prompt_texts=[prompt],
                    completion_text=raw_text,
                )
                usage_payload = {
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "total_tokens": usage.total_tokens,
                    "token_source": usage.token_source,
                }
                request_id = _extract_request_id(raw_message)
                finish_reason = _extract_finish_reason(raw_message)
                judge_result = validate_judge_output(parsed_output.model_dump())
                return {
                    "response_quality": judge_result.as_response_quality(),
                    "llm_metadata": {
                        "model": str(self._model_name),
                        "provider": self._provider,
                        **usage_payload,
                        "request_id": request_id,
                        "finish_reason": finish_reason,
                        "prompt_version": ResponseQualityJudge.prompt_version,
                        "judge_name": ResponseQualityJudge.judge_name,
                        "judge_status": "succeeded",
                        "latency_ms": duration_ms(started_at, utc_now()),
                    },
                }
            except Exception as exc:
                last_error = exc

        error_message = str(last_error) if last_error is not None else "judge_failed"
        return {
            "response_quality": None,
            "llm_metadata": {
                "model": str(self._model_name),
                "provider": self._provider,
                **usage_payload,
                "request_id": request_id,
                "finish_reason": finish_reason,
                "prompt_version": ResponseQualityJudge.prompt_version,
                "judge_name": ResponseQualityJudge.judge_name,
                "judge_status": "failed",
                "error_message": error_message,
                "raw_text": raw_text or None,
                "latency_ms": duration_ms(started_at, utc_now()),
            },
        }

    def _build_prompt(
        self,
        *,
        email_subject: str | None,
        email_body: str | None,
        draft_text: str | None,
        evidence_summary: str | None,
        policy_summary: str | None,
        primary_route: str | None,
        final_action: str | None,
    ) -> str:
        prompt_template = load_prompt_template("response_quality_judge.txt")
        return prompt_template.format(
            email_subject=email_subject or "",
            email_body=email_body or "",
            draft_text=draft_text or "",
            evidence_summary=evidence_summary or "",
            policy_summary=policy_summary or "",
            primary_route=primary_route or "",
            final_action=final_action or "",
        )


__all__ = [
    "JudgeEvaluationResult",
    "JudgeResult",
    "JudgeSchemaError",
    "ResponseQualityJudge",
    "ResponseQualityJudgeOutput",
    "RuleBasedResponseQualityBaseline",
    "validate_judge_output",
]
