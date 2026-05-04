"""
Speech-to-text endpoints.

Provides two modes:

1. **One-shot POST** ``/api/stt`` (new, preferred)
   Browser VAD detects end-of-speech and sends a complete WAV blob.
   Server runs a single faster-whisper inference and returns JSON.
   Typical latency: ~150–400 ms for a 2–5 s utterance (base.en int8).

2. **WebSocket** ``/api/stt/ws/{session_id}`` (legacy, kept for compatibility)
   MediaRecorder streams 500 ms webm/opus chunks; server transcribes on a
   3 s timer.  Higher latency (~3 s) but works without browser-side VAD.
"""

import asyncio
import io
import json
import wave

import numpy as np
from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect

from app.core.logging import setup_logger
from app.services.stt import _get_model, transcribe_raw

router = APIRouter(prefix="/api/stt", tags=["stt"])
logger = setup_logger(__name__)

# Serialize STT inference — CTranslate2 parallelizes internally.
_stt_semaphore = asyncio.Semaphore(1)


def _check_model_available() -> None:
    """
    Verify the STT model can be loaded.

    Raises ``HTTPException(503)`` if ``faster-whisper`` is not installed or
    the model cannot be initialised, so callers get a clear error instead of
    a silent empty transcript.
    """
    try:
        _get_model()
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="STT model unavailable") from exc


# ── One-shot STT (browser VAD → complete utterance → single inference) ────────


@router.post("")
async def stt_oneshot(request: Request) -> dict:
    """
    Transcribe a complete utterance in one shot.

    Accepts raw WAV audio (16-bit PCM, 16kHz, mono) as the request body.
    Returns ``{"text": "..."}``.

    The browser detects end-of-speech with Silero VAD, encodes a WAV blob,
    and POSTs it here.  No sliding window, no re-transcription.
    """
    body = await request.body()
    if not body:
        return {"text": ""}

    # Fail fast with 503 if the STT model is unavailable (mode 1 fix).
    _check_model_available()

    async with _stt_semaphore:
        text = await asyncio.to_thread(_transcribe_wav, body)

    return {"text": text}


def _transcribe_wav(wav_bytes: bytes) -> str:
    """
    Parse WAV bytes → float32 numpy array → faster-whisper transcription.

    Expects 16-bit PCM, 16kHz, mono WAV.  Falls back to the file-based
    ``transcribe_raw`` for non-standard formats.

    Raises ``ImportError`` if ``faster-whisper`` is not installed (caller
    converts this to HTTP 503 via ``_check_model_available``).
    Raises ``HTTPException(500)`` if both the direct path and fallback fail.
    """
    # Let ImportError propagate — the route handler converts it to 503.
    model = _get_model()

    # Extract WAV header info for duration check and logging
    duration: float = 0.0
    framerate: int = 16000
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            nframes = wf.getnframes()
            framerate = wf.getframerate()
            duration = nframes / framerate if framerate > 0 else 0.0
    except Exception:
        pass  # will be caught again below

    # Skip inference for very short clips (VAD fired too early)
    if duration > 0 and duration < 0.3:
        logger.debug("STT skipped — audio too short (%.3fs)", duration)
        return ""

    try:
        audio = _wav_bytes_to_float32(wav_bytes)
    except (ValueError, wave.Error) as exc:
        # Non-WAV format (e.g. WebM/Opus from MediaRecorder) or non-16-bit WAV.
        logger.debug("WAV parse failed (%s), falling back to transcribe_raw", exc)
        result = transcribe_raw(wav_bytes, "audio/webm")
        if not result:
            # Both direct path and fallback failed — surface as a real error.
            raise HTTPException(
                status_code=500, detail="STT transcription failed"
            ) from exc
        return result

    segments, _ = model.transcribe(
        audio,
        beam_size=5,
        language="en",
        condition_on_previous_text=False,
        vad_filter=False,
        without_timestamps=True,
        temperature=[0.0, 0.2, 0.4],
    )
    result = " ".join(seg.text.strip() for seg in segments).strip()
    if not result:
        logger.debug("STT returned empty — duration=%.2fs sr=%d", duration, framerate)
    return result


def _wav_bytes_to_float32(wav_bytes: bytes) -> np.ndarray:
    """Convert raw WAV bytes (16-bit PCM) to float32 numpy array in [-1, 1]."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        if wf.getsampwidth() != 2:
            raise ValueError(
                f"Expected 16-bit WAV, got {wf.getsampwidth() * 8}-bit"
            )
        frames = wf.readframes(wf.getnframes())

    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


# ── Legacy WebSocket STT ─────────────────────────────────────────────────────

# Transcribe whatever is in the buffer every N seconds
WINDOW_SEC = 3.0


@router.websocket("/ws/{session_id}")
async def stt_websocket(websocket: WebSocket, session_id: int):
    await websocket.accept()
    logger.info("STT WebSocket opened session=%d", session_id)

    buffer = bytearray()
    mime = "audio/webm"
    running = True

    async def flush_and_send(final: bool) -> str:
        """Transcribe current buffer, clear it, send result to client."""
        nonlocal buffer
        if not buffer:
            if final:
                await websocket.send_text(json.dumps({"transcript": "", "final": True}))
            return ""
        data = bytes(buffer)
        buffer = bytearray()
        try:
            text = await _transcribe(data, mime)
        except Exception as exc:
            logger.error("STT transcription error: %s", exc)
            text = ""
        if text:
            await websocket.send_text(
                json.dumps({"transcript": text, "final": final})
            )
        elif final:
            await websocket.send_text(json.dumps({"transcript": "", "final": True}))
        return text

    async def periodic_flush():
        """Fire every WINDOW_SEC while session is open."""
        while running:
            await asyncio.sleep(WINDOW_SEC)
            if buffer:
                await flush_and_send(final=False)

    flush_task = asyncio.create_task(periodic_flush())

    try:
        while True:
            message = await websocket.receive()

            if message.get("bytes"):
                buffer.extend(message["bytes"])

            elif message.get("text"):
                try:
                    ctrl = json.loads(message["text"])
                except json.JSONDecodeError:
                    continue

                if ctrl.get("mime"):
                    mime = ctrl["mime"]
                    logger.debug("STT mime=%s session=%d", mime, session_id)

                action = ctrl.get("action", "")

                if action == "stop":
                    flush_task.cancel()
                    await flush_and_send(final=True)
                    break

    except WebSocketDisconnect:
        logger.info("STT WebSocket disconnected session=%d", session_id)
    except Exception as exc:
        logger.error("STT WebSocket error session=%d: %s", session_id, exc)
        try:
            await websocket.send_text(json.dumps({"error": str(exc)}))
        except Exception:
            pass
    finally:
        running = False
        flush_task.cancel()


async def _transcribe(audio: bytes, mime: str) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, transcribe_raw, audio, mime)
