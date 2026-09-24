"""Lesson 9 - Ollama's /api/chat with tools, and nothing else.

Lesson 1's provider (`localrag/providers/ollama.py`) sends one system and one
user message and reads back text. Tool calling needs the whole message list and
a `tools` array, so this is a separate ~80-line client over `requests`, which the
course already depends on. No SDK: the point is to see the JSON.

Request:   {"model", "messages", "tools": [...], "stream": false, "options": {...}}
Response:  {"message": {"role": "assistant", "content": "...",
                        "tool_calls": [{"function": {"name": ..., "arguments": {...}}}]}}
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional

import requests


class OllamaError(RuntimeError):
    """The model failed: a crash, a bad request, a missing model."""


class OllamaUnreachable(OllamaError):
    """The server is not there. Not the model's fault, so never recorded as its result."""


class OllamaModel:
    def __init__(self, url: str, model: str, *, think: Optional[bool] = False,
                 temperature: float = 0.0, seed: int = 7, num_ctx: int = 8192,
                 timeout: float = 600.0) -> None:
        self.url = url.rstrip("/")
        self.model = model
        self.think = think
        # num_ctx: Ollama's default window is 4K on machines with under 24 GB of VRAM.
        # Tool schemas, three passages and a few turns fit in 8K; past the window,
        # Ollama truncates the prompt and the model never sees what was cut.
        self.options = {"temperature": temperature, "seed": seed, "num_ctx": num_ctx}
        self.timeout = timeout
        self._caps: Optional[List[str]] = None

    def capabilities(self) -> List[str]:
        """What the model's own metadata claims: e.g. ['completion', 'tools', 'thinking']."""
        if self._caps is None:
            self._caps = show(self.url, self.model).get("capabilities", [])
        return self._caps

    def chat(self, messages: List[dict], tools: List[dict]) -> Dict:
        payload: Dict = {"model": self.model, "messages": messages, "stream": False,
                         "options": self.options}
        if tools:
            payload["tools"] = tools
        # Sending `think` to a model without the capability is an error, not a no-op.
        if self.think is not None and "thinking" in self.capabilities():
            payload["think"] = self.think
        started = time.monotonic()
        try:
            resp = requests.post(f"{self.url}/api/chat", json=payload, timeout=self.timeout)
        except requests.ConnectionError as exc:
            # First: ConnectTimeout is both a ConnectionError and a Timeout, and a
            # server that cannot be reached is an outage, not the model's answer.
            raise OllamaUnreachable(f"cannot reach Ollama at {self.url}: {exc}") from exc
        except requests.Timeout as exc:
            # The server is there; the model did not answer in time. On a CPU that
            # is a result worth recording, not an outage.
            raise OllamaError(f"no reply within {self.timeout:.0f}s") from exc
        except requests.RequestException as exc:
            raise OllamaUnreachable(f"cannot reach Ollama at {self.url}: {exc}") from exc
        if resp.status_code == 404:
            raise OllamaError(f"model {self.model!r} not found - run: ollama pull {self.model}")
        body = _json(resp)
        if resp.status_code != 200 or "error" in body:
            raise OllamaError(body.get("error") or f"HTTP {resp.status_code}")
        msg = body.get("message", {})
        keep = {"role": "assistant", "content": msg.get("content") or ""}
        if msg.get("tool_calls"):
            keep["tool_calls"] = msg["tool_calls"]
        return {"message": keep, "seconds": round(time.monotonic() - started, 1)}


def _json(resp) -> Dict:
    try:
        return resp.json()
    except ValueError:
        return {"error": resp.text[:200] or f"HTTP {resp.status_code}"}


def show(url: str, model: str) -> Dict:
    try:
        resp = requests.post(f"{url.rstrip('/')}/api/show", json={"model": model}, timeout=30)
    except requests.RequestException as exc:
        raise OllamaUnreachable(f"cannot reach Ollama at {url}: {exc}") from exc
    return _json(resp) if resp.status_code == 200 else {}


def unload(url: str, model: str) -> None:
    """Free the model's memory now instead of after Ollama's 5-minute keep-alive.

    Recording six models back to back on a 19 GB laptop got the server
    OOM-killed: the last model was still resident while the next one loaded.
    """
    try:
        requests.post(f"{url.rstrip('/')}/api/generate",
                      json={"model": model, "keep_alive": 0}, timeout=60)
    except requests.RequestException:
        pass


def version(url: str) -> str:
    try:
        return requests.get(f"{url.rstrip('/')}/api/version", timeout=5).json().get("version", "?")
    except (requests.RequestException, ValueError):
        return "?"


def local_models(url: str) -> List[Dict]:
    """Every pulled model with its size and advertised capabilities."""
    try:
        resp = requests.get(f"{url.rstrip('/')}/api/tags", timeout=10)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise OllamaUnreachable(f"cannot reach Ollama at {url}: {exc}") from exc
    out = []
    for m in resp.json().get("models", []):
        caps = show(url, m["name"]).get("capabilities", [])
        gb = round(m.get("size", 0) / 1e9, 1)
        out.append({"name": m["name"], "gb": gb, "capabilities": caps})
    return sorted(out, key=lambda m: m["name"])
