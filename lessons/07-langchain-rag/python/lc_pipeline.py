"""Lesson 7 - the same RAG pipeline, rebuilt on LangChain.

Read this next to `handrolled_pipeline.py`. Same corpus, same system prompt, same
citation contract, same shape - different machinery at every step:

  load     extract.py            ->  Document(page_content=..., metadata=...)
  split    chunk.py              ->  RecursiveCharacterTextSplitter
  index    store.py              ->  InMemoryVectorStore        (embedding arm only)
  retrieve retriever.py          ->  LocalRagBM25Retriever / vectorstore.as_retriever()
  prompt   prompts.py            ->  ChatPromptTemplate
  chain    engine.answer_question->  an LCEL chain composed with `|`

Two retrieval arms:
  bm25   deterministic, offline, no model - the default, and what the demo compares
  embed  real vectors via Ollama, entirely local - `--arm embed`

The system prompt is imported from `localrag.prompts`, not retyped. Both pipelines
being prompted identically is what makes the comparison mean anything.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

from handrolled_pipeline import CORPUS_DIR, SYSTEM_PROMPT
from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_text_splitters import RecursiveCharacterTextSplitter
from lc_provider import LocalRagBM25Retriever, LocalRagChatModel, LocalRagEmbeddings

NAME = "langchain"

# Mirrors localrag.prompts.build_user_prompt exactly, so neither pipeline gets a
# better brief than the other.
USER_TEMPLATE = (
    "DOCUMENT CONTEXT:\n"
    "{context}\n\n"
    "QUESTION:\n"
    "{question}\n\n"
    "Answer using the rules above, citing [filename:page] for document-based claims."
)


def load(corpus_dir: Path = CORPUS_DIR) -> List[Document]:
    """LangChain ships loaders (`PyPDFLoader`, `Docx2txtLoader`, ...), but for plain
    text a `Document` is just a string plus metadata - so build it directly and keep
    the dependency list short. `page` mirrors Lesson 1's page numbering for markdown."""
    docs: List[Document] = []
    for path in sorted(corpus_dir.rglob("*.md")):
        docs.append(
            Document(
                page_content=path.read_text(encoding="utf-8").strip(),
                metadata={"source": path.name, "page": 1},
            )
        )
    return docs


def split(docs: List[Document], size: int, overlap: int) -> List[Document]:
    """The component that replaces chunk.py - and the one that behaves differently.

    `RecursiveCharacterTextSplitter` walks separators in order ("\\n\\n", "\\n", " ", "")
    and preserves the text as written. Lesson 1's `_split_text` first collapses all
    whitespace, then breaks on sentence punctuation. Same job, different boundaries -
    which is exactly what the playground lets you watch."""
    splitter = RecursiveCharacterTextSplitter(chunk_size=size, chunk_overlap=overlap)
    return splitter.split_documents(docs)


def bm25_retriever(chunks: List[Document], k: int):
    """Our own `BaseRetriever` over rank_bm25 - see lc_provider.LocalRagBM25Retriever."""
    return LocalRagBM25Retriever(documents=chunks, k=k)


def embedding_retriever(chunks: List[Document], k: int, config, provider: str = "ollama"):
    """The framework's own store, fed by our own embeddings. Needs Ollama running."""
    from langchain_core.vectorstores import InMemoryVectorStore

    store = InMemoryVectorStore.from_documents(chunks, LocalRagEmbeddings(config, provider))
    return store.as_retriever(search_kwargs={"k": k})


def native_ollama_retriever(chunks: List[Document], k: int, model: str):
    """The same thing with no code of ours at all - `OllamaEmbeddings` off the shelf.

    Worth running once beside `embedding_retriever`: identical behaviour, one import
    instead of a class. That trade is the whole argument of this lesson."""
    from langchain_core.vectorstores import InMemoryVectorStore
    from langchain_ollama import OllamaEmbeddings

    store = InMemoryVectorStore.from_documents(chunks, OllamaEmbeddings(model=model))
    return store.as_retriever(search_kwargs={"k": k})


def sources(hits: List[Document]) -> List[str]:
    """The citation contract, unchanged from Lesson 1: `source:page`, de-duplicated."""
    seen: List[str] = []
    for d in hits:
        tag = f"{d.metadata.get('source', '?')}:{d.metadata.get('page', 1)}"
        if tag not in seen:
            seen.append(tag)
    return seen


def format_docs(docs: List[Document]) -> str:
    """Identical to localrag.prompts.build_context, over Documents instead of Chunks."""
    return "\n\n---\n\n".join(
        f"[{d.metadata.get('source', '?')}:{d.metadata.get('page', 1)}]\n{d.page_content}"
        for d in docs
    )


def prompt_template() -> ChatPromptTemplate:
    """prompts.py, as a component. The system text is Lesson 1's, imported."""
    return ChatPromptTemplate.from_messages(
        [("system", SYSTEM_PROMPT), ("human", USER_TEMPLATE)]
    )


def render_prompt(question: str, hits: List[Document]) -> tuple[str, str]:
    """Render the template to the exact strings a model would receive."""
    messages = prompt_template().format_messages(
        context=format_docs(hits) if hits else "(no relevant documents found)",
        question=question,
    )
    return str(messages[0].content), str(messages[1].content)


def build_chain(retriever, llm):
    """engine.answer_question(), as an LCEL chain.

    Read the `|` left to right: fan the question into a context lookup and a
    passthrough, render the prompt, call the model, take the text out."""
    return (
        {"context": retriever | format_docs, "question": RunnablePassthrough()}
        | prompt_template()
        | llm
        | StrOutputParser()
    )


def answer(config, question: str, retriever, provider: str = "claude") -> str:
    """The whole pipeline in one call, driven by our own chat model adapter."""
    return build_chain(retriever, LocalRagChatModel(config=config, provider_name=provider)).invoke(
        question
    )
