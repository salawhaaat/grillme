import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import setup_logger
from app.models.session import InterviewSession
from app.services.jd import JDService
from app.services.llm import LLMService, RateLimitError, ProviderError

logger = setup_logger(__name__)
router = APIRouter(prefix="/api/sessions", tags=["sessions"])

llm = LLMService()
jd_service = JDService(llm=llm)


def _build_system_prompt(session: InterviewSession) -> str:
    base = (
        f"{session.persona}\n\n"
        f"You are conducting a technical mock interview for {session.role} at "
        f"{session.company} ({session.level} level).\n\n"
        "Rules: ask ONE question at a time, follow up on incomplete answers, "
        "stay in character throughout.\n\n"
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


class FromJDRequest(BaseModel):
    jd: str


class MessageRequest(BaseModel):
    content: str


class SessionResponse(BaseModel):
    id: int
    mode: str
    company: str | None
    role: str | None
    level: str | None
    persona: str | None
    scorecard: dict | None
    messages: list[dict]
    created_at: datetime
    finished_at: datetime | None


@router.post("/from-jd")
async def create_from_jd(
    body: FromJDRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        parsed, persona, question_bank = await jd_service.process_jd(body.jd)
    except Exception as e:
        logger.error("JD processing failed: %s", e)
        raise HTTPException(503, f"LLM processing failed: {e}") from e

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
        jd_raw=body.jd,
        company=parsed.get("company"),
        role=parsed.get("role"),
        level=parsed.get("level"),
        persona=persona,
        question_bank=json.dumps(question_bank),
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
        company=session.company,
        role=session.role,
        level=session.level,
        persona=session.persona,
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
        scorecard_raw = await jd_service.generate_scorecard(messages, session.persona or "")
    except Exception as e:
        logger.error("Scorecard generation failed: %s", e)
        raise HTTPException(503, f"Scorecard generation failed: {e}") from e

    session.scorecard = scorecard_raw
    session.finished_at = datetime.utcnow()
    await db.commit()

    return {"scorecard": json.loads(scorecard_raw)}
