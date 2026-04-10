import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.llm import LLMService
from app.services.tools import WEB_SEARCH_TOOL, execute_web_search


def _mock_message(content="ok", tool_calls=None):
    return SimpleNamespace(
        content=content,
        tool_calls=tool_calls or [],
        model_dump=lambda: {"role": "assistant", "content": content},
    )


def _mock_response(message):
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def test_web_search_tool_schema():
    assert WEB_SEARCH_TOOL["type"] == "function"
    assert WEB_SEARCH_TOOL["function"]["name"] == "web_search"
    assert "parameters" in WEB_SEARCH_TOOL["function"]
    assert WEB_SEARCH_TOOL["function"]["parameters"]["required"] == ["query"]


async def test_execute_web_search_returns_summary_string():
    html = (
        '<a class="result__a">Result One</a><a class="result__snippet">Snippet one</a>'
        '<a class="result__a">Result Two</a><a class="result__snippet">Snippet two</a>'
    )
    response = MagicMock()
    response.text = html
    response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = response
        result = await execute_web_search("stripe interview")

    assert isinstance(result, str)
    assert "Result One" in result


async def test_execute_web_search_timeout_returns_error_string():
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.TimeoutException("timeout")
        result = await execute_web_search("stripe interview")

    assert "timeout" in result.lower()


async def test_complete_with_tools_no_tool_calls_returns_direct_content():
    with patch("app.services.llm.settings") as s, patch("app.services.llm.AsyncOpenAI") as MockClient:
        s.llm_provider = "openai"
        s.llm_model = "gpt-4o-mini"
        s.openai_api_key = "sk-test"
        client = MockClient.return_value
        client.chat.completions.create = AsyncMock(
            return_value=_mock_response(_mock_message(content="final answer", tool_calls=[]))
        )

        result = await LLMService().complete_with_tools([{"role": "user", "content": "hi"}], tools=[])

    assert result == "final answer"


async def test_complete_with_tools_executes_tool_then_returns_final():
    tool_call = SimpleNamespace(
        id="tc_1",
        function=SimpleNamespace(name="web_search", arguments='{"query":"stripe interview"}'),
    )
    first = _mock_response(_mock_message(content=None, tool_calls=[tool_call]))
    second = _mock_response(_mock_message(content="tool-augmented final", tool_calls=[]))

    with (
        patch("app.services.llm.settings") as s,
        patch("app.services.llm.AsyncOpenAI") as MockClient,
        patch("app.services.llm.TOOL_REGISTRY", {"web_search": AsyncMock(return_value="search output")}),
    ):
        s.llm_provider = "openai"
        s.llm_model = "gpt-4o-mini"
        s.openai_api_key = "sk-test"
        client = MockClient.return_value
        client.chat.completions.create = AsyncMock(side_effect=[first, second])

        result = await LLMService().complete_with_tools(
            [{"role": "user", "content": "research stripe"}],
            tools=[WEB_SEARCH_TOOL],
            max_tool_calls=3,
        )

    assert result == "tool-augmented final"


async def test_complete_with_tools_respects_max_tool_calls_limit():
    tool_call = SimpleNamespace(
        id="tc_1",
        function=SimpleNamespace(name="web_search", arguments='{"query":"stripe interview"}'),
    )
    loop_response = _mock_response(_mock_message(content=None, tool_calls=[tool_call]))
    final_response = _mock_response(_mock_message(content="final after limit", tool_calls=[]))

    with (
        patch("app.services.llm.settings") as s,
        patch("app.services.llm.AsyncOpenAI") as MockClient,
        patch("app.services.llm.TOOL_REGISTRY", {"web_search": AsyncMock(return_value="search output")}),
    ):
        s.llm_provider = "openai"
        s.llm_model = "gpt-4o-mini"
        s.openai_api_key = "sk-test"
        client = MockClient.return_value
        client.chat.completions.create = AsyncMock(side_effect=[loop_response, final_response])

        result = await LLMService().complete_with_tools(
            [{"role": "user", "content": "research stripe"}],
            tools=[WEB_SEARCH_TOOL],
            max_tool_calls=1,
        )

    assert result == "final after limit"
