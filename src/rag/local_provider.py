from __future__ import annotations

from typing import Sequence

from langchain_chroma import Chroma
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough

from src.config import get_settings
from src.llm.models import build_chat_model, build_embedding_model
from src.prompts.loader import load_prompt_template
from src.rag.provider import KnowledgeAnswer, KnowledgeProviderProtocol


class LocalKnowledgeProvider(KnowledgeProviderProtocol):
    def __init__(self) -> None:
        settings = get_settings()
        embeddings = build_embedding_model()
        vectorstore = Chroma(
            persist_directory=str(settings.knowledge.chroma_persist_directory),
            embedding_function=embeddings,
        )
        retriever = vectorstore.as_retriever(
            search_kwargs={"k": settings.knowledge.retriever_k}
        )
        llm = build_chat_model(temperature=0.1)
        prompt = ChatPromptTemplate.from_template(
            load_prompt_template("rag_search.txt")
        )

        self._qa_chain = (
            {"context": retriever, "question": RunnablePassthrough()}
            | prompt
            | llm
            | StrOutputParser()
        )

    def answer_question(self, question: str) -> str:
        return self._qa_chain.invoke(question)

    def answer_questions(
        self,
        questions: Sequence[str],
    ) -> list[KnowledgeAnswer]:
        return [
            KnowledgeAnswer(question=question, answer=self.answer_question(question))
            for question in questions
        ]


__all__ = ["LocalKnowledgeProvider"]
