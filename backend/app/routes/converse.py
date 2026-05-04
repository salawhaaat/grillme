"""
Streaming voice-converse endpoint.

POST /api/converse/stream
  Body: {"session_id": int, "text": str, "voice": str?}
  Response: StreamingResponse of MP3 audio bytes (chunked transfer).

The pipeline chains three async generators:
  LLM tokens → sentence splitter → per-sentence edge-tts → MP3 bytes

Supports clean cancellation via AbortController on the client side:
  - Browser abort() → Starlette http.disconnect → CancelledError in generator
  - Shared asyncio.Event propagates cancel across all generators
  - LLM stream is closed to halt upstream billing

Also exposes a text-only variant for transcript display:
POST /api/converse/stream-text
  Same body, but yields "data: <json>\n\n" SSE events with sentence text.

POST /api/stt
  Body: raw WAV audio (16-bit PCM, 16kHz, mono)
  Response: {"text": "transcribed text"}
  One-shot transcription via faster-whisper (no WebSocket, no sliding window).
"""

import asyncio
import contextlib
import json
import struct
from typing import AsyncIterator

import edge_tts
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import setup_logger
from app.models.session import InterviewSession
from app.services.avatar import avatar_service
from app.services.llm import LLMService, ProviderError, RateLimitError
from app.services.sentence_splitter import split_sentences

logger = setup_logger(__name__)
router = APIRouter(prefix="/api/converse", tags=["converse"])

llm = LLMService()

# Serialize STT inference — CTranslate2 parallelizes internally.
_stt_semaphore = asyncio.Semaphore(1)


# ── Request schemas ──────────────────────────────────────────────────────────

class ConverseRequest(BaseModel):
    session_id: int
    text: str
    voice: str = "en-US-GuyNeural"


# ── Helpers imported from sessions.py (kept DRY via local re-implementation) ─

def _estimate_text_tokens(text: str | None) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


def _estimate_messages_tokens(messages: list[dict]) -> int:
    return sum(_estimate_text_tokens(str(m.get("content", ""))) for m in messages)


def _apply_usage(
    session: InterviewSession, prompt_tokens: int, completion_tokens: int
) -> None:
    session.prompt_tokens = (session.prompt_tokens or 0) + max(0, prompt_tokens)
    session.completion_tokens = (session.completion_tokens or 0) + max(
        0, completion_tokens
    )
    session.total_tokens = (session.total_tokens or 0) + max(
        0, prompt_tokens + completion_tokens
    )


# ── Generator chain ─────────────────────────────────────────────────────────


async def _stream_llm_tokens(
    messages: list[dict],
    cancel: asyncio.Event,
) -> AsyncIterator[str]:
    """Yield LLM text tokens, checking cancel between each."""
    try:
        async for token in llm.stream_chat(messages):
            if cancel.is_set():
                break
            yield token
    except asyncio.CancelledError:
        cancel.set()
        raise


async def _tts_sentence_bytes(
    sentence: str,
    voice: str,
    cancel: asyncio.Event,
) -> AsyncIterator[bytes]:
    """Stream MP3 bytes for a single sentence via edge-tts."""
    communicate = edge_tts.Communicate(sentence, voice)
    try:
        async for chunk in communicate.stream():
            if cancel.is_set():
                return
            if chunk["type"] == "audio":
                data = chunk["data"]
                if isinstance(data, bytearray):
                    data = bytes(data)
                if data:
                    yield data
    except asyncio.CancelledError:
        cancel.set()
        raise


async def _voice_pipeline(
    messages: list[dict],
    voice: str,
    cancel: asyncio.Event,
    collected_text: list[str],
) -> AsyncIterator[bytes]:
    """
    Full LLM → sentence-split → TTS chain.
    Collects full assistant text in *collected_text* (mutated in place).

    Yields length-prefixed sentence blobs:
      [4-byte big-endian length] [MP3 bytes for one sentence]

    This allows the browser to accumulate bytes per-sentence and decode
    each complete MP3 blob via decodeAudioData() — partial MP3 fragments
    cannot be decoded.
    """
    token_stream = _stream_llm_tokens(messages, cancel)
    sentence_stream = split_sentences(token_stream, min_length=15)

    async for sentence in sentence_stream:
        if cancel.is_set():
            return
        collected_text.append(sentence)

        # Collect all MP3 bytes for this sentence
        sentence_bytes = bytearray()
        async for mp3_chunk in _tts_sentence_bytes(sentence, voice, cancel):
            if cancel.is_set():
                return
            sentence_bytes.extend(mp3_chunk)

        if sentence_bytes:
            # Send length header + complete MP3 blob
            yield struct.pack(">I", len(sentence_bytes))
            yield bytes(sentence_bytes)


# ── Import session system prompt builder from sessions module ────────────────

def _import_build_system_prompt():
    """Lazy import to avoid circular dependency."""
    from app.routes.sessions import _build_system_prompt
    return _build_system_prompt


def _trim_messages(messages: list[dict], max_turns: int = 12) -> list[dict]:
    """
    Keep only the most recent `max_turns` messages to prevent context bloat
    on long sessions. Always preserves the first assistant message (opening).
    Reduced to 12 for local Ollama (4096 token context limit).
    """
    if len(messages) <= max_turns:
        return messages
    # Always keep the first message (opening), then the most recent (max_turns - 1)
    return [messages[0]] + messages[-(max_turns - 1):]


# ── Streaming voice endpoint ────────────────────────────────────────────────


