import asyncio
import json
import re
from urllib.parse import quote_plus

import httpx

from app.core.logging import setup_logger
from app.services.llm import LLMService

logger = setup_logger(__name__)

_cache: dict[str, dict] = {}

TITLE_PATTERN = re.compile(r'<a[^>]*class="[^"]*\bresult__a\b[^"]*"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
SNIPPET_PATTERN = re.compile(r'<a[^>]*class="[^"]*\bresult__snippet\b[^"]*"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
TAG_PATTERN = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", TAG_PATTERN.sub("", text)).strip()


class ResearchService:
    def __init__(self, llm: LLMService) -> None:
        self.llm = llm

    async def _search_source(self, query: str, timeout: int = 10) -> list[dict[str, str]]:
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=timeout)
            response.raise_for_status()

        titles = [_strip_html(m) for m in TITLE_PATTERN.findall(response.text)]
        snippets = [_strip_html(m) for m in SNIPPET_PATTERN.findall(response.text)]
        count = min(len(titles), len(snippets))
        return [{"title": titles[i], "snippet": snippets[i]} for i in range(count)]

    async def search(self, company: str, role: str) -> dict:
        cache_key = f"{company}|{role}"
        if cache_key in _cache:
            return _cache[cache_key]

        reddit_query = f"site:reddit.com {company} {role} interview experience"
        glassdoor_query = f"site:glassdoor.com {company} interview questions"

        source_results = await asyncio.gather(
            self._search_source(reddit_query, timeout=10),
            self._search_source(glassdoor_query, timeout=10),
            return_exceptions=True,
        )

        merged_results: list[dict[str, str]] = []
        for result in source_results:
            if isinstance(result, Exception):
                logger.warning("Research source failed: %s", result)
                continue
            merged_results.extend(result)

        if not merged_results:
            result = {"no_results": True}
            _cache[cache_key] = result
            return result

        messages = [
            {
                "role": "system",
                "content": (
                    "Summarize these interview experiences into structured intel. "
                    "Return JSON with keys: common_questions (list[str]), "
                    "culture_notes (str), interview_format (str), tips (list[str])."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(merged_results),
            },
        ]

        try:
            summary_raw = await self.llm.complete(messages, json_mode=True)
            summary = json.loads(summary_raw)
            summary["no_results"] = False
            _cache[cache_key] = summary
            return summary
        except Exception as e:
            logger.warning("Research summarization failed: %s", e)
            fallback = {"no_results": False, "raw_results": merged_results}
            _cache[cache_key] = fallback
            return fallback
