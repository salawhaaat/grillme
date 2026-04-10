import json
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import setup_logger
from app.agents.orchestrator import Orchestrator
from app.models.problem import Problem
from app.models.session import InterviewSession
from app.services.llm import LLMService, RateLimitError, ProviderError
from app.services.scraper import ScraperService

logger = setup_logger(__name__)
router = APIRouter(prefix="/api/sessions", tags=["sessions"])

llm = LLMService()
orchestrator = Orchestrator(llm=llm)
scraper = ScraperService()

DIFFICULTY_INSTRUCTIONS: dict[str, str] = {
    "rare": (
        "DIFFICULTY — RARE: Be warm and encouraging like a patient mentor. "
        "If the candidate seems stuck or has not made clear progress within 2 exchanges, "
        "proactively offer a specific hint framed as 'one thing to consider…'. "
        "Never let them flounder for more than 2 messages without a nudge."
    ),
    "medium": (
        "DIFFICULTY — MEDIUM: Provide hints only if the candidate explicitly asks for help. "
        "Offer at most one focused hint per question. Maintain a professional, neutral tone."
    ),
    "well_done": (
        "DIFFICULTY — WELL DONE: Never volunteer hints under any circumstances. "
        "If an answer is incomplete or incorrect, express professional dissatisfaction and "
        "push back with a sharper follow-up question. Challenge every assumption. "
        "Make the candidate rigorously justify their reasoning. "
        "You may interrupt with clarifying questions to expose gaps. "
        "This is a high-bar interview — fail candidates who do not meet the bar."
    ),
}


def _build_system_prompt(session: InterviewSession) -> str:
    difficulty_block = DIFFICULTY_INSTRUCTIONS.get(session.difficulty or "medium", DIFFICULTY_INSTRUCTIONS["medium"])

    base = (
        f"{session.persona}\n\n"
        f"You are conducting a technical mock interview for {session.role} at "
        f"{session.company} ({session.level} level).\n\n"
        "Rules: ask ONE question at a time, follow up on incomplete answers, "
        "stay in character throughout.\n\n"
        f"{difficulty_block}\n\n"
    )
    if not session.question_bank:
        return base

    qb = json.loads(session.question_bank)
    coding = qb.get("coding", {})
    coding_line = (
        f"  Coding round ({coding.get('type', 'leetcode')}): {coding.get('topic', '')}"
    )
    structure = (
        "Follow this interview structure in order:\n"
        f"1. Warmup (2 questions): {' | '.join(qb.get('warmup', []))}\n"
        f"2. Technical trivia (4 questions): {' | '.join(qb.get('trivia', []))}\n"
        f"3. Culture fit (2 questions): {' | '.join(qb.get('culture_fit', []))}\n"
        f"4. {coding_line}\n\n"
        "Progress through sections naturally. Do not skip sections."
    )
    return base + structure


# ── Request / Response models ──────────────────────────────────────────────

class FromJDRequest(BaseModel):
    jd: str
    difficulty: Literal["rare", "medium", "well_done"] = "medium"

    @field_validator("jd")
    @classmethod
    def jd_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("jd must not be empty")
        return v


class FromProblemRequest(BaseModel):
    problem_url: str
    difficulty: Literal["rare", "medium", "well_done"] = "medium"

    @field_validator("problem_url")
    @classmethod
    def url_is_leetcode(cls, v: str) -> str:
        if "leetcode.com/problems/" not in v:
            raise ValueError("problem_url must be a leetcode.com/problems/ URL")
        return v


class MessageRequest(BaseModel):
    content: str


class SessionResponse(BaseModel):
    id: int
    mode: str
    difficulty: str
    company: str | None
    role: str | None
    level: str | None
    persona: str | None
    prep_plan: str | None
    oa_platform: str | None
    problem_url: str | None
    scorecard: dict | None
    messages: list[dict]
    created_at: datetime
    finished_at: datetime | None


class SessionListItem(BaseModel):
    id: int
    mode: str
    difficulty: str
    company: str | None
    role: str | None
    level: str | None
    oa_platform: str | None
    overall_score: int | None
    message_count: int
    created_at: datetime
    finished_at: datetime | None


# ── Routes ─────────────────────────────────────────────────────────────────

@router.get("/", response_model=list[SessionListItem])
async def list_sessions(db: AsyncSession = Depends(get_db)) -> list[SessionListItem]:
    result = await db.execute(
        select(InterviewSession).order_by(InterviewSession.created_at.desc())
    )
    sessions = result.scalars().all()

    items = []
    for s in sessions:
        score: int | None = None
        if s.scorecard:
            try:
                score = json.loads(s.scorecard).get("overall_score")
            except (json.JSONDecodeError, AttributeError):
                pass

        messages = json.loads(s.messages) if s.messages else []
        items.append(SessionListItem(
            id=s.id,
            mode=s.mode,
            difficulty=s.difficulty or "medium",
            company=s.company,
            role=s.role,
            level=s.level,
            oa_platform=s.oa_platform,
            overall_score=score,
            message_count=len(messages),
            created_at=s.created_at,
            finished_at=s.finished_at,
        ))
    return items


