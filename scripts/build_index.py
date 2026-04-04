from __future__ import annotations

import sys
from pathlib import Path

from langchain_chroma import Chroma
from langchain_community.document_loaders import TextLoader
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_text_splitters import RecursiveCharacterTextSplitter


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import INDEX_REQUIRED_SETTINGS, validate_required_settings
from src.llm import build_chat_model, build_embedding_model
from src.prompts.loader import load_prompt_template


def main() -> None:
    settings = validate_required_settings(INDEX_REQUIRED_SETTINGS)

    print("Loading & Chunking Docs...")
    loader = TextLoader(str(settings.knowledge.source_document_path), encoding="utf-8")
    docs = loader.load()

    doc_splitter = RecursiveCharacterTextSplitter(chunk_size=300, chunk_overlap=50)
    doc_chunks = doc_splitter.split_documents(docs)

    print("Creating vector embeddings...")
    embeddings = build_embedding_model()

    vectorstore = Chroma.from_documents(
        doc_chunks,
        embeddings,
        persist_directory=str(settings.knowledge.chroma_persist_directory),
    )

    vectorstore_retriever = vectorstore.as_retriever(
        search_kwargs={"k": settings.knowledge.retriever_k}
    )

    print("Test RAG chain...")
    prompt = ChatPromptTemplate.from_template(load_prompt_template("rag_search.txt"))
    llm = build_chat_model(temperature=0.1)

    rag_chain = (
        {"context": vectorstore_retriever, "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )

    query = "What are your pricing options?"
    result = rag_chain.invoke(query)
    print(f"Question: {query}")
    print(f"Answer: {result}")


if __name__ == "__main__":
    main()
