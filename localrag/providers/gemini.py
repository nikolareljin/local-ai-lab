"""Google Gemini provider via the Generative Language REST API."""

from __future__ import annotations

from typing import List

import requests

from ..config import Config

_BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider:
    name = "gemini"

    def __init__(self, config: Config) -> None:
        self.api_key = config.gemini_api_key
        self.model = config.gemini_model
        self.embed_model = config.gemini_embed_model

    def is_available(self) -> bool:
        return bool(self.api_key)

    def chat(self, system: str, user: str) -> str:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not set.")
        resp = requests.post(
            f"{_BASE}/models/{self.model}:generateContent",
            params={"key": self.api_key},
            json={
                "system_instruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
            },
            timeout=180,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()

    def embed(self, texts: List[str]) -> List[List[float]]:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not set.")
        vectors: List[List[float]] = []
        for text in texts:
            resp = requests.post(
                f"{_BASE}/models/{self.embed_model}:embedContent",
                params={"key": self.api_key},
                json={"content": {"parts": [{"text": text}]}},
                timeout=120,
            )
            resp.raise_for_status()
            vectors.append(resp.json()["embedding"]["values"])
        return vectors
