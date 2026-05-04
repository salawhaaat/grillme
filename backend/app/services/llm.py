from abc import ABC, abstractmethod
from typing import AsyncIterator
import asyncio
import json
import re
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


# ── Abstract base ─────────────────────────────────────────────────────────────

class BaseProvider(ABC):
    @abstractmethod
    async def stream(self, messages: list[dict]) -> AsyncIterator[str]: ...

    @abstractmethod
    async def complete(
        self,
        messages: list[dict],
        *,
        json_mode: bool = False,
        temperature: float | None = None,
    ) -> str: ...

    @abstractmethod
    async def complete_with_tools(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tool_calls: int = 3,
    ) -> str: ...


# ── Adapters ──────────────────────────────────────────────────────────────────

# Providers that natively support response_format: json_object.
# All others get a prompt-injected instruction instead.
_NATIVE_JSON_MODE = {"openai", "groq"}


def _inject_json_instruction(messages: list[dict]) -> list[dict]:
    """Append a JSON-only instruction to the system message (or prepend one)."""
    note = "Respond with valid JSON only. No markdown fences, no explanation."
    if messages and messages[0]["role"] == "system":
        return [{**messages[0], "content": f"{messages[0]['content']}\n\n{note}"}, *messages[1:]]
    return [{"role": "system", "content": note}, *messages]


def _fix_bare_newlines_in_json(text: str) -> str:
    """Replace bare newlines inside JSON string values with \\n/\\r escape sequences.

    Operates as a character state machine so outer formatting whitespace (valid JSON)
    is left untouched while bare newlines that appear inside string values (invalid
    JSON) are properly escaped. This preserves newlines in starter_code, etc.
    """
    result: list[str] = []
    in_string = False
    escaped = False
    for ch in text:
        if escaped:
            result.append(ch)
            escaped = False
        elif ch == '\\' and in_string:
            result.append(ch)
            escaped = True
        elif ch == '"':
            in_string = not in_string
            result.append(ch)
        elif in_string and ch == '\n':
            result.append('\\n')
        elif in_string and ch == '\r':
            result.append('\\r')
        else:
            result.append(ch)
    return ''.join(result)


def _strip_json_fences(text: str) -> str:
    """Strip markdown fences and sanitize control characters from LLM JSON output."""
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    text = match.group(1).strip() if match else text
    # Replace other literal control characters (not \n/\r — handled below).
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', ' ', text)
    # Fix bare newlines only inside JSON string values (preserves code indentation).
    return _fix_bare_newlines_in_json(text)


class OpenAICompatProvider(BaseProvider):
    """Adapter for any OpenAI-compatible chat completions endpoint."""

    def __init__(self, api_key: str, base_url: str | None = None, name: str = "") -> None:
        self._name = name
        self._native_json_mode = name in _NATIVE_JSON_MODE
        kwargs: dict = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = AsyncOpenAI(**kwargs)

    def _raise(self, e: Exception) -> None:
        if isinstance(e, openai.RateLimitError):
            raise RateLimitError("Rate limit reached — please wait a few minutes and try again.") from e
        if isinstance(e, openai.AuthenticationError):
            raise ProviderError("Invalid API key — check Settings.") from e
        if isinstance(e, openai.APIConnectionError):
            msg = (
                "Could not reach Ollama — make sure 'ollama serve' is running."
                if self._name == "ollama"
                else "Could not reach the AI provider — check your internet connection."
            )
            raise ProviderError(msg) from e
        if isinstance(e, openai.OpenAIError):
            raise ProviderError(f"AI provider error: {e}") from e
        raise e

    async def stream(self, messages: list[dict]) -> AsyncIterator[str]:
        try:
            result = await self._client.chat.completions.create(
                model=settings.llm_model,
                messages=messages,
                stream=True,
            )
            async for chunk in result:
                content = chunk.choices[0].delta.content
                if content is not None:
                    yield content
        except Exception as e:
            self._raise(e)

    async def complete(
        self,
        messages: list[dict],
        *,
        json_mode: bool = False,
        temperature: float | None = None,
    ) -> str:
        if json_mode and not self._native_json_mode:
            messages = _inject_json_instruction(messages)
        kwargs: dict = dict(model=settings.llm_model, messages=messages)
        if json_mode and self._native_json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if temperature is not None:
            kwargs["temperature"] = temperature
        try:
            response = await self._client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content or ""
            return _strip_json_fences(content) if json_mode else content
        except Exception as e:
            self._raise(e)

    async def complete_with_tools(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tool_calls: int = 3,
    ) -> str:
        convo = list(messages)
        for _ in range(max_tool_calls):
            kwargs: dict = dict(model=settings.llm_model, messages=convo)
            if tools:
                kwargs["tools"] = tools
            response = await self._client.chat.completions.create(**kwargs)
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
                convo.append({"role": "tool", "tool_call_id": tc.id, "content": result})

        final = await self._client.chat.completions.create(
            model=settings.llm_model, messages=convo
        )
        return final.choices[0].message.content or ""


