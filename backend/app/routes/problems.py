from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator
from app.services.scraper import ScraperService
from app.core.logging import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/api/problems", tags=["problems"])
scraper = ScraperService()


class ScrapeRequest(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def must_be_leetcode_url(cls, v: str) -> str:
        if "leetcode.com/problems/" not in v:
            raise ValueError("must be a leetcode.com/problems/ URL")
        return v


class ProblemResponse(BaseModel):
    title: str
    difficulty: str
    description: str


@router.post("/scrape", response_model=ProblemResponse)
async def scrape_problem(body: ScrapeRequest) -> ProblemResponse:
    logger.info("scraping %s", body.url)
    result = await scraper.scrape(body.url)
    if result is None:
        raise HTTPException(status_code=404, detail="Problem not found")
    return ProblemResponse(**result)
