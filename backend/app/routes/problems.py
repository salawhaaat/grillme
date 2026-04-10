from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.services.scraper import ScraperService
from app.core.logging import setup_logger
from app.models.problem import Problem

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


class ProblemItem(BaseModel):
    id: int
    title: str
    difficulty: str
    url: str
    scraped_at: datetime


@router.post("/scrape", response_model=ProblemResponse)
async def scrape_problem(body: ScrapeRequest) -> ProblemResponse:
    logger.info("scraping %s", body.url)
    result = await scraper.scrape(body.url)
    if result is None:
        raise HTTPException(status_code=404, detail="Problem not found")
    return ProblemResponse(**result)


@router.get("", response_model=list[ProblemItem])
async def list_problems(
    q: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[ProblemItem]:
    stmt = select(Problem)
    if q:
        stmt = stmt.where(Problem.title.ilike(f"%{q}%"))
    stmt = stmt.order_by(Problem.scraped_at.desc())

    result = await db.execute(stmt)
    problems = result.scalars().all()
    return [
        ProblemItem(
            id=problem.id,
            title=problem.title,
            difficulty=problem.difficulty,
            url=problem.url,
            scraped_at=problem.scraped_at,
        )
        for problem in problems
    ]
