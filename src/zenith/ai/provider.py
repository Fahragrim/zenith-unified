"""AI Provider abstraction — pluggable backends for LLM and embeddings."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class AIResponse:
    text: str
    model: str = ""
    tokens_used: int = 0
    raw: dict[str, Any] | None = None


@dataclass
class EmbeddingResult:
    vectors: list[list[float]]
    model: str = ""


class AIProvider(ABC):
    """Abstract AI backend. Supports chat + embeddings."""

    name: str = "base"

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    async def chat(self, prompt: str, system: str = "", *, temperature: float = 0.7) -> AIResponse: ...

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        raise NotImplementedError(f"{self.name} does not support embeddings")


class NullProvider(AIProvider):
    """No-op provider — returns empty responses."""

    name = "null"

    def is_available(self) -> bool:
        return True

    async def chat(self, prompt: str, system: str = "", *, temperature: float = 0.7) -> AIResponse:
        return AIResponse(text="[AI not configured — null provider]", model="null")


class LocalProvider(AIProvider):
    """OpenAI-compatible local endpoint (Ollama, LM Studio, etc.)."""

    name = "local"

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "qwen2.5:14b") -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    def is_available(self) -> bool:
        try:
            import httpx  # noqa: F401
            return True
        except ImportError:
            return False

    async def chat(self, prompt: str, system: str = "", *, temperature: float = 0.7) -> AIResponse:
        try:
            import httpx

            messages: list[dict[str, Any]] = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    f"{self.base_url}/v1/chat/completions",
                    json={"model": self.model, "messages": messages, "temperature": temperature},
                )
                data = resp.json()
                text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return AIResponse(text=text, model=self.model, tokens_used=data.get("usage", {}).get("total_tokens", 0), raw=data)
        except Exception as e:
            return AIResponse(text=f"[AI error: {e}]", model=self.model)


def create_provider(name: str = "local", **kwargs: Any) -> AIProvider:
    if name == "null":
        return NullProvider()
    return LocalProvider(**kwargs)
