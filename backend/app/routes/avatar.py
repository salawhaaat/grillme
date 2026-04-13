from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.session import InterviewSession
from app.services.avatar import AvatarService

router = APIRouter(prefix="/api/avatar", tags=["avatar"])
avatar_service = AvatarService()


@router.get("/session/{session_id}")
async def get_avatar_session(
    session_id: int,
    db: AsyncSession = Depends(get_db),
) -> dict:
    session = await db.get(InterviewSession, session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    return await avatar_service.create_session(
        persona=session.persona,
        session_id=session.id,
    )


class AvatarSpeakRequest(BaseModel):
    text: str

    @field_validator("text")
    @classmethod
    def text_not_empty(cls, v: str) -> str:
        val = v.strip()
        if not val:
            raise ValueError("text must not be empty")
        return val


@router.post("/session/{session_id}/speak-video")
async def create_avatar_speak_video(
    session_id: int,
    body: AvatarSpeakRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    session = await db.get(InterviewSession, session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    return await avatar_service.create_talking_head_video(
        persona=session.persona,
        session_id=session.id,
        text=body.text,
    )


@router.get("/video/{filename}")
async def serve_avatar_video(filename: str) -> FileResponse:
    # Reject path traversal attempts
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(400, "Invalid filename")
    video_path = Path(settings.videos_dir) / filename
    if not video_path.exists():
        raise HTTPException(404, "Video not found")
    return FileResponse(video_path, media_type="video/mp4")
