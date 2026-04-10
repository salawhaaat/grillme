import json
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import setup_logger
from app.agents.memory import MemoryAgent
from app.agents.orchestrator import Orchestrator
from app.agents.schemas import CodingProblem, ScorecardResult
from app.models.problem import Problem
from app.models.session import InterviewSession
from app.models.user_memory import UserMemory
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


def _estimate_text_tokens(text: str | None) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


def _estimate_messages_tokens(messages: list[dict]) -> int:
    return sum(_estimate_text_tokens(str(m.get("content", ""))) for m in messages)


def _apply_usage(session: InterviewSession, prompt_tokens: int, completion_tokens: int) -> None:
    session.prompt_tokens = (session.prompt_tokens or 0) + max(0, prompt_tokens)
    session.completion_tokens = (session.completion_tokens or 0) + max(0, completion_tokens)
    session.total_tokens = (session.total_tokens or 0) + max(0, prompt_tokens + completion_tokens)


def _cv_context(cv_text: str | None) -> str:
    if not cv_text:
        return ""
    return cv_text[:3000]


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
    if session.cv_text:
        base += (
            "Candidate CV context (use only these facts for personalized follow-ups):\n"
            f"{_cv_context(session.cv_text)}\n\n"
        )
    if session.full_problem:
        base += (
            "\n\nFULL PROBLEM (the candidate sees a CUT version without examples/constraints):\n"
            f"{session.full_problem}\n\n"
            f"The candidate has starter code:\n```python\n{session.starter_code or ''}\n```\n\n"
            "RULES FOR THIS INTERVIEW:\n"
            "- Only reveal examples, constraints, or edge cases when the candidate ASKS about them.\n"
            "- If they don't ask and start coding, silently note it (it will affect their curiosity score).\n"
            "- React to their code and test results when they share them.\n"
            "- Near the end (after they solve or give up), wrap with 'That's all from me — do you have any questions for me?'\n"
        )
    messages = json.loads(session.messages) if session.messages else []
    latest_code_block = None
    for m in reversed(messages):
        if m.get("content", "").startswith("[CODE UPDATE]"):
            latest_code_block = m["content"]
            break
    if latest_code_block:
        base += f"\n\nLATEST CODE FROM CANDIDATE:\n{latest_code_block}\n"
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
        "5. Closing: ask the candidate 'Do you have any questions for me?' and discuss their questions.\n\n"
        "Progress through sections naturally. Do not skip sections. "
        "In the closing part, encourage strong candidate-style questions that show curiosity about "
        "the team, the problems they are solving, and what matters most in the role."
    )
    return base + structure


# ── Request / Response models ──────────────────────────────────────────────

class FromJDRequest(BaseModel):
    jd: str
    cv_text: str | None = None
    difficulty: Literal["rare", "medium", "well_done"] = "medium"

    @field_validator("jd")
    @classmethod
    def jd_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("jd must not be empty")
        return v

    @field_validator("cv_text")
    @classmethod
    def cv_size_guard(cls, v: str | None) -> str | None:
        if v is None:
            return None
        trimmed = v.strip()
        if not trimmed:
            return None
        if len(trimmed) > 20000:
            raise ValueError("cv_text is too long")
        return trimmed


class FromProblemRequest(BaseModel):
    problem_url: str
    difficulty: Literal["rare", "medium", "well_done"] = "medium"

    @field_validator("problem_url")
    @classmethod
    def url_is_leetcode(cls, v: str) -> str:
        if "leetcode.com/problems/" not in v:
            raise ValueError("problem_url must be a leetcode.com/problems/ URL")
        return v


