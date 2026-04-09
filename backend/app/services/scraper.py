import re
import httpx
from app.core.logging import setup_logger

logger = setup_logger(__name__)

GRAPHQL_URL = "https://leetcode.com/graphql"
QUERY = """
query getQuestion($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    title
    difficulty
    content
  }
}
"""


class ScraperService:
    async def scrape(self, url: str) -> dict | None:
        slug = self._extract_slug(url)
        if not slug:
            return None

        async with httpx.AsyncClient() as client:
            response = await client.post(
                GRAPHQL_URL,
                json={"query": QUERY, "variables": {"titleSlug": slug}},
                headers={"Content-Type": "application/json"},
                timeout=10,
            )

        data = response.json().get("data", {}).get("question")
        if not data:
            return None

        return {
            "title": data["title"],
            "difficulty": data["difficulty"],
            "description": self._strip_html(data["content"] or ""),
        }

    def _extract_slug(self, url: str) -> str | None:
        match = re.search(r"leetcode\.com/problems/([\w-]+)", url)
        return match.group(1) if match else None

    def _strip_html(self, html: str) -> str:
        return re.sub(r"<[^>]+>", "", html).strip()
