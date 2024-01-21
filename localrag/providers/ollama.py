"""Local Ollama provider: chat via /api/chat, embeddings via /api/embeddings."""

from __future__ import annotations

from typing import List

import requests

from ..config import Config


class OllamaProvider:
    name = "ollama"

    def __init__(self, config: Config) -> None:
        self.url = config.ollama_url
        self.model = config.ollama_model
        self.embed_model = config.ollama_embed_model

    def is_available(self) -> bool:
        try:
            requests.get(f"{self.url}/api/tags", timeout=2).raise_for_status()
            return True
        except Exception:
            return False

    def chat(self, system: str, user: str) -> str:
        resp = requests.post(
            f"{self.url}/api/chat",
            json={
                "model": self.model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=180,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"].strip()

    def embed(self, texts: List[str]) -> List[List[float]]:
        vectors: List[List[float]] = []
        for text in texts:
            resp = requests.post(
                f"{self.url}/api/embeddings",
                json={"model": self.embed_model, "prompt": text},
                timeout=120,
            )
            resp.raise_for_status()
            vectors.append(resp.json()["embedding"])
        return vectors
