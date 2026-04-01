from __future__ import annotations

from typing import Sequence

from langchain_chroma import Chroma
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough

from src.config import get_settings
from src.llm import build_chat_model, build_embedding_model
from src.tools.types import KnowledgeAnswer, KnowledgeProviderProtocol


RAG_SEARCH_PROMPT_TEMPLATE = """
Using the following pieces of retrieved context, answer the question comprehensively and concisely.
Ensure your response fully addresses the question based on the given context.

IMPORTANT:
Just provide the answer and never mention or refer to having access to the external context or information in your answer.
If you are unable to determine the answer from the provided context, state 'I don't know.'

Question: {question}
Context: {context}
"""


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
        prompt = ChatPromptTemplate.from_template(RAG_SEARCH_PROMPT_TEMPLATE)

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


class McpKnowledgeProvider(KnowledgeProviderProtocol):
    """Reserved interface for future external knowledge integration."""

    def answer_question(self, question: str) -> str:
        raise NotImplementedError("MCP knowledge provider is not implemented in V1.")

    def answer_questions(
        self,
        questions: Sequence[str],
    ) -> list[KnowledgeAnswer]:
        raise NotImplementedError("MCP knowledge provider is not implemented in V1.")