class CreateSessionRequest(BaseModel):
    source: Literal["jd", "url", "text"]
    content: str
    difficulty: Literal["rare", "medium", "well_done"] = "medium"

    @field_validator("content")
    @classmethod
    def content_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("content must not be empty")
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
    cv_text: str | None
    oa_platform: str | None
    problem_url: str | None
    problem_statement: str | None = None
    starter_code: str | None = None
    test_cases: dict | None = None
    method_name: str | None = None
    scorecard: dict | None
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
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
    total_tokens: int
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
            total_tokens=s.total_tokens or 0,
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
    weakness_rows = await db.execute(
        select(UserMemory).order_by(UserMemory.frequency.desc()).limit(5)
    )
    user_weaknesses = [w.area for w in weakness_rows.scalars().all()]

    try:
        result = await orchestrator.run_jd_pipeline(
            body.jd, user_weaknesses=user_weaknesses
        )
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

    opening_messages = [
        {
            "role": "system",
            "content": (
                f"{persona}\n\n"
                f"You are interviewing a candidate for {parsed.get('role')} at {parsed.get('company')} "
                f"({parsed.get('level')} level). "
                f"{'Candidate CV context:\\n' + _cv_context(body.cv_text) + '\\n\\n' if body.cv_text else ''}"
                "Give a one-sentence introduction as yourself, then ask your first warmup question. "
                "Be direct. No preamble, no agenda, no prep tips."
            ),
        },
        {"role": "user", "content": "Begin."},
    ]
    opening = await llm.complete(opening_messages)

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
        cv_text=body.cv_text,
        oa_platform=oa_platform,
        messages=json.dumps([{"role": "assistant", "content": opening}]),
    )
    _apply_usage(
        session,
        prompt_tokens=_estimate_messages_tokens(opening_messages),
        completion_tokens=_estimate_text_tokens(opening),
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


@router.post("/create")
async def create_session(
    body: CreateSessionRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    weakness_rows = await db.execute(
        select(UserMemory).order_by(UserMemory.frequency.desc()).limit(5)
    )
    user_weaknesses = [w.area for w in weakness_rows.scalars().all()]

    try:
        result = await orchestrator.run_interview_pipeline(
            source=body.source,
            content=body.content,
            difficulty=body.difficulty,
            user_weaknesses=user_weaknesses,
        )
    except Exception as e:
        logger.error("Interview pipeline failed: %s", e)
        raise HTTPException(503, f"Pipeline failed: {e}") from e

    problem = result.problem
    persona = result.persona
    parsed = result.parsed_jd

    opening_messages = [
        {
            "role": "system",
            "content": (
                f"{persona.persona_text}\n\n"
                "You are about to present a coding problem. State the problem in 2-3 sentences, "
                "then WAIT. Do NOT ask 'any questions?' — do NOT hint that clarifying questions are expected. "
                "Simply present the cut problem and stop."
            ),
        },
        {
            "role": "user",
            "content": f"Present this problem:\n{problem.problem_statement}",
        },
    ]
    opening = await llm.complete(opening_messages)

    session = InterviewSession(
        mode=body.source,
        difficulty=body.difficulty,
        jd_raw=body.content if body.source == "jd" else None,
        problem_url=body.content if body.source == "url" else None,
        company=parsed.company if parsed else None,
        role=parsed.role if parsed else None,
        level=parsed.level if parsed else None,
        persona=persona.persona_text,
        oa_platform=persona.oa_platform,
        problem_statement=problem.problem_statement,
        full_problem=problem.full_problem,
        starter_code=problem.starter_code,
        test_cases=json.dumps({
            "method_name": problem.method_name,
            "test_cases": problem.test_cases,
        }),
        method_name=problem.method_name,
        messages=json.dumps([{"role": "assistant", "content": opening}]),
    )
    _apply_usage(
        session,
        prompt_tokens=_estimate_messages_tokens(opening_messages),
        completion_tokens=_estimate_text_tokens(opening),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    return {
        "session_id": session.id,
        "source": body.source,
        "difficulty": body.difficulty,
        "company": session.company,
        "role": session.role,
        "level": session.level,
        "problem": {
            "title": problem.title,
            "difficulty": problem.difficulty,
            "statement": problem.problem_statement,
            "method_name": problem.method_name,
        },
        "starter_code": problem.starter_code,
        "opening_message": opening,
    }


@router.get("/memory")
async def get_user_memory(db: AsyncSession = Depends(get_db)) -> list[dict]:
    result = await db.execute(
        select(UserMemory).order_by(UserMemory.frequency.desc())
    )
    memories = result.scalars().all()
    return [
        {
            "area": m.area,
            "frequency": m.frequency,
            "last_session_id": m.last_session_id,
        }
        for m in memories
    ]


@router.delete("/")
async def clear_sessions_history(db: AsyncSession = Depends(get_db)) -> dict:
    session_result = await db.execute(delete(InterviewSession))
    memory_result = await db.execute(delete(UserMemory))
    await db.commit()
    return {
        "deleted_sessions": session_result.rowcount or 0,
        "deleted_memory_rows": memory_result.rowcount or 0,
    }


@router.delete("/{session_id}")
async def delete_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    session = await db.get(InterviewSession, session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    memory_rows = await db.execute(
        select(UserMemory).where(UserMemory.last_session_id == session_id)
    )
    for row in memory_rows.scalars().all():
        row.last_session_id = None

    await db.delete(session)
    await db.commit()
    return {"deleted_session_id": session_id}


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
        cv_text=session.cv_text,
        oa_platform=session.oa_platform,
        problem_url=session.problem_url,
        problem_statement=session.problem_statement,
        starter_code=session.starter_code,
        test_cases=json.loads(session.test_cases) if session.test_cases else None,
        method_name=session.method_name,
        scorecard=json.loads(session.scorecard) if session.scorecard else None,
        prompt_tokens=session.prompt_tokens or 0,
        completion_tokens=session.completion_tokens or 0,
        total_tokens=session.total_tokens or 0,
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
        assistant_text = "".join(collected)
        _apply_usage(
            session,
            prompt_tokens=_estimate_messages_tokens(llm_messages),
            completion_tokens=_estimate_text_tokens(assistant_text),
        )
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

    opening_messages = [
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
    ]
    opening = await llm.complete(opening_messages)

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
    _apply_usage(
        session,
        prompt_tokens=_estimate_messages_tokens(opening_messages),
        completion_tokens=_estimate_text_tokens(opening),
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
        problem_obj = None
        if session.test_cases:
            tc = json.loads(session.test_cases)
            problem_obj = CodingProblem(
                title=session.company or "Problem",
                difficulty=session.difficulty or "medium",
                problem_statement=session.problem_statement or "",
                full_problem=session.full_problem or "",
                starter_code=session.starter_code or "",
                test_cases=tc.get("test_cases", []),
                method_name=tc.get("method_name", ""),
            )
        scorecard_v2 = await orchestrator.run_six_axis_scoring(
            messages=messages,
            persona=session.persona or "",
            problem=problem_obj,
        )
        scorecard_raw = scorecard_v2.model_dump_json()
    except Exception as e:
        logger.error("Six-axis scoring failed, falling back to legacy scorer: %s", e)
        try:
            scorecard_result = await orchestrator.run_scoring(messages, session.persona or "")
            scorecard_raw = scorecard_result.model_dump_json()
        except Exception as inner:
            logger.error("Scorecard generation failed: %s", inner)
            raise HTTPException(503, f"Scorecard generation failed: {inner}") from inner

    session.scorecard = scorecard_raw
    session.finished_at = datetime.now(UTC)
    score_prompt_tokens = (_estimate_messages_tokens(messages) + _estimate_text_tokens(session.persona or "")) * 2
    score_completion_tokens = _estimate_text_tokens(scorecard_raw) * 2
    _apply_usage(
        session,
        prompt_tokens=score_prompt_tokens,
        completion_tokens=score_completion_tokens,
    )
    await db.commit()

    try:
        memory_agent = MemoryAgent(llm)
        scorecard_data = json.loads(scorecard_raw) if isinstance(scorecard_raw, str) else scorecard_raw
        scorecard_obj = (
            ScorecardResult(**scorecard_data)
            if isinstance(scorecard_data, dict)
            else scorecard_data
        )
        tags = await memory_agent.extract_weaknesses(scorecard_obj)

        for tag in tags:
            existing = await db.execute(select(UserMemory).where(UserMemory.area == tag))
            row = existing.scalar_one_or_none()
            if row:
                row.frequency += 1
                row.last_session_id = session.id
                row.updated_at = datetime.now(UTC)
            else:
                db.add(UserMemory(area=tag, last_session_id=session.id))
        await db.commit()
    except Exception as e:
        logger.warning("Memory extraction failed: %s", e)

    return {"scorecard": json.loads(scorecard_raw)}