@router.post("/from-jd")
async def create_from_jd(
    body: FromJDRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        result = await orchestrator.run_jd_pipeline(body.jd)
        parsed = result.parsed_jd.model_dump()
        persona = result.persona.persona_text
        question_bank = result.persona.question_bank.model_dump()
        prep_plan = result.persona.prep_plan
        oa_platform = result.persona.oa_platform
    except Exception as e:
        logger.error("JD processing failed: %s", e)
        raise HTTPException(503, f"LLM processing failed: {e}") from e

    prep_plan_with_oa = prep_plan
    if oa_platform:
        prep_plan_with_oa = (
            f"{prep_plan}\n\n"
            f"The company uses {oa_platform} for online assessments. Include platform-specific tips."
        )

    opening = await llm.complete([
        {
            "role": "system",
            "content": (
                f"{persona}\n\n"
                f"You are interviewing a candidate for {parsed.get('role')} at {parsed.get('company')} "
                f"({parsed.get('level')} level). "
                "Give a one-sentence introduction as yourself, then ask your first warmup question. "
                "Be direct. No preamble, no agenda, no prep tips."
            ),
        },
        {"role": "user", "content": "Begin."},
    ])

    session = InterviewSession(
        mode="jd",
        difficulty=body.difficulty,
        jd_raw=body.jd,
        company=parsed.get("company"),
        role=parsed.get("role"),
        level=parsed.get("level"),
        persona=persona,
        question_bank=json.dumps(question_bank),
        prep_plan=prep_plan_with_oa,
        oa_platform=oa_platform,
        messages=json.dumps([{"role": "assistant", "content": opening}]),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    return {
        "session_id": session.id,
        "company": session.company,
        "role": session.role,
        "level": session.level,
        "difficulty": session.difficulty,
        "prep_plan": session.prep_plan,
        "oa_platform": session.oa_platform,
        "opening_message": opening,
    }


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    session = await db.get(InterviewSession, session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    return SessionResponse(
        id=session.id,
        mode=session.mode,
        difficulty=session.difficulty or "medium",
        company=session.company,
        role=session.role,
        level=session.level,
        persona=session.persona,
        prep_plan=session.prep_plan,
        oa_platform=session.oa_platform,
        problem_url=session.problem_url,
        scorecard=json.loads(session.scorecard) if session.scorecard else None,
        messages=json.loads(session.messages),
        created_at=session.created_at,
        finished_at=session.finished_at,
    )


@router.post("/{session_id}/message")
async def send_message(
    session_id: int,
    body: MessageRequest,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    session = await db.get(InterviewSession, session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    messages = json.loads(session.messages)
    messages.append({"role": "user", "content": body.content})

    system_prompt = _build_system_prompt(session)
    llm_messages = [{"role": "system", "content": system_prompt}] + messages

    async def generate():
        collected: list[str] = []
        try:
            async for chunk in llm.stream_chat(llm_messages):
                collected.append(chunk)
                yield chunk
        except RateLimitError:
            yield "\n\n[error:429] LLM quota exceeded — try again later"
            return
        except (ProviderError, ValueError) as e:
            yield f"\n\n[error:503] {e}"
            return

        messages.append({"role": "assistant", "content": "".join(collected)})
        session.messages = json.dumps(messages)
        await db.commit()

    return StreamingResponse(generate(), media_type="text/plain")


@router.post("/from-problem")
async def create_from_problem(
    body: FromProblemRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    cached = await db.execute(select(Problem).where(Problem.url == body.problem_url))
    cached_problem = cached.scalar_one_or_none()
    if cached_problem:
        problem = {
            "title": cached_problem.title,
            "difficulty": cached_problem.difficulty,
            "description": cached_problem.description,
        }
    else:
        problem = await scraper.scrape(body.problem_url)
        if not problem:
            raise HTTPException(422, "Could not scrape problem — check the URL")

        existing = await db.execute(select(Problem).where(Problem.url == body.problem_url))
        if not existing.scalar_one_or_none():
            db.add(Problem(
                title=problem["title"],
                difficulty=problem["difficulty"],
                url=body.problem_url,
                description=problem["description"],
            ))

    try:
        persona = await orchestrator.build_problem_persona(problem)
    except Exception as e:
        logger.error("Persona generation failed: %s", e)
        raise HTTPException(503, f"LLM processing failed: {e}") from e

    opening = await llm.complete([
        {
            "role": "system",
            "content": (
                f"{persona}\n\n"
                f"You are starting a coding interview. Present this problem clearly, "
                f"then ask the candidate to walk you through their initial approach "
                f"before writing any code.\n\n"
                f"Problem: {problem['title']}\n\n{problem['description']}"
            ),
        },
        {"role": "user", "content": "Begin."},
    ])

    session = InterviewSession(
        mode="problem",
        difficulty=body.difficulty,
        company="Technical Interview",
        role="Software Engineer",
        level="mid",
        persona=persona,
        problem_url=body.problem_url,
        question_bank=json.dumps({
            "warmup": [],
            "trivia": [],
            "culture_fit": [],
            "coding": {"type": "leetcode", "topic": problem["title"], "hints": []},
        }),
        messages=json.dumps([{"role": "assistant", "content": opening}]),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    return {
        "session_id": session.id,
        "problem_title": problem["title"],
        "problem_difficulty": problem["difficulty"],
        "difficulty": session.difficulty,
        "opening_message": opening,
    }


@router.post("/{session_id}/finish")
async def finish_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    session = await db.get(InterviewSession, session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    messages = json.loads(session.messages)
    try:
        scorecard_result = await orchestrator.run_scoring(messages, session.persona or "")
        scorecard_raw = scorecard_result.model_dump_json()
    except Exception as e:
        logger.error("Scorecard generation failed: %s", e)
        raise HTTPException(503, f"Scorecard generation failed: {e}") from e

    session.scorecard = scorecard_raw
    session.finished_at = datetime.utcnow()
    await db.commit()

    return {"scorecard": json.loads(scorecard_raw)}
