"""Lesson 7 - the three escape hatches you have to write yourself.

LangChain replaces almost every piece of Lesson 1 with a component you can import.
Almost. Three things it cannot know about are *your* provider, *your* embeddings,
and *your* retriever - so you subclass its base classes and hand it your own.

That is the honest shape of every framework: a wide catalogue of components, plus
a small number of base classes you extend when the catalogue does not fit. Having
written the primitives in Lesson 1, none of this is mysterious.

  LocalRagChatModel     <- SimpleChatModel   wraps localrag.providers.get_provider
  LocalRagEmbeddings    <- Embeddings        wraps localrag.providers.embed_texts
  LocalRagBM25Retriever <- BaseRetriever     wraps rank_bm25 over LangChain Documents

The chat model matters most: the course's default provider is the Claude Code CLI,
which LangChain has no adapter for. Sixty lines here and every LCEL chain in the
ecosystem can drive it.
"""

from __future__ import annotations

import re
from typing import Any, List, Optional

from handrolled_pipeline import Config  # noqa: F401  (re-exported for callers)
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.language_models.chat_models import SimpleChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.retrievers import BaseRetriever

from localrag.providers import embed_texts, get_provider


def _truncate_at_stop(text: str, stop: Optional[List[str]]) -> str:
    """Enforce LangChain's `stop` contract on providers that have no stop parameter.

    A caller can pass stop sequences to any chat model and expect output to end at
    the first one. None of Lesson 1's providers take a stop argument, so honour it
    here by cutting the response - silently ignoring `stop` would hand the caller
    text they explicitly asked not to receive.
    """
    if not stop:
        return text
    cut = len(text)
    for sequence in stop:
        if not sequence:
            continue
        found = text.find(sequence)
        if found != -1:
            cut = min(cut, found)
    return text[:cut]


class LocalRagChatModel(SimpleChatModel):
    """Drive any localrag provider (claude / ollama / gemini / openai) from an LCEL chain.

    `SimpleChatModel` asks for exactly one method: turn a list of messages into a
    string. Everything else - streaming, batching, callbacks, `|` composition -
    LangChain supplies once this exists.
    """

    config: Any
    provider_name: str = "claude"

    @property
    def _llm_type(self) -> str:
        return f"localrag-{self.provider_name}"

    def _call(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> str:
        system = "\n".join(str(m.content) for m in messages if isinstance(m, SystemMessage))
        user = "\n".join(str(m.content) for m in messages if isinstance(m, HumanMessage))
        text = get_provider(self.provider_name, self.config).chat(system, user)
        return _truncate_at_stop(text, stop)


class LocalRagEmbeddings(Embeddings):
    """Expose localrag's embedding providers through LangChain's `Embeddings` interface.

    Note what this cannot do: the Claude Code provider has no embedding endpoint, so
    asking it to embed raises `EmbeddingError`. That limit is a property of the
    provider, not of the wrapper - exactly as it was in Lesson 1.
    """

    def __init__(self, config: Any, provider_name: str = "ollama") -> None:
        self.config = config
        self.provider_name = provider_name

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return embed_texts(self.provider_name, self.config, list(texts))

    def embed_query(self, text: str) -> List[float]:
        return self.embed_documents([text])[0]


def _tokenize(text: str) -> List[str]:
    """The same tokenizer Lesson 1 uses, so the two BM25 arms differ only in their input."""
    return re.findall(r"[a-z0-9]+", text.lower())


class LocalRagBM25Retriever(BaseRetriever):
    """BM25 over LangChain `Document`s, using rank_bm25 - already a course dependency.

    LangChain shipped a `BM25Retriever` in `langchain-community`, but that package is
    now sunset. Twenty lines against `BaseRetriever` removes the dependency, the
    deprecation warning, and the migration you would otherwise be doing next year.
    """

    documents: List[Document]
    k: int = 3

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        from rank_bm25 import BM25Okapi

        if not self.documents or self.k <= 0:
            return []
        bm25 = BM25Okapi([_tokenize(d.page_content) for d in self.documents])
        scores = bm25.get_scores(_tokenize(query))
        ranked = sorted(range(len(self.documents)), key=lambda i: scores[i], reverse=True)[: self.k]
        if scores[ranked[0]] <= 0:
            return [self.documents[i] for i in ranked]
        return [self.documents[i] for i in ranked if scores[i] > 0]