@router.post("/stream")
async def converse_stream(
    body: ConverseRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    Stream MP3 audio of the AI interviewer's response.

    The browser should fetch this with an AbortController signal.
    Aborting the fetch cancels the LLM + TTS pipeline immediately.
    """
    session = await db.get(InterviewSession, body.session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    # Build LLM message list
    messages = json.loads(session.messages)
    messages.append({"role": "user", "content": body.text})

    build_system_prompt = _import_build_system_prompt()
    system_prompt = build_system_prompt(session, messages=messages)
    llm_messages = [{"role": "system", "content": system_prompt}] + messages

    cancel = asyncio.Event()
    collected_text: list[str] = []

    async def watchdog() -> None:
        """Poll for client disconnect every 50ms."""
        while not cancel.is_set():
            if await request.is_disconnected():
                cancel.set()
                return
            await asyncio.sleep(0.05)

    async def generate() -> AsyncIterator[bytes]:
        watchdog_task = asyncio.create_task(watchdog())
        try:
            async for chunk in _voice_pipeline(
                llm_messages, body.voice, cancel, collected_text
            ):
                if cancel.is_set():
                    break
                yield chunk
        except asyncio.CancelledError:
            cancel.set()
        except (RateLimitError, ProviderError, ValueError) as exc:
            logger.error("Converse stream error: %s", exc)
        finally:
            cancel.set()
            watchdog_task.cancel()
            with contextlib.suppress(BaseException):
                await watchdog_task

            # Persist the conversation even if cancelled partway through.
            assistant_text = " ".join(collected_text).strip()
            if assistant_text:
                messages.append(
                    {"role": "assistant", "content": assistant_text}
                )
                session.messages = json.dumps(messages)
                _apply_usage(
                    session,
                    prompt_tokens=_estimate_messages_tokens(llm_messages),
                    completion_tokens=_estimate_text_tokens(assistant_text),
                )
                try:
                    await db.commit()
                except Exception:
                    logger.exception("Failed to persist converse messages")

    return StreamingResponse(
        generate(),
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
        },
    )


# ── Streaming text endpoint (SSE, for transcript display) ───────────────────


@router.post("/stream-text")
async def converse_stream_text(
    body: ConverseRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """
    Stream the AI response as SSE text events (no audio).
    Each event: data: {"sentence": "...", "done": false}\n\n

    Useful for displaying the transcript while audio plays.
    """
    session = await db.get(InterviewSession, body.session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    messages = json.loads(session.messages)
    messages.append({"role": "user", "content": body.text})

    build_system_prompt = _import_build_system_prompt()
    system_prompt = build_system_prompt(session, messages=messages)
    llm_messages = [{"role": "system", "content": system_prompt}] + messages

    cancel = asyncio.Event()
    collected_text: list[str] = []

    async def generate() -> AsyncIterator[str]:
        try:
            token_stream = _stream_llm_tokens(llm_messages, cancel)
            sentence_stream = split_sentences(token_stream, min_length=15)
            async for sentence in sentence_stream:
                if cancel.is_set():
                    break
                collected_text.append(sentence)
                yield f"data: {json.dumps({'sentence': sentence, 'done': False})}\n\n"
            yield f"data: {json.dumps({'sentence': '', 'done': True})}\n\n"
        except asyncio.CancelledError:
            cancel.set()
        except (RateLimitError, ProviderError, ValueError) as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
        finally:
            cancel.set()
            assistant_text = " ".join(collected_text).strip()
            if assistant_text:
                messages.append(
                    {"role": "assistant", "content": assistant_text}
                )
                session.messages = json.dumps(messages)
                _apply_usage(
                    session,
                    prompt_tokens=_estimate_messages_tokens(llm_messages),
                    completion_tokens=_estimate_text_tokens(assistant_text),
                )
                try:
                    await db.commit()
                except Exception:
                    logger.exception("Failed to persist stream-text messages")

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
        },
    )


# ── Respond endpoint: LLM → save → start wav2lip job ─────────────────────────


class RespondRequest(BaseModel):
    session_id: int
    text: str
    voice: str = "en-US-GuyNeural"


@router.post("/respond")
async def converse_respond(
    body: RespondRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Full non-streaming turn:
      1. Fetch session + build system prompt
      2. Call LLM synchronously → response_text
      3. Persist user + assistant messages to DB
      4. Kick off wav2lip background job (no-op if wav2lip disabled)
      5. Return {job_id, text} immediately

    Frontend shows response_text in dialogue right away, then polls
    GET /api/avatar/job/{job_id} until status=done before playing the video.
    """
    session = await db.get(InterviewSession, body.session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    messages = json.loads(session.messages)
    messages.append({"role": "user", "content": body.text})

    build_system_prompt = _import_build_system_prompt()
    system_prompt = build_system_prompt(session, messages=messages)
    llm_messages = [{"role": "system", "content": system_prompt}] + _trim_messages(messages)

    try:
        response_text = await llm.complete(llm_messages)
    except (RateLimitError, ProviderError, ValueError) as exc:
        raise HTTPException(503, str(exc)) from exc

    # Persist both turns
    messages.append({"role": "assistant", "content": response_text})
    session.messages = json.dumps(messages)
    _apply_usage(
        session,
        prompt_tokens=_estimate_messages_tokens(llm_messages),
        completion_tokens=_estimate_text_tokens(response_text),
    )
    try:
        await db.commit()
    except Exception:
        logger.exception("Failed to persist respond messages")

    # Always render the actual LLM response via wav2lip so video matches chat text.
    # Pre-rendered scenario clips are intentionally NOT used here — they play scripted
    # audio that doesn't match response_text, making chat and video show different things.
    job_id = avatar_service.start_response_job(response_text, body.voice, persona=session.persona)
    return {"job_id": job_id, "text": response_text, "prerendered": False}
