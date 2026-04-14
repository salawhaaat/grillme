from typing import AsyncIterator
import asyncio
import json
import openai
from openai import AsyncOpenAI
from google import genai
from google.genai.errors import ClientError, ServerError
from app.core.config import settings, get_runtime_provider, get_runtime_api_key
from app.core.logging import setup_logger
from app.services.tools import TOOL_REGISTRY

logger = setup_logger(__name__)


class RateLimitError(Exception):
    """Provider returned 429 — quota exceeded."""


class ProviderError(Exception):
    """Provider returned an unexpected error."""


class LLMService:
    def _active_provider(self) -> str:
        return get_runtime_provider() or settings.llm_provider

    def _api_key_for(self, provider: str) -> str:
        if get_runtime_provider() == provider:
            return get_runtime_api_key()
        if provider == "openai":
            return settings.openai_api_key
        if provider == "groq":
            return settings.groq_api_key
        if provider == "gemini":
            return settings.gemini_api_key
        return ""

    async def stream_chat(self, messages: list[dict]) -> AsyncIterator[str]:
        provider = self._active_provider()

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

    @staticmethod
    def _translate_openai_error(e: Exception) -> Exception:
        """Convert OpenAI/Groq SDK errors into our domain exceptions."""
        if isinstance(e, openai.RateLimitError):
            return RateLimitError("Rate limit reached — please wait a few minutes and try again.")
        if isinstance(e, openai.AuthenticationError):
            return ProviderError("Invalid API key — check Settings.")
        if isinstance(e, openai.APIConnectionError):
            return ProviderError("Could not reach the AI provider — check your internet connection.")
        if isinstance(e, openai.OpenAIError):
            return ProviderError(f"AI provider error: {e}")
        return e

    async def _stream_openai(self, messages: list[dict]) -> AsyncIterator[str]:
        key = self._api_key_for("openai")
        if not key:
            raise ValueError("No OpenAI API key — add it in Settings.")

        client = AsyncOpenAI(api_key=key)
        try:
            stream = await client.chat.completions.create(
                model=settings.llm_model,
                messages=messages,
                stream=True,
            )
            async for chunk in stream:
                content = chunk.choices[0].delta.content
                if content is not None:
                    yield content
        except (RateLimitError, ProviderError):
            raise
        except Exception as e:
            raise self._translate_openai_error(e) from e

    async def _stream_groq(self, messages: list[dict]) -> AsyncIterator[str]:
        key = self._api_key_for("groq")
        if not key:
            raise ValueError("No Groq API key — add it in Settings.")

        client = AsyncOpenAI(
            api_key=key,
            base_url="https://api.groq.com/openai/v1",
        )
        try:
            stream = await client.chat.completions.create(
                model=settings.llm_model,
                messages=messages,
                stream=True,
            )
            async for chunk in stream:
                content = chunk.choices[0].delta.content
                if content is not None:
                    yield content
        except (RateLimitError, ProviderError):
            raise
        except Exception as e:
            raise self._translate_openai_error(e) from e

    async def complete(
        self,
        messages: list[dict],
        json_mode: bool = False,
        temperature: float | None = None,
    ) -> str:
        provider = self._active_provider()

        if provider in ("openai", "groq"):
            return await self._complete_compat(messages, json_mode, temperature)
        elif provider == "gemini":
            return await self._complete_gemini(messages)
        else:
            raise ValueError(f"Unknown provider: '{provider}'")

    async def complete_with_tools(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tool_calls: int = 3,
    ) -> str:
        provider = self._active_provider()
        if provider == "gemini":
            return await self.complete(messages)

        key = self._api_key_for(provider)
        if not key:
            raise ValueError(f"No {provider.capitalize()} API key — add it in Settings.")
        if provider == "groq":
            client = AsyncOpenAI(
                api_key=key,
                base_url="https://api.groq.com/openai/v1",
            )
        else:
            client = AsyncOpenAI(api_key=key)

        convo = list(messages)
        for _ in range(max_tool_calls):
            kwargs: dict = dict(model=settings.llm_model, messages=convo)
            if tools:
                kwargs["tools"] = tools
            response = await client.chat.completions.create(**kwargs)
            msg = response.choices[0].message
            if not msg.tool_calls:
                return msg.content or ""

            convo.append(msg.model_dump())
            for tc in msg.tool_calls:
                fn_name = tc.function.name
                fn_args = json.loads(tc.function.arguments or "{}")
                executor = TOOL_REGISTRY.get(fn_name)
                if executor:
                    try:
                        result = await asyncio.wait_for(executor(**fn_args), timeout=15)
                    except (asyncio.TimeoutError, Exception) as e:
                        result = f"Tool execution failed: {e}"
                else:
                    result = f"Unknown tool: {fn_name}"
                convo.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

        final = await client.chat.completions.create(
            model=settings.llm_model,
            messages=convo,
        )
        return final.choices[0].message.content or ""

    async def _complete_compat(
        self,
        messages: list[dict],
        json_mode: bool = False,
        temperature: float | None = None,
    ) -> str:
        provider = self._active_provider()
        key = self._api_key_for(provider)
        if not key:
            raise ValueError(f"No {provider.capitalize()} API key — add it in Settings.")
        if provider == "groq":
            client = AsyncOpenAI(
                api_key=key,
                base_url="https://api.groq.com/openai/v1",
            )
        else:
            client = AsyncOpenAI(api_key=key)

        kwargs: dict = dict(model=settings.llm_model, messages=messages)
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if temperature is not None:
            kwargs["temperature"] = temperature

        try:
            response = await client.chat.completions.create(**kwargs)
            return response.choices[0].message.content
        except (RateLimitError, ProviderError):
            raise
        except Exception as e:
            raise self._translate_openai_error(e) from e

    async def _complete_gemini(self, messages: list[dict]) -> str:
        key = self._api_key_for("gemini")
        if not key:
            raise ValueError("No Gemini API key — add it in Settings.")

        client = genai.Client(api_key=key)
        prompt = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)

        try:
            response = await client.aio.models.generate_content(
                model=settings.llm_model,
                contents=prompt,
            )
            return response.text
        except ClientError as e:
            if e.code == 429:
                raise RateLimitError(str(e)) from e
            raise ProviderError(str(e)) from e
        except ServerError as e:
            raise ProviderError(str(e)) from e

    async def _stream_gemini(self, messages: list[dict]) -> AsyncIterator[str]:
        key = self._api_key_for("gemini")
        if not key:
            raise ValueError("No Gemini API key — add it in Settings.")

        client = genai.Client(api_key=key)

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