class GeminiProvider(BaseProvider):
    """Adapter for the Google Gemini SDK."""

    def __init__(self, api_key: str) -> None:
        self._client = genai.Client(api_key=api_key)

    def _prompt(self, messages: list[dict]) -> str:
        return "\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)

    def _raise(self, e: Exception) -> None:
        if isinstance(e, ClientError):
            raise (RateLimitError(str(e)) if e.code == 429 else ProviderError(str(e))) from e
        if isinstance(e, ServerError):
            raise ProviderError(str(e)) from e
        raise e

    async def stream(self, messages: list[dict]) -> AsyncIterator[str]:
        try:
            async for chunk in await self._client.aio.models.generate_content_stream(
                model=settings.llm_model,
                contents=self._prompt(messages),
            ):
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            self._raise(e)

    async def complete(
        self,
        messages: list[dict],
        *,
        json_mode: bool = False,
        temperature: float | None = None,
    ) -> str:
        try:
            response = await self._client.aio.models.generate_content(
                model=settings.llm_model,
                contents=self._prompt(messages),
            )
            return response.text
        except Exception as e:
            self._raise(e)

    async def complete_with_tools(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tool_calls: int = 3,
    ) -> str:
        return await self.complete(messages)


# ── Factory ───────────────────────────────────────────────────────────────────

class ProviderFactory:
    @staticmethod
    def create(name: str, api_key: str | None = None) -> BaseProvider:
        # Evaluated on each call so settings mocks in tests are picked up.
        # To add a new OpenAI-compatible provider: one entry here + settings field in config.py.
        compat: dict[str, tuple[str, str | None]] = {
            # name:          (settings_api_key,         base_url or None for OpenAI default)
            "openai":        (settings.openai_api_key,  None),
            "groq":          (settings.groq_api_key,    "https://api.groq.com/openai/v1"),
            "ollama":        ("ollama",                  f"{settings.ollama_base_url}/v1"),
            "ollama_cloud":  (settings.ollama_api_key,  settings.ollama_cloud_base_url),
        }

        if name == "gemini":
            key = api_key or settings.gemini_api_key
            if not key:
                raise ValueError("No Gemini API key — add it in Settings.")
            return GeminiProvider(api_key=key)

        if name not in compat:
            raise ValueError(f"Unknown provider: '{name}'")

        default_key, base_url = compat[name]
        key = api_key or default_key
        if not key:
            raise ValueError(f"No API key configured for '{name}' — add it in .env or Settings.")

        return OpenAICompatProvider(api_key=key, base_url=base_url, name=name)


# ── Facade ────────────────────────────────────────────────────────────────────

class LLMService:
    """Thin facade — callers use this; provider details are hidden behind it."""

    def _get_provider(self) -> BaseProvider:
        name = get_runtime_provider() or settings.llm_provider
        runtime_key = get_runtime_api_key() if get_runtime_provider() else None
        return ProviderFactory.create(name, api_key=runtime_key)

    async def stream_chat(self, messages: list[dict]) -> AsyncIterator[str]:
        async for chunk in self._get_provider().stream(messages):
            yield chunk

    async def complete(
        self,
        messages: list[dict],
        json_mode: bool = False,
        temperature: float | None = None,
    ) -> str:
        return await self._get_provider().complete(
            messages, json_mode=json_mode, temperature=temperature
        )

    async def complete_with_tools(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tool_calls: int = 3,
    ) -> str:
        return await self._get_provider().complete_with_tools(
            messages, tools=tools, max_tool_calls=max_tool_calls
        )
