"""CLI: Refresh company_questions.json by scraping configured GitHub sources.

Usage: python -m app.cli.refresh_questions
"""

import asyncio
import json

from app.services.github_scraper import GitHubScraper, RepoSource
from app.services.question_bank import DATA_PATH

SOURCES: dict[str, list[RepoSource]] = {
    "amazon": [
        RepoSource("swolecoder", "Amazon-Online-Assessment-Questions-LeetCode"),
        RepoSource("KushalVijay", "AmazonCrackedResource"),
        RepoSource("raleighlittles", "Amazon-SDE-Interview-Assessments"),
    ],
}


async def main() -> None:
    scraper = GitHubScraper()
    result: dict[str, list[dict]] = {}

    for company, sources in SOURCES.items():
        print(f"Scraping {company} from {len(sources)} sources...")
        entries = await scraper.scrape_company(company, sources)
        result[company] = [entry.model_dump() for entry in entries]
        print(f"  -> {len(entries)} unique problems")

    if DATA_PATH.exists():
        existing = json.loads(DATA_PATH.read_text())
        for key, value in existing.items():
            if key not in result:
                result[key] = value

    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_text(json.dumps(result, indent=2))
    print(f"Wrote {DATA_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
