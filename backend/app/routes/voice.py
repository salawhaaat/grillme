import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.session import InterviewSession
from app.services.tts import TTSService

router = APIRouter(prefix="/api/voice", tags=["voice"])
tts = TTSService()


class SpeakRequest(BaseModel):
    text: str
    voice: str = "en-US-GuyNeural"


@router.post("/speak")
async def speak(body: SpeakRequest) -> Response:
    audio = await tts.synthesize(text=body.text, voice=body.voice)
    return Response(content=audio, media_type="audio/mpeg")


@router.post("/speak-text")
async def speak_text(body: SpeakRequest) -> Response:
    audio = await tts.synthesize(text=body.text, voice=body.voice)
    return Response(content=audio, media_type="audio/mpeg")


@router.post("/speak-session/{session_id}")
async def speak_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    voice: str = "en-US-GuyNeural",
) -> Response:
    session = await db.get(InterviewSession, session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    messages = json.loads(session.messages) if session.messages else []
    latest_assistant = next(
        (message for message in reversed(messages) if message.get("role") == "assistant"),
        None,
    )
    if not latest_assistant or not latest_assistant.get("content"):
        raise HTTPException(404, "No assistant message found")

    audio = await tts.synthesize(text=latest_assistant["content"], voice=voice)
    return Response(content=audio, media_type="audio/mpeg")
