import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.llm import LLMService
from app.services.research import ResearchService, _cache


class _Response:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error",
                request=httpx.Request("GET", "https://html.duckduckgo.com"),
                response=httpx.Response(self.status_code),
            )


@pytest.fixture(autouse=True)
def clear_research_cache():
    _cache.clear()
    yield
    _cache.clear()


@pytest.fixture
def research_service():
    llm = AsyncMock(spec=LLMService)
    return ResearchService(llm=llm), llm


async def test_search_returns_structured_summary(research_service):
    service, llm = research_service
    html = (
        '<a class="result__a">Stripe interview experience</a>'
        '<a class="result__snippet">Mostly systems and behavioral</a>'
    )
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [_Response(html), _Response(html), _Response(html)]
        llm.complete.return_value = json.dumps({
            "common_questions": ["Tell me about yourself"],
            "culture_notes": "Fast-paced",
            "interview_format": "Phone + onsite",
            "tips": ["Practice system design"],
        })

        result = await service.search("Stripe", "Software Engineer")

    assert result["no_results"] is False
    assert result["common_questions"] == ["Tell me about yourself"]
    assert mock_get.await_count == 3
    llm.complete.assert_awaited_once()


async def test_search_handles_timeout_with_partial_results(research_service):
    service, llm = research_service
    html = (
        '<a class="result__a">Stripe Reddit thread</a>'
        '<a class="result__snippet">Good communication focus</a>'
    )
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [
            httpx.TimeoutException("timeout"),
            _Response(html),
            _Response(html),
        ]
        llm.complete.return_value = json.dumps({
            "common_questions": ["Behavioral deep dive"],
            "culture_notes": "Collaborative",
            "interview_format": "Screen + panel",
            "tips": ["Prepare STAR stories"],
        })

        result = await service.search("Stripe", "Backend Engineer")

    assert result["no_results"] is False
    assert "common_questions" in result
    assert mock_get.await_count == 3
    llm.complete.assert_awaited_once()


async def test_search_all_sources_fail_returns_no_results(research_service):
    service, llm = research_service
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [
            httpx.TimeoutException("timeout"),
            httpx.HTTPError("boom"),
            httpx.TimeoutException("timeout"),
        ]

        result = await service.search("Stripe", "Platform Engineer")

    assert result == {"no_results": True}
    assert mock_get.await_count == 3
    llm.complete.assert_not_awaited()


async def test_search_uses_cache_without_extra_http_calls(research_service):
    service, llm = research_service
    html = (
        '<a class="result__a">Stripe interview prep</a>'
        '<a class="result__snippet">Expect coding plus design</a>'
    )
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [_Response(html), _Response(html), _Response(html)]
        llm.complete.return_value = json.dumps({
            "common_questions": ["Design a payment API"],
            "culture_notes": "Ownership-heavy",
            "interview_format": "Recruiter + loops",
            "tips": ["Clarify trade-offs"],
        })

        first = await service.search("Stripe", "Backend Engineer")
        second = await service.search("Stripe", "Backend Engineer")

    assert first == second
    assert mock_get.await_count == 3
    llm.complete.assert_awaited_once()


async def test_search_github_returns_structured_results(research_service):
    service, _ = research_service
    html = (
        '<a class="result__a">GitHub discussion: Stripe interview</a>'
        '<a class="result__snippet">People discuss bar raiser rounds</a>'
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=_Response(html)):
        results = await service._search_github("Stripe", "Backend Engineer")

    assert results == [
        {
            "title": "GitHub discussion: Stripe interview",
            "snippet": "People discuss bar raiser rounds",
        }
    ]


async def test_search_gathers_three_sources(research_service):
    service, llm = research_service
    html = (
        '<a class="result__a">Interview thread</a>'
        '<a class="result__snippet">Mix of coding and behavioral</a>'
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [_Response(html), _Response(html), _Response(html)]
        llm.complete.return_value = json.dumps({
            "common_questions": ["Tell me about yourself"],
            "culture_notes": "Ownership-heavy",
            "interview_format": "Screen + onsite",
            "tips": ["Be structured"],
        })

        result = await service.search("Stripe", "Engineer")

    assert result["no_results"] is False
    assert mock_get.await_count == 3


async def test_search_still_works_if_github_source_fails(research_service):
    service, llm = research_service
    html = (
        '<a class="result__a">Reddit: Stripe interview</a>'
        '<a class="result__snippet">System design and coding</a>'
    )

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = [
            _Response(html),
            _Response(html),
            httpx.TimeoutException("github timeout"),
        ]
        llm.complete.return_value = json.dumps({
            "common_questions": ["Design payment system"],
            "culture_notes": "Fast-paced and pragmatic",
            "interview_format": "Phone then onsite",
            "tips": ["Ask clarifying questions"],
        })

        result = await service.search("Stripe", "Engineer")

    assert result["no_results"] is False
    assert "common_questions" in result
    assert mock_get.await_count == 3
