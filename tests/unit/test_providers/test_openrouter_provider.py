"""Unit tests for OpenRouterProvider.

All tests mock the AsyncOpenAI client — no real API calls are made.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("openai", reason="openai SDK not installed")

from repowise.core.providers.llm.base import GeneratedResponse, ProviderError, RateLimitError
from repowise.core.providers.llm.openrouter import OpenRouterProvider

# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_provider_name():
    p = OpenRouterProvider(api_key="sk-or-test")
    assert p.provider_name == "openrouter"


def test_default_model():
    p = OpenRouterProvider(api_key="sk-or-test")
    assert p.model_name == "anthropic/claude-sonnet-4.6"


def test_api_key_from_env(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-env-test")
    p = OpenRouterProvider()
    assert p.provider_name == "openrouter"


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ProviderError):
        OpenRouterProvider()


def test_custom_model():
    p = OpenRouterProvider(api_key="sk-or-test", model="google/gemini-3.1-flash-lite-preview")
    assert p.model_name == "google/gemini-3.1-flash-lite-preview"


def test_default_headers_app_title():
    """Default app_title='repowise' sets X-Title header."""
    p = OpenRouterProvider(api_key="sk-or-test")
    headers = p._client._custom_headers
    assert headers.get("X-Title") == "repowise"


def test_default_headers_with_referer():
    """When http_referer is provided, HTTP-Referer header is set."""
    p = OpenRouterProvider(api_key="sk-or-test", http_referer="https://example.com")
    headers = p._client._custom_headers
    assert headers.get("HTTP-Referer") == "https://example.com"
    assert headers.get("X-Title") == "repowise"


def test_no_headers_when_empty():
    """When app_title is empty and no referer, no custom headers."""
    p = OpenRouterProvider(api_key="sk-or-test", app_title="")
    # default_headers should be None → no custom headers set
    headers = p._client._custom_headers
    assert not headers.get("X-Title")


# ---------------------------------------------------------------------------
# Successful generation
# ---------------------------------------------------------------------------


def _make_mock_chat_response(text: str = "# Doc\nContent.") -> MagicMock:
    usage = MagicMock()
    usage.prompt_tokens = 120
    usage.completion_tokens = 60
    usage.total_tokens = 180

    choice = MagicMock()
    choice.message.content = text

    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    return response


async def test_generate_returns_generated_response():
    provider = OpenRouterProvider(api_key="sk-or-test")
    mock_response = _make_mock_chat_response("Hello from OpenRouter")

    with patch("openai.AsyncOpenAI") as mock_client:
        mock_client.return_value.chat.completions.create = AsyncMock(return_value=mock_response)
        provider._client = mock_client.return_value
        result = await provider.generate("sys", "user")

    assert isinstance(result, GeneratedResponse)
    assert result.content == "Hello from OpenRouter"


async def test_generate_token_counts():
    provider = OpenRouterProvider(api_key="sk-or-test")
    mock_response = _make_mock_chat_response()

    with patch("openai.AsyncOpenAI") as mock_client:
        mock_client.return_value.chat.completions.create = AsyncMock(return_value=mock_response)
        provider._client = mock_client.return_value
        result = await provider.generate("sys", "user")

    assert result.input_tokens == 120
    assert result.output_tokens == 60
    assert result.cached_tokens == 0


async def test_generate_sends_correct_messages():
    provider = OpenRouterProvider(api_key="sk-or-test", model="google/gemini-3.1-flash-lite-preview")
    mock_response = _make_mock_chat_response()
    captured_kwargs: list[dict] = []

    async def fake_create(**kwargs):
        captured_kwargs.append(kwargs)
        return mock_response

    with patch("openai.AsyncOpenAI") as mock_client:
        mock_client.return_value.chat.completions.create = fake_create
        provider._client = mock_client.return_value
        await provider.generate("system msg", "user msg", max_tokens=2048, temperature=0.5)

    kw = captured_kwargs[0]
    assert kw["model"] == "google/gemini-3.1-flash-lite-preview"
    assert kw["max_completion_tokens"] == 2048
    assert kw["temperature"] == 0.5
    messages = kw["messages"]
    assert messages[0] == {"role": "system", "content": "system msg"}
    assert messages[1] == {"role": "user", "content": "user msg"}


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


async def test_rate_limit_error():
    from openai import RateLimitError as _OpenAIRateLimitError

    provider = OpenRouterProvider(api_key="sk-or-test")

    with patch("openai.AsyncOpenAI") as mock_client:
        mock_client.return_value.chat.completions.create = AsyncMock(
            side_effect=_OpenAIRateLimitError(
                "rate limit", response=MagicMock(status_code=429), body={}
            )
        )
        provider._client = mock_client.return_value
        with pytest.raises(RateLimitError):
            await provider.generate("sys", "user")


async def test_api_status_error():
    from openai import APIStatusError as _OpenAIAPIStatusError

    provider = OpenRouterProvider(api_key="sk-or-test")

    with patch("openai.AsyncOpenAI") as mock_client:
        mock_client.return_value.chat.completions.create = AsyncMock(
            side_effect=_OpenAIAPIStatusError(
                "server error", response=MagicMock(status_code=500), body={}
            )
        )
        provider._client = mock_client.return_value
        with pytest.raises(ProviderError):
            await provider.generate("sys", "user")
