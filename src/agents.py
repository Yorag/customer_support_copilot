from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder, PromptTemplate

from .llm import build_chat_model
from .prompts import *
from .structure_outputs import *
from .triage import TriageContext, TriageDecisionService


class Agents:
    def __init__(self, *, triage_service: TriageDecisionService | None = None):
        llm = build_chat_model(temperature=0.1)
        self.triage_service = triage_service or TriageDecisionService()

        email_category_prompt = PromptTemplate(
            template=CATEGORIZE_EMAIL_PROMPT,
            input_variables=["email"],
        )
        self.categorize_email = (
            email_category_prompt
            | llm.with_structured_output(CategorizeEmailOutput)
        )

        triage_prompt = PromptTemplate(
            template=TRIAGE_EMAIL_PROMPT,
            input_variables=["subject", "email"],
        )
        self.triage_email = triage_prompt | llm.with_structured_output(TriageOutput)

        generate_query_prompt = PromptTemplate(
            template=GENERATE_RAG_QUERIES_PROMPT,
            input_variables=["email"],
        )
        self.design_rag_queries = (
            generate_query_prompt
            | llm.with_structured_output(RAGQueriesOutput)
        )

        writer_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", EMAIL_WRITER_PROMPT),
                MessagesPlaceholder("history"),
                ("human", "{email_information}"),
            ]
        )
        self.email_writer = (
            writer_prompt
            | llm.with_structured_output(WriterOutput)
        )

        proofreader_prompt = PromptTemplate(
            template=EMAIL_PROOFREADER_PROMPT,
            input_variables=["initial_email", "generated_email"],
        )
        self.email_proofreader = (
            proofreader_prompt
            | llm.with_structured_output(ProofReaderOutput)
        )

    def triage_email_with_rules(
        self,
        *,
        subject: str | None,
        email: str,
        context: TriageContext | None = None,
    ):
        return self.triage_service.evaluate(
            subject=subject,
            body=email,
            context=context,
        )
