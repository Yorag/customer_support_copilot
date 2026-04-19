from __future__ import annotations

import json
from dataclasses import dataclass

from langchain_core.prompts import PromptTemplate

from src.contracts.outputs import MemoryExtractionOutput
from src.llm.runtime import LlmInvocationResult, LlmRuntime
from src.prompts.loader import load_prompt_template


@dataclass(frozen=True)
class MemoryExtractionCandidate:
    output: MemoryExtractionOutput
    llm_invocation: LlmInvocationResult | None
    fallback_used: bool


class LlmMemoryExtractor:
    def __init__(self, *, runtime: LlmRuntime | None = None) -> None:
        self._runtime = runtime or LlmRuntime(temperature=0.0)

    def extract(self, *, case_context: dict[str, object]) -> MemoryExtractionCandidate:
        try:
            invocation = self._runtime.invoke_structured(
                PromptTemplate(
                    template=load_prompt_template("memory_extraction.txt"),
                    input_variables=["case_context_json"],
                ),
                schema=MemoryExtractionOutput,
                inputs={
                    "case_context_json": json.dumps(
                        case_context,
                        ensure_ascii=True,
                        sort_keys=True,
                        default=str,
                    )
                },
            )
        except Exception:
            return MemoryExtractionCandidate(
                output=MemoryExtractionOutput(),
                llm_invocation=None,
                fallback_used=True,
            )

        return MemoryExtractionCandidate(
            output=invocation.parsed_output,
            llm_invocation=invocation,
            fallback_used=False,
        )


__all__ = [
    "LlmMemoryExtractor",
    "MemoryExtractionCandidate",
]
