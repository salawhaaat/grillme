from unittest.mock import AsyncMock, patch

import pytest

from app.services.github_scraper import GitHubScraper, RepoSource
from app.services.question_bank import QuestionEntry


def test_parse_readme_markdown_link_extracts_entry():
    scraper = GitHubScraper()
    markdown = "[Two Sum](https://leetcode.com/problems/two-sum/)"

    entries = scraper.parse_readme(markdown, "swolecoder")

    assert len(entries) == 1
    assert entries[0].title == "Two Sum"
    assert entries[0].slug == "two-sum"


def test_parse_readme_bare_url_derives_title_from_slug():
    scraper = GitHubScraper()
    markdown = "Practice: https://leetcode.com/problems/lru-cache/"

    entries = scraper.parse_readme(markdown, "swolecoder")

    assert len(entries) == 1
    assert entries[0].slug == "lru-cache"
    assert entries[0].title == "Lru Cache"


def test_parse_readme_strips_numeric_title_prefix():
    scraper = GitHubScraper()
    markdown = "[1. Two Sum](https://leetcode.com/problems/two-sum/)"

    entries = scraper.parse_readme(markdown, "swolecoder")

    assert len(entries) == 1
    assert entries[0].title == "Two Sum"


def test_parse_readme_dedupes_same_slug():
    scraper = GitHubScraper()
    markdown = """
    [Two Sum](https://leetcode.com/problems/two-sum/)
    https://leetcode.com/problems/two-sum/
    """

    entries = scraper.parse_readme(markdown, "swolecoder")

    assert len(entries) == 1
    assert entries[0].slug == "two-sum"


def test_merge_sources_sums_frequency_and_merges_sources():
    scraper = GitHubScraper()
    left = [
        QuestionEntry(
            title="Two Sum",
            slug="two-sum",
            difficulty="Unknown",
            frequency=1,
            sources=["swolecoder"],
            topics=[],
            last_seen="2024",
        )
    ]
    right = [
        QuestionEntry(
            title="Two Sum",
            slug="two-sum",
            difficulty="Unknown",
            frequency=1,
            sources=["KushalVijay"],
            topics=[],
            last_seen="2024",
        ),
        QuestionEntry(
            title="LRU Cache",
            slug="lru-cache",
            difficulty="Unknown",
            frequency=1,
            sources=["raleighlittles"],
            topics=[],
            last_seen="2024",
        ),
    ]

    merged = scraper.merge_sources([left, right])

    assert merged[0].slug == "two-sum"
    assert merged[0].frequency == 2
    assert set(merged[0].sources) == {"swolecoder", "KushalVijay"}


@pytest.mark.asyncio
async def test_fetch_readme_returns_text_when_200():
    scraper = GitHubScraper()
    source = RepoSource("owner", "repo")
    response = AsyncMock()
    response.status_code = 200
    response.text = "hello"

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=response):
        readme = await scraper.fetch_readme(source)

    assert readme == "hello"


@pytest.mark.asyncio
async def test_fetch_readme_falls_back_from_main_to_master():
    scraper = GitHubScraper()
    source = RepoSource("owner", "repo")

    first = AsyncMock()
    first.status_code = 404
    first.text = ""
    second = AsyncMock()
    second.status_code = 200
    second.text = "master readme"

    with patch(
        "httpx.AsyncClient.get",
        new_callable=AsyncMock,
        side_effect=[first, second],
    ):
        readme = await scraper.fetch_readme(source)

    assert readme == "master readme"


@pytest.mark.asyncio
async def test_fetch_readme_returns_none_when_all_fail():
    scraper = GitHubScraper()
    source = RepoSource("owner", "repo")

    first = AsyncMock()
    first.status_code = 404
    first.text = ""
    second = AsyncMock()
    second.status_code = 404
    second.text = ""

    with patch(
        "httpx.AsyncClient.get",
        new_callable=AsyncMock,
        side_effect=[first, second],
    ):
        readme = await scraper.fetch_readme(source)

    assert readme is None


@pytest.mark.asyncio
async def test_scrape_company_merges_results():
    scraper = GitHubScraper()
    sources = [RepoSource("swolecoder", "a"), RepoSource("KushalVijay", "b")]
    markdown_one = "[Two Sum](https://leetcode.com/problems/two-sum/)"
    markdown_two = """
    [Two Sum](https://leetcode.com/problems/two-sum/)
    [LRU Cache](https://leetcode.com/problems/lru-cache/)
    """

    with patch.object(
        scraper,
        "fetch_readme",
        new_callable=AsyncMock,
        side_effect=[markdown_one, markdown_two],
    ):
        entries = await scraper.scrape_company("amazon", sources)

    by_slug = {entry.slug: entry for entry in entries}
    assert by_slug["two-sum"].frequency == 2
    assert set(by_slug["two-sum"].sources) == {"swolecoder", "KushalVijay"}
    assert by_slug["lru-cache"].frequency == 1
