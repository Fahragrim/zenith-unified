"""Unit tests for zenith/ai/provider.py — AI provider abstraction."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from zenith.ai.provider import AIProvider, AIResponse, EmbeddingResult, LocalProvider, NullProvider, create_provider


class TestAIResponse:
    """Tests for the AIResponse dataclass."""

    def test_creation_all_fields(self) -> None:
        result = AIResponse(text="Hello", model="gpt-4", tokens_used=42, raw={"key": "val"})
        assert result.text == "Hello"
        assert result.model == "gpt-4"
        assert result.tokens_used == 42
        assert result.raw == {"key": "val"}

    def test_creation_defaults(self) -> None:
        result = AIResponse(text="Hello")
        assert result.text == "Hello"
        assert result.model == ""
        assert result.tokens_used == 0
        assert result.raw is None

    def test_repr(self) -> None:
        result = AIResponse(text="test", model="m", tokens_used=5)
        assert "AIResponse" in repr(result)


class TestEmbeddingResult:
    """Tests for the EmbeddingResult dataclass."""

    def test_creation(self) -> None:
        vectors = [[0.1, 0.2], [0.3, 0.4]]
        result = EmbeddingResult(vectors=vectors, model="minilm")
        assert result.vectors == vectors
        assert result.model == "minilm"

    def test_default_model(self) -> None:
        result = EmbeddingResult(vectors=[])
        assert result.model == ""


class TestNullProvider:
    """Tests for the NullProvider (no-op backend)."""

    def test_is_available(self) -> None:
        provider = NullProvider()
        assert provider.is_available() is True

    @pytest.mark.asyncio
    async def test_chat_returns_null_message(self) -> None:
        provider = NullProvider()
        result = await provider.chat("any prompt")
        assert isinstance(result, AIResponse)
        assert result.text == "[AI not configured — null provider]"
        assert result.model == "null"

    @pytest.mark.asyncio
    async def test_chat_with_system_prompt(self) -> None:
        provider = NullProvider()
        result = await provider.chat("prompt", system="be helpful")
        assert result.text == "[AI not configured — null provider]"

    @pytest.mark.asyncio
    async def test_embed_raises_not_implemented(self) -> None:
        provider = NullProvider()
        with pytest.raises(NotImplementedError):
            await provider.embed(["text"])


class TestLocalProvider:
    """Tests for the LocalProvider (OpenAI-compatible)."""

    def test_init_defaults(self) -> None:
        provider = LocalProvider()
        assert provider.base_url == "http://localhost:11434"
        assert provider.model == "qwen2.5:14b"

    def test_init_custom(self) -> None:
        provider = LocalProvider(base_url="http://127.0.0.1:8080/", model="llama3")
        assert provider.base_url == "http://127.0.0.1:8080"
        assert provider.model == "llama3"

    def test_is_available_true(self) -> None:
        provider = LocalProvider()
        assert provider.is_available() is True

    def test_is_available_false(self) -> None:
        with patch("builtins.__import__") as mock_import:
            mock_import.side_effect = ImportError("no httpx")
            provider = LocalProvider()
            assert provider.is_available() is False

    @pytest.mark.asyncio
    async def test_chat_success(self) -> None:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "hello world"}}],
            "usage": {"total_tokens": 10},
        }
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            provider = LocalProvider()
            result = await provider.chat("hi")

        assert result.text == "hello world"
        assert result.model == "qwen2.5:14b"
        assert result.tokens_used == 10
        assert result.raw is not None

        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args[1]
        assert call_kwargs["json"]["model"] == "qwen2.5:14b"
        assert call_kwargs["json"]["messages"] == [{"role": "user", "content": "hi"}]
        assert call_kwargs["json"]["temperature"] == 0.7

    @pytest.mark.asyncio
    async def test_chat_with_system_prompt(self) -> None:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "response"}}],
            "usage": {"total_tokens": 5},
        }
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            provider = LocalProvider()
            result = await provider.chat("question", system="be concise")

        assert result.text == "response"

        call_kwargs = mock_client.post.call_args[1]
        assert call_kwargs["json"]["messages"] == [
            {"role": "system", "content": "be concise"},
            {"role": "user", "content": "question"},
        ]

    @pytest.mark.asyncio
    async def test_chat_error_path(self) -> None:
        with patch("httpx.AsyncClient", side_effect=RuntimeError("connection refused")):
            provider = LocalProvider()
            result = await provider.chat("hi")

        assert result.text == "[AI error: connection refused]"
        assert result.model == "qwen2.5:14b"

    @pytest.mark.asyncio
    async def test_chat_error_during_request(self) -> None:
        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.side_effect = RuntimeError("timeout")

        with patch("httpx.AsyncClient", return_value=mock_client):
            provider = LocalProvider()
            result = await provider.chat("hi")

        assert "[AI error:" in result.text

    @pytest.mark.asyncio
    async def test_chat_empty_content(self) -> None:
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": ""}}], "usage": {}}
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            provider = LocalProvider()
            result = await provider.chat("hi")

        assert result.text == ""


class TestCreateProvider:
    """Tests for the factory function create_provider."""

    def test_create_null(self) -> None:
        provider = create_provider("null")
        assert isinstance(provider, NullProvider)

    def test_create_local_default(self) -> None:
        provider = create_provider("local")
        assert isinstance(provider, LocalProvider)
        assert provider.model == "qwen2.5:14b"

    def test_create_local_with_kwargs(self) -> None:
        provider = create_provider("local", base_url="http://localhost:8080", model="custom")
        assert isinstance(provider, LocalProvider)
        assert provider.base_url == "http://localhost:8080"
        assert provider.model == "custom"

    def test_create_local_without_name(self) -> None:
        provider = create_provider()
        assert isinstance(provider, LocalProvider)

    def test_ai_provider_abstract(self) -> None:
        assert AIProvider.__abstractmethods__ == {"chat", "is_available"}
