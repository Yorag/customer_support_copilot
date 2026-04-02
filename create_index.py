from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from src.config import INDEX_REQUIRED_SETTINGS, validate_required_settings
from src.llm import build_chat_model, build_embedding_model

RAG_SEARCH_PROMPT_TEMPLATE = """
Using the following pieces of retrieved context, answer the question comprehensively and concisely.
Ensure your response fully addresses the question based on the given context.

**IMPORTANT:**
Just provide the answer and never mention or refer to having access to the external context or information in your answer.
If you are unable to determine the answer from the provided context, state 'I don't know.'

Question: {question}
Context: {context}
"""

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
    prompt = ChatPromptTemplate.from_template(RAG_SEARCH_PROMPT_TEMPLATE)
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

