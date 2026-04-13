import hashlib
import uuid
from pathlib import Path

import httpx

from app.core.config import settings
from app.core.logging import setup_logger

logger = setup_logger(__name__)


class AvatarService:
    @staticmethod
    def _is_wav2lip_enabled() -> bool:
        return settings.avatar_provider == "wav2lip" and bool(settings.avatar_service_url)

    @staticmethod
    def _videos_dir() -> Path:
        d = Path(settings.videos_dir)
        d.mkdir(parents=True, exist_ok=True)
        return d

    async def create_session(self, persona: str | None, session_id: int) -> dict:
        persona_text = persona or "AI Interviewer"
        persona_seed = hashlib.sha1(f"{session_id}:{persona_text}".encode()).hexdigest()[:12]

        if self._is_wav2lip_enabled():
            return {"enabled": True, "provider": "wav2lip", "persona_seed": persona_seed}

        return {
            "enabled": False,
            "provider": "local",
            "persona_seed": persona_seed,
            "reason": "Set AVATAR_PROVIDER=wav2lip and start the avatar-service",
        }

    async def create_talking_head_video(
        self,
        *,
        persona: str | None,
        session_id: int,
        text: str,
        voice: str = "en-US-JennyNeural",
    ) -> dict:
        if not text.strip():
            return {"enabled": False, "provider": "local", "reason": "Empty text"}

        session_meta = await self.create_session(persona=persona, session_id=session_id)
        if not session_meta.get("enabled"):
            return session_meta

        url = settings.avatar_service_url.rstrip("/") + "/generate"
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                res = await client.post(url, json={"text": text, "voice": voice})
                if res.status_code == 503:
                    detail = res.json().get("detail", "avatar service not ready")
                    return {"enabled": False, "provider": "local", "reason": detail}
                res.raise_for_status()

                filename = f"{uuid.uuid4().hex}.mp4"
                video_path = self._videos_dir() / filename
                video_path.write_bytes(res.content)

                return {
                    "enabled": True,
                    "provider": "wav2lip",
                    "video_url": f"/api/avatar/video/{filename}",
                }
        except httpx.ConnectError:
            logger.warning("Wav2Lip avatar service not reachable at %s", url)
            return {"enabled": False, "provider": "local", "reason": "avatar-service is not running"}
        except Exception as e:
            logger.warning("Wav2Lip generation failed: %s", e)
            return {"enabled": False, "provider": "local", "reason": str(e)}
