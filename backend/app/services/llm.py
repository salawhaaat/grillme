from typing import AsyncIterator
from openai import AsyncOpenAI
from google import genai
from google.genai.errors import ClientError, ServerError
from app.core.config import settings
from app.core.logging import setup_logger

logger = setup_logger(__name__)


class RateLimitError(Exception):
    """Provider returned 429 — quota exceeded."""


class ProviderError(Exception):
    """Provider returned an unexpected error."""


class LLMService:
    async def stream_chat(self, messages: list[dict]) -> AsyncIterator[str]:
        provider = settings.llm_provider

        if provider == "openai":
            async for chunk in self._stream_openai(messages):
                yield chunk
        elif provider == "groq":
            async for chunk in self._stream_groq(messages):
                yield chunk
        elif provider == "gemini":
            async for chunk in self._stream_gemini(messages):
                yield chunk
        else:
            raise ValueError(f"Unknown provider: '{provider}'")

    async def _stream_openai(self, messages: list[dict]) -> AsyncIterator[str]:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is not set in .env")

        client = AsyncOpenAI(api_key=settings.openai_api_key)
        stream = await client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            stream=True,
        )

        async for chunk in stream:
            content = chunk.choices[0].delta.content
            if content is not None:
                yield content

    async def _stream_groq(self, messages: list[dict]) -> AsyncIterator[str]:
        if not settings.groq_api_key:
            raise ValueError("GROQ_API_KEY is not set in .env")

        client = AsyncOpenAI(
            api_key=settings.groq_api_key,
            base_url="https://api.groq.com/openai/v1",
        )
        stream = await client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            stream=True,
        )

        async for chunk in stream:
            content = chunk.choices[0].delta.content
            if content is not None:
                yield content

    async def _stream_gemini(self, messages: list[dict]) -> AsyncIterator[str]:
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is not set in .env")

        client = genai.Client(api_key=settings.gemini_api_key)

        prompt = "\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in messages
        )

        try:
            async for chunk in await client.aio.models.generate_content_stream(
                model=settings.llm_model,
                contents=prompt,
            ):
                if chunk.text:
                    yield chunk.text
        except ClientError as e:
            if e.code == 429:
                raise RateLimitError(str(e)) from e
            raise ProviderError(str(e)) from e
        except ServerError as e:
            raise ProviderError(str(e)) from e
