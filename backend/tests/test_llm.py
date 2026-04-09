import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from google.genai.errors import ClientError, ServerError
from app.services.llm import LLMService, RateLimitError, ProviderError


MESSAGES = [{"role": "user", "content": "explain two sum"}]


def make_chunk(content: str) -> AsyncMock:
    """Create a mocked streamed chunk with the given content."""
    chunk = AsyncMock()
    chunk.choices[0].delta.content = content
    return chunk


async def stream(*tokens: str):
    """Yield mocked streamed chunks for each token in order."""
    for t in tokens:
        yield make_chunk(t)


def make_client_error(status_code: int, message: str) -> ClientError:
    response = MagicMock()
    response.status_code = status_code
    return ClientError(status_code, {"error": {"message": message}}, response)


@pytest.fixture
def mock_openai():
    with (
        patch("app.services.llm.AsyncOpenAI") as MockClient,
        patch("app.services.llm.settings") as s,
    ):
        s.llm_provider = "openai"
        s.llm_model = "gpt-4o-mini"
        s.openai_api_key = "sk-test"
        yield MockClient.return_value, s


@pytest.fixture
def mock_gemini():
    with (
        patch("app.services.llm.genai") as MockGenai,
        patch("app.services.llm.settings") as s,
    ):
        s.llm_provider = "gemini"
        s.llm_model = "gemini-2.0-flash-lite"
        s.gemini_api_key = "test-key"
        yield MockGenai.Client.return_value, s


async def collect(gen):
    """Collect all items from an async generator into a list."""
    return [chunk async for chunk in gen]


# --- OpenAI tests ---

async def test_returns_tokens(mock_openai):
    """Verify that streamed tokens are returned in order."""
    client, _ = mock_openai
    client.chat.completions.create = AsyncMock(
        return_value=stream("Hello", " candidate", ".")
    )

    result = await collect(LLMService().stream_chat(MESSAGES))

    assert result == ["Hello", " candidate", "."]


async def test_skips_none_chunks(mock_openai):
    """Verify that None chunks are skipped from the streamed output."""
    client, _ = mock_openai
    client.chat.completions.create = AsyncMock(return_value=stream(None, "Hi"))

    result = await collect(LLMService().stream_chat(MESSAGES))

    assert result == ["Hi"]


async def test_raises_without_openai_key():
    """Verify that missing OpenAI API key raises a ValueError."""
    with patch("app.services.llm.settings") as s:
        s.llm_provider = "openai"
        s.openai_api_key = ""

        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            await collect(LLMService().stream_chat(MESSAGES))


async def test_raises_unknown_provider():
    """Verify that an unknown provider raises a ValueError."""
    with patch("app.services.llm.settings") as s:
        s.llm_provider = "unknown"
        s.openai_api_key = "sk-test"

        with pytest.raises(ValueError, match="provider"):
            await collect(LLMService().stream_chat(MESSAGES))


async def test_calls_openai_with_correct_args(mock_openai):
    """Verify that OpenAI API is called with correct model, messages, and stream parameters."""
    client, conf = mock_openai
    client.chat.completions.create = AsyncMock(return_value=stream("Hi"))

    await collect(LLMService().stream_chat(MESSAGES))

    client.chat.completions.create.assert_called_once_with(
        model=conf.llm_model, messages=MESSAGES, stream=True
    )


# --- Gemini tests ---

async def test_raises_without_gemini_key():
    """Verify that missing Gemini API key raises a ValueError."""
    with patch("app.services.llm.settings") as s:
        s.llm_provider = "gemini"
        s.gemini_api_key = ""

        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            await collect(LLMService().stream_chat(MESSAGES))


async def test_gemini_rate_limit_raises_rate_limit_error(mock_gemini):
    """Verify that a 429 from Gemini raises RateLimitError."""
    client, _ = mock_gemini

    async def fail():
        raise make_client_error(429, "quota exceeded")
        yield  # make it an async generator

    client.aio.models.generate_content_stream = AsyncMock(return_value=fail())

    with pytest.raises(RateLimitError, match="quota"):
        await collect(LLMService().stream_chat(MESSAGES))


async def test_gemini_model_not_found_raises_provider_error(mock_gemini):
    """Verify that a 404 from Gemini raises ProviderError."""
    client, _ = mock_gemini

    async def fail():
        raise make_client_error(404, "model not found")
        yield

    client.aio.models.generate_content_stream = AsyncMock(return_value=fail())

    with pytest.raises(ProviderError, match="model not found"):
        await collect(LLMService().stream_chat(MESSAGES))


async def test_gemini_server_error_raises_provider_error(mock_gemini):
    """Verify that a 5xx ServerError from Gemini raises ProviderError."""
    client, _ = mock_gemini

    async def fail():
        raise ServerError(500, {"error": {"message": "internal server error"}}, MagicMock())
        yield

    client.aio.models.generate_content_stream = AsyncMock(return_value=fail())

    with pytest.raises(ProviderError):
        await collect(LLMService().stream_chat(MESSAGES))
