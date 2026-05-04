import asyncio
import hashlib
import json
import random
import uuid
from pathlib import Path

import httpx

from app.core.config import settings
from app.core.logging import setup_logger

logger = setup_logger(__name__)

# In-memory job store: job_id -> {status, video_url?, error?}
_video_jobs: dict[str, dict] = {}
_MAX_JOBS = 200

# Pre-render progress tracking
_prerender_status: dict = {"running": False, "total": 0, "done": 0, "phase": ""}

# Generic small-talk clips pre-rendered at startup for immediate playback
SMALLTALK_CLIPS = [
    "Let me pull up your session.",
    "Just a moment while I get set up.",
    "Getting everything ready for you.",
    "One moment please.",
    "Almost ready to begin.",
]


class AvatarService:
    @staticmethod
    def _is_wav2lip_enabled() -> bool:
        return settings.avatar_provider == "wav2lip" and bool(settings.avatar_service_url)

    @staticmethod
    def _videos_dir() -> Path:
        d = Path(settings.videos_dir)
        d.mkdir(parents=True, exist_ok=True)
        return d

    @staticmethod
    def _wav2lip_url(path: str) -> str:
        return settings.avatar_service_url.rstrip("/") + path

    # ── Intro video (pre-rendered at session creation) ────────────────────────

    async def render_intro_video(
        self,
        session_id: int,
        text: str,
        voice: str = "en-US-JennyNeural",
    ) -> None:
        """Background task: render the opening message as a wav2lip video."""
        if not self._is_wav2lip_enabled():
            logger.debug("wav2lip disabled — skipping intro render for session %d", session_id)
            return

        video_path = self._videos_dir() / f"session_{session_id}_intro.mp4"
        if video_path.exists():
            logger.debug("Intro video already exists for session %d", session_id)
            return

        logger.info("Rendering intro video for session %d …", session_id)
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                res = await client.post(
                    self._wav2lip_url("/generate"),
                    json={"text": text, "voice": voice},
                )
                res.raise_for_status()
                video_path.write_bytes(res.content)
                logger.info("Intro video ready for session %d (%d bytes)", session_id, len(res.content))
        except httpx.ConnectError:
            logger.warning("wav2lip not reachable — intro render skipped for session %d", session_id)
        except Exception as exc:
            logger.warning("Intro render failed for session %d: %s", session_id, exc)

    def get_intro_status(self, session_id: int) -> dict:
        """Return whether the intro video is ready and its URL."""
        if not self._is_wav2lip_enabled():
            return {"ready": False, "reason": "wav2lip not configured"}

        video_path = self._videos_dir() / f"session_{session_id}_intro.mp4"
        if video_path.exists():
            return {
                "ready": True,
                "video_url": f"/api/avatar/video/session_{session_id}_intro.mp4",
            }
        return {"ready": False}

    async def prerender_smalltalk_clips(self) -> None:
        """
        Pre-render generic small-talk clips at startup for immediate playback.
        Skips clips that already exist on disk. Safe to call multiple times.
        """
        if not self._is_wav2lip_enabled():
            logger.debug("wav2lip disabled — skipping smalltalk pre-render")
            return

        # Check if all clips already exist — skip the wait if so
        all_exist = all(
            (self._videos_dir() / f"smalltalk_{i}.mp4").exists()
            for i in range(len(SMALLTALK_CLIPS))
        )
        if all_exist:
            logger.debug("All smalltalk clips already exist — skipping pre-render")
            return

        # Wait for avatar service before rendering
        if not await self._wait_for_avatar_service():
            logger.warning("Skipping smalltalk pre-render — avatar service unavailable")
            return

        logger.info("Pre-rendering %d smalltalk clips …", len(SMALLTALK_CLIPS))
        for i, phrase in enumerate(SMALLTALK_CLIPS):
            video_path = self._videos_dir() / f"smalltalk_{i}.mp4"
            if video_path.exists():
                logger.debug("Smalltalk clip %d already exists — skipping", i)
                continue
            try:
                async with httpx.AsyncClient(timeout=300.0) as client:
                    res = await client.post(
                        self._wav2lip_url("/generate"),
                        json={"text": phrase, "voice": "en-US-GuyNeural"},
                    )
                    res.raise_for_status()
                    video_path.write_bytes(res.content)
                    logger.info("Smalltalk clip %d ready (%d bytes)", i, len(res.content))
            except httpx.ConnectError:
                logger.warning("wav2lip not reachable — smalltalk clip %d skipped", i)
            except Exception as exc:
                logger.warning("Smalltalk clip %d render failed: %s", i, exc)

    def get_smalltalk_urls(self) -> list[str]:
        """Return URLs for all pre-rendered smalltalk clips that exist on disk."""
        urls = []
        for i in range(len(SMALLTALK_CLIPS)):
            video_path = self._videos_dir() / f"smalltalk_{i}.mp4"
            if video_path.exists():
                urls.append(f"/api/avatar/video/smalltalk_{i}.mp4")
        return urls

    # ── Scenario pre-rendering ───────────────────────────────────────────────

    async def _wait_for_avatar_service(self, timeout: int = 120) -> bool:
        """
        Poll the avatar service /health endpoint until it responds OK.
        Returns True if ready, False if timed out.
        """
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    res = await client.get(self._wav2lip_url("/health"))
                    if res.status_code == 200:
                        logger.info("Avatar service is ready")
                        return True
            except (httpx.ConnectError, httpx.TimeoutException):
                pass
            await asyncio.sleep(3)
        logger.warning("Avatar service did not become ready within %ds", timeout)
        return False

    async def prerender_scenario_clips(self) -> None:
        if not self._is_wav2lip_enabled():
            logger.debug("wav2lip disabled — skipping scenario pre-render")
            return
        from app.services.scenarios import SCENARIO_PHRASES
        scenarios_dir = self._videos_dir() / "scenarios"
        scenarios_dir.mkdir(parents=True, exist_ok=True)

        # Count how many actually need rendering
        to_render = [p for p in SCENARIO_PHRASES if not (scenarios_dir / f"{p['phase']}_{p['index']}.mp4").exists()]
        if not to_render:
            logger.info("All %d scenario clips already exist — skipping pre-render", len(SCENARIO_PHRASES))
            self._write_scenario_manifest()
            return

        # Set status atomically before waiting so frontend polls see running=True immediately
        _prerender_status["running"] = True
        _prerender_status["total"] = len(to_render)
        _prerender_status["done"] = 0

        if not await self._wait_for_avatar_service():
            logger.warning("Skipping scenario pre-render — avatar service unavailable")
            _prerender_status["running"] = False
            self._write_scenario_manifest()  # write empty manifest so frontend doesn't keep polling
            return

        logger.info("Pre-rendering %d scenario clips (%d already cached) …", len(to_render), len(SCENARIO_PHRASES) - len(to_render))
        for phrase in to_render:
            filename = f"{phrase['phase']}_{phrase['index']}.mp4"
            video_path = scenarios_dir / filename
            _prerender_status["phase"] = f"{phrase['phase']}_{phrase['index']}"
            try:
                async with httpx.AsyncClient(timeout=300.0) as client:
                    res = await client.post(self._wav2lip_url("/generate"), json={"text": phrase["text"], "voice": "en-US-GuyNeural"})
                    res.raise_for_status()
                    video_path.write_bytes(res.content)
                    logger.info("Scenario clip %s ready (%d bytes)", filename, len(res.content))
            except httpx.ConnectError:
                logger.warning("wav2lip not reachable — scenario clip %s skipped", filename)
            except Exception as exc:
                logger.warning("Scenario clip %s render failed: %s", filename, exc)
            _prerender_status["done"] += 1

        _prerender_status["running"] = False
        _prerender_status["phase"] = ""
        self._write_scenario_manifest()

    def _write_scenario_manifest(self) -> None:
        from app.services.scenarios import SCENARIO_PHRASES
        scenarios_dir = self._videos_dir() / "scenarios"
        clips = []
        for phrase in SCENARIO_PHRASES:
            filename = f"{phrase['phase']}_{phrase['index']}.mp4"
            if (scenarios_dir / filename).exists():
                clips.append({"phase": phrase["phase"], "index": phrase["index"], "text": phrase["text"], "path": f"scenarios/{filename}"})
        manifest_path = scenarios_dir / "manifest.json"
        manifest_path.write_text(json.dumps({"clips": clips}, indent=2))
        logger.info("Scenario manifest written with %d clips", len(clips))

    def get_scenario_manifest(self) -> dict:
        manifest_path = self._videos_dir() / "scenarios" / "manifest.json"
        if not manifest_path.exists():
            return {"clips": []}
        try:
            return json.loads(manifest_path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read scenario manifest: %s", exc)
            return {"clips": []}

    def get_intro_clip(self) -> dict:
        """Return a random pre-rendered intro clip URL, or None if none exist."""
        manifest = self.get_scenario_manifest()
        intro_clips = [c for c in manifest.get("clips", []) if c.get("phase") == "intro"]
        if not intro_clips:
            return {"video_url": None}
        clip = random.choice(intro_clips)
        return {"video_url": f"/api/avatar/video/{clip['path']}"}

    @staticmethod
    def get_prerender_status() -> dict:
        """Return current pre-render progress for the frontend banner."""
        return dict(_prerender_status)

    # ── Response videos (one per AI turn, rendered in background) ────────────

    def start_response_job(self, text: str, voice: str, persona: str | None = None) -> str | None:
        """
        Register a new wav2lip render job. Returns job_id, or None if
        wav2lip is disabled (caller should skip polling).
        """
        if not self._is_wav2lip_enabled():
            return None

        # FIFO eviction — keep memory bounded to _MAX_JOBS entries
        if len(_video_jobs) >= _MAX_JOBS:
            oldest_key = next(iter(_video_jobs))
            del _video_jobs[oldest_key]

        job_id = uuid.uuid4().hex
        _video_jobs[job_id] = {"status": "pending"}
        asyncio.create_task(self._render_response(job_id, text, voice, persona))
        return job_id

    async def _render_response(self, job_id: str, text: str, voice: str, persona: str | None = None) -> None:
        """Async task: render a response video and update job store."""
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                body: dict = {"text": text, "voice": voice}
                if persona is not None:
                    body["persona"] = persona
                res = await client.post(
                    self._wav2lip_url("/generate"),
                    json=body,
                )
                res.raise_for_status()

                filename = f"response_{job_id}.mp4"
                video_path = self._videos_dir() / filename
                video_path.write_bytes(res.content)

                _video_jobs[job_id] = {
                    "status": "done",
                    "video_url": f"/api/avatar/video/{filename}",
                }
                logger.info("Response video ready job=%s (%d bytes)", job_id, len(res.content))
        except httpx.ConnectError:
            _video_jobs[job_id] = {"status": "error", "error": "wav2lip service not reachable"}
            logger.warning("wav2lip not reachable for job %s", job_id)
        except Exception as exc:
            _video_jobs[job_id] = {"status": "error", "error": str(exc)}
            logger.warning("Response render failed job=%s: %s", job_id, exc)

    @staticmethod
    def get_job_status(job_id: str) -> dict:
        job = _video_jobs.get(job_id)
        if not job:
            return {"status": "not_found"}
        return job

    # ── Legacy (kept for existing speak-video route) ──────────────────────────

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

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                res = await client.post(
                    self._wav2lip_url("/generate"),
                    json={"text": text, "voice": voice},
                )
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
            logger.warning("Wav2Lip avatar service not reachable at %s", settings.avatar_service_url)
            return {"enabled": False, "provider": "local", "reason": "avatar-service is not running"}
        except Exception as exc:
            logger.warning("Wav2Lip generation failed: %s", exc)
            return {"enabled": False, "provider": "local", "reason": str(exc)}


# Shared singleton — import this everywhere instead of constructing AvatarService()
avatar_service = AvatarService()
