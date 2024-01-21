"""Pluggable AI providers behind one small interface.

Inspired by netwise-ai's AiProvider abstraction: every provider exposes the same
``chat`` method, and embedding-capable ones also expose ``embed``. The factory
picks an implementation by name so the rest of the app never branches on provider.
"""

from __future__ import annotations

from typing import List, Protocol, runtime_checkable

from ..config import Config


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    def is_available(self) -> bool:
        ...

    def chat(self, system: str, user: str) -> str:
        ...


class EmbeddingError(RuntimeError):
    """Raised when a provider cannot produce embeddings."""


def get_provider(name: str, config: Config) -> LLMProvider:
    name = (name or "").lower()
    if name == "claude":
        from .claude_code import ClaudeCodeProvider

        return ClaudeCodeProvider(config)
    if name == "ollama":
        from .ollama import OllamaProvider

        return OllamaProvider(config)
    if name == "gemini":
        from .gemini import GeminiProvider

        return GeminiProvider(config)
    if name == "openai":
        from .openai import OpenAIProvider

        return OpenAIProvider(config)
    raise ValueError(
        f"Unknown provider '{name}'. Choose one of: claude, ollama, gemini, openai."
    )


def embed_texts(provider_name: str, config: Config, texts: List[str]) -> List[List[float]]:
    """Embed texts using a named provider. Claude cannot embed."""
    provider = get_provider(provider_name, config)
    embed = getattr(provider, "embed", None)
    if embed is None:
        raise EmbeddingError(
            f"Provider '{provider_name}' cannot produce embeddings. "
            "Use RAG_EMBED_PROVIDER=ollama|gemini|openai."
        )
    return embed(texts)
