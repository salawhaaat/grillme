import asyncio
import re
from dataclasses import dataclass
from typing import Iterable

import httpx

from app.core.logging import setup_logger
from app.services.question_bank import QuestionEntry

logger = setup_logger(__name__)

LEETCODE_LINK = re.compile(
    r"(?:leetcode\.com/problems/)([a-z0-9\-]+)",
    re.IGNORECASE,
)
MARKDOWN_LINK = re.compile(
    r"\[([^\]]+)\]\(([^)]*leetcode\.com/problems/[^)]+)\)",
    re.IGNORECASE,
)


@dataclass
class RepoSource:
    owner: str
    repo: str

    @property
    def raw_readme_urls(self) -> list[str]:
        """Try main branch first, then master."""
        return [
            f"https://raw.githubusercontent.com/{self.owner}/{self.repo}/main/README.md",
            f"https://raw.githubusercontent.com/{self.owner}/{self.repo}/master/README.md",
        ]


class GitHubScraper:
    async def fetch_readme(self, source: RepoSource, timeout: int = 15) -> str | None:
        """Try each candidate URL, return the first one that succeeds."""
        async with httpx.AsyncClient() as client:
            for url in source.raw_readme_urls:
                try:
                    resp = await client.get(url, timeout=timeout)
                    if resp.status_code == 200 and resp.text.strip():
                        return resp.text
                except httpx.HTTPError as exc:
                    logger.warning("Failed to fetch %s: %s", url, exc)
        return None

    def parse_readme(self, markdown: str, source_name: str) -> list[QuestionEntry]:
        """Extract LeetCode problem entries from README markdown."""
        seen: dict[str, QuestionEntry] = {}

        for match in MARKDOWN_LINK.finditer(markdown):
            title = match.group(1).strip()
            url = match.group(2).strip()
            slug_match = LEETCODE_LINK.search(url)
            if not slug_match:
                continue
            slug = slug_match.group(1).lower()
            if slug in seen:
                continue
            seen[slug] = QuestionEntry(
                title=self._clean_title(title),
                slug=slug,
                difficulty="Unknown",
                frequency=1,
                sources=[source_name],
                topics=[],
                last_seen="2024",
            )

        for match in LEETCODE_LINK.finditer(markdown):
            slug = match.group(1).lower()
            if slug in seen:
                continue
            seen[slug] = QuestionEntry(
                title=slug.replace("-", " ").title(),
                slug=slug,
                difficulty="Unknown",
                frequency=1,
                sources=[source_name],
                topics=[],
                last_seen="2024",
            )

        return list(seen.values())

    def _clean_title(self, title: str) -> str:
        title = re.sub(r"^\s*[\d]+\.\s*", "", title)
        title = re.sub(r"^\s*[-*]\s*", "", title)
        return title.strip()

    def merge_sources(self, lists: Iterable[list[QuestionEntry]]) -> list[QuestionEntry]:
        """Merge entries from multiple sources, deduping by slug and summing frequency."""
        merged: dict[str, QuestionEntry] = {}
        for entries in lists:
            for entry in entries:
                if entry.slug in merged:
                    existing = merged[entry.slug]
                    existing.frequency += 1
                    for src in entry.sources:
                        if src not in existing.sources:
                            existing.sources.append(src)
                else:
                    merged[entry.slug] = entry.model_copy()

        return sorted(merged.values(), key=lambda entry: entry.frequency, reverse=True)

    async def scrape_company(
        self, company: str, sources: list[RepoSource]
    ) -> list[QuestionEntry]:
        """Fetch all source repos for a company and merge the results."""
        fetched = await asyncio.gather(
            *(self.fetch_readme(source) for source in sources),
            return_exceptions=True,
        )
        parsed: list[list[QuestionEntry]] = []
        for source, result in zip(sources, fetched):
            if isinstance(result, Exception) or result is None:
                logger.warning("Skipping %s/%s", source.owner, source.repo)
                continue
            parsed.append(self.parse_readme(result, source.owner))
        return self.merge_sources(parsed)
