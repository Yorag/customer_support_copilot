from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass(frozen=True)
class KnowledgeAnswer:
    question: str
    answer: str


class KnowledgeProviderProtocol(Protocol):
    def answer_question(self, question: str) -> str:
        ...

    def answer_questions(
        self,
        questions: Sequence[str],
    ) -> list[KnowledgeAnswer]:
        ...


__all__ = ["KnowledgeAnswer", "KnowledgeProviderProtocol"]
