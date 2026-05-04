"""
Speech-to-text via faster-whisper (local, no API key needed).

The model is lazy-loaded on first use and kept in memory for the process lifetime.
Uses the 'tiny' model by default (~75 MB) — fast enough for real-time on CPU.
Override with STT_MODEL env var (e.g. 'base', 'small').
"""

import io
import os
import tempfile
import wave
from pathlib import Path
from typing import Generator

from app.core.logging import setup_logger

logger = setup_logger(__name__)

_MODEL_SIZE = os.getenv("STT_MODEL", "base.en")
_model = None  # lazy


def _get_model():
    global _model  # noqa: PLW0603
    if _model is None:
        from faster_whisper import WhisperModel  # import deferred so startup is fast

        logger.info("Loading faster-whisper model '%s' …", _MODEL_SIZE)
        _model = WhisperModel(_MODEL_SIZE, device="cpu", compute_type="int8")
        logger.info("faster-whisper model loaded.")
    return _model


def transcribe_raw(audio_bytes: bytes, mime: str = "audio/webm") -> str:
    """
    Transcribe raw audio bytes (webm/ogg/wav/mp4 — anything ffmpeg understands).
    Returns the transcript string (may be empty if silence).
    """
    model = _get_model()

    # Write to a temp file so faster-whisper / ffmpeg can read it
    suffix = _mime_to_suffix(mime)
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(audio_bytes)
        tmp_path = f.name

    try:
        segments: Generator = model.transcribe(
            tmp_path,
            language="en",
            beam_size=1,
            vad_filter=False,   # changed from True — browser VAD already confirmed speech
            vad_parameters={"min_silence_duration_ms": 300},
        )[0]
        text = " ".join(seg.text.strip() for seg in segments).strip()
        return text
    except Exception as exc:
        logger.exception("transcribe_raw failed: %s", exc)
        return ""
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def _mime_to_suffix(mime: str) -> str:
    mapping = {
        "audio/webm": ".webm",
        "audio/ogg": ".ogg",
        "audio/wav": ".wav",
        "audio/mp4": ".mp4",
        "audio/mpeg": ".mp3",
    }
    for key, suffix in mapping.items():
        if mime.startswith(key):
            return suffix
    return ".webm"
