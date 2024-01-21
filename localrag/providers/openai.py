"""OpenAI (or any OpenAI-compatible endpoint) provider.

Works against api.openai.com, and also against local OpenAI-compatible servers
by overriding OPENAI_BASE_URL (vLLM, LM Studio, Ollama's /v1, etc.).
"""

from __future__ import annotations

from typing import List

import requests

from ..config import Config


class OpenAIProvider:
    name = "openai"

    def __init__(self, config: Config) -> None:
        self.api_key = config.openai_api_key
        self.base_url = config.openai_base_url
        self.model = config.openai_model
        self.embed_model = config.openai_embed_model

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}"}

    def is_available(self) -> bool:
        return bool(self.api_key)

    def chat(self, system: str, user: str) -> str:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not set.")
        resp = requests.post(
            f"{self.base_url}/chat/completions",
            headers=self._headers(),
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=180,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

    def embed(self, texts: List[str]) -> List[List[float]]:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not set.")
        resp = requests.post(
            f"{self.base_url}/embeddings",
            headers=self._headers(),
            json={"model": self.embed_model, "input": texts},
            timeout=120,
        )
        resp.raise_for_status()
        return [item["embedding"] for item in resp.json()["data"]]
