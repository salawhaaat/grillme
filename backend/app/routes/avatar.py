import re
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.session import InterviewSession
from app.services.avatar import avatar_service

router = APIRouter(prefix="/api/avatar", tags=["avatar"])


@router.get("/session/{session_id}/intro")
async def get_intro_status(session_id: int) -> dict:
    """Poll this until ready=true, then play the video_url as a <video> element."""
    return avatar_service.get_intro_status(session_id)


@router.get("/job/{job_id}")
async def get_video_job(job_id: str) -> dict:
    """Poll this until status=done, then play the video_url as a <video> element."""
    return avatar_service.get_job_status(job_id)


@router.get("/smalltalk")
async def get_smalltalk_clips() -> dict:
    """Return list of pre-rendered smalltalk clip URLs for immediate playback."""
    return {"clips": avatar_service.get_smalltalk_urls()}


@router.get("/scenarios")
async def get_scenario_manifest_endpoint() -> dict:
    return avatar_service.get_scenario_manifest()


@router.get("/prerender-status")
async def get_prerender_status() -> dict:
    """Return pre-render progress for the frontend setup banner."""
    return avatar_service.get_prerender_status()


@router.get("/intro-clip")
async def get_intro_clip() -> dict:
    """Return a random pre-rendered intro clip URL for immediate playback on session load."""
    return avatar_service.get_intro_clip()


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


@router.get("/video/{filename:path}")
async def serve_avatar_video(filename: str) -> FileResponse:
    if ".." in filename:
        raise HTTPException(400, "Invalid filename")
    if "/" in filename:
        if not re.match(r"^scenarios/[a-z_]+_\d+\.mp4$", filename):
            raise HTTPException(400, "Invalid filename")
    elif "\\" in filename:
        raise HTTPException(400, "Invalid filename")
    video_path = Path(settings.videos_dir) / filename
    if not video_path.exists():
        raise HTTPException(404, "Video not found")
    return FileResponse(video_path, media_type="video/mp4")
