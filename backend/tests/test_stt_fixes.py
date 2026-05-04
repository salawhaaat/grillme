"""Tests for STT fixes — minimum duration check, fallback logging, vad_filter."""
import io
import struct
import wave
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.routes.stt import _transcribe_wav


def _make_wav(duration_s: float, sample_rate: int = 16000) -> bytes:
    """Generate a silent WAV file of the given duration."""
    n_frames = int(duration_s * sample_rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * n_frames)
    return buf.getvalue()


class TestMinDurationCheck:
    def test_short_audio_returns_empty(self):
        """Audio < 0.3s should return empty without running Whisper."""
        wav = _make_wav(0.1)
        with patch("app.routes.stt._get_model") as mock_model:
            result = _transcribe_wav(wav)
        assert result == ""
        mock_model.return_value.transcribe.assert_not_called()

    def test_normal_audio_runs_whisper(self):
        """Audio >= 0.3s should run Whisper inference."""
        wav = _make_wav(1.0)
        mock_seg = MagicMock()
        mock_seg.text = "hello world"
        mock_model = MagicMock()
        mock_model.transcribe.return_value = ([mock_seg], None)
        with patch("app.routes.stt._get_model", return_value=mock_model):
            result = _transcribe_wav(wav)
        assert result == "hello world"
        mock_model.transcribe.assert_called_once()


class TestVadFilterDisabled:
    def test_transcribe_raw_uses_vad_filter_false(self):
        """transcribe_raw should call model.transcribe with vad_filter=False."""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([]), None)
        with patch("app.services.stt._get_model", return_value=mock_model):
            from app.services.stt import transcribe_raw
            transcribe_raw(b"fake audio", "audio/wav")
        call_kwargs = mock_model.transcribe.call_args
        assert call_kwargs[1].get("vad_filter") is False or call_kwargs.kwargs.get("vad_filter") is False


# ── Bug Condition Exploration Tests (Task 1) ─────────────────────────────────
# These tests MUST FAIL on unfixed code — failure confirms the bug exists.
# DO NOT fix the code when these tests fail.
# Validates: Requirements 1.1, 1.2, 1.3


class TestBugMode1ImportError:
    """
    Mode 1: _get_model raises ImportError → route should return HTTP 503.
    On unfixed code this FAILS: gets 200 with {"text": ""}.

    Validates: Requirements 1.1
    """

    def test_import_error_returns_503(self, client: TestClient):
        """
        When _get_model raises ImportError (faster-whisper not installed),
        POST /api/stt should return HTTP 503, not 200 with empty text.

        Expected counterexample on unfixed code:
          assert response.status_code == 503
          AssertionError: actual status_code=200, body={"text": ""}
        """
        wav_bytes = _make_wav(1.0)

        with patch("app.routes.stt._get_model", side_effect=ImportError("No module named 'faster_whisper'")):
            response = client.post(
                "/api/stt",
                content=wav_bytes,
                headers={"Content-Type": "audio/wav"},
            )

        assert response.status_code == 503, (
            f"Expected 503 (model unavailable) but got {response.status_code}; "
            f"body={response.text!r}"
        )


class TestBugMode2WavParseFailure:
    """
    Mode 2: _wav_bytes_to_float32 raises ValueError + transcribe_raw returns "" →
    route should return HTTP 4xx/5xx or a non-empty error field.
    On unfixed code this FAILS: gets {"text": ""} with HTTP 200.

    Validates: Requirements 1.2
    """

    def test_wav_parse_failure_with_broken_fallback_returns_error(self, client: TestClient):
        """
        When WAV parsing fails AND the fallback transcribe_raw also returns "",
        the route should NOT silently return {"text": ""}.
        It should return HTTP 4xx/5xx OR a body with a non-empty error field.

        Expected counterexample on unfixed code:
          assert response.status_code >= 400 or response.json().get("error") or response.json().get("detail")
          AssertionError: actual status_code=200, body={"text": ""}
        """
        wav_bytes = _make_wav(1.0)

        with patch("app.routes.stt._wav_bytes_to_float32", side_effect=ValueError("Expected 16-bit WAV, got 24-bit")):
            with patch("app.routes.stt.transcribe_raw", return_value=""):
                response = client.post(
                    "/api/stt",
                    content=wav_bytes,
                    headers={"Content-Type": "audio/wav"},
                )

        body = response.json()
        is_error_response = (
            response.status_code >= 400
            or body.get("error")
            or body.get("detail")
        )
        assert is_error_response, (
            f"Expected HTTP 4xx/5xx or non-empty error field, but got "
            f"status_code={response.status_code}, body={body!r}"
        )


class TestBugMode3ZeroSegmentParameters:
    """
    Mode 3: model.transcribe returns empty iterator → should be called with
    beam_size=5 and temperature=[0.0, 0.2, 0.4] (tuned params).
    On unfixed code this FAILS: called with beam_size=1, temperature=0.0.

    Validates: Requirements 1.3
    """

    def test_transcribe_called_with_tuned_parameters(self):
        """
        For a valid 1 s WAV, model.transcribe should be called with
        beam_size=5 and temperature=[0.0, 0.2, 0.4] to reduce false-empty results.

        Expected counterexample on unfixed code:
          assert call_kwargs["beam_size"] == 5
          AssertionError: actual beam_size=1
          assert call_kwargs["temperature"] == [0.0, 0.2, 0.4]
          AssertionError: actual temperature=0.0
        """
        wav_bytes = _make_wav(1.0)

        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([]), None)  # zero segments

        with patch("app.routes.stt._get_model", return_value=mock_model):
            _transcribe_wav(wav_bytes)

        assert mock_model.transcribe.called, "model.transcribe was never called for a 1 s WAV"

        call_kwargs = mock_model.transcribe.call_args.kwargs

        assert call_kwargs.get("beam_size") == 5, (
            f"Expected beam_size=5 but got beam_size={call_kwargs.get('beam_size')!r}. "
            "Unfixed code uses beam_size=1."
        )
        assert call_kwargs.get("temperature") == [0.0, 0.2, 0.4], (
            f"Expected temperature=[0.0, 0.2, 0.4] but got temperature={call_kwargs.get('temperature')!r}. "
            "Unfixed code uses temperature=0.0 (greedy only, no fallback)."
        )


# ── Preservation Property Tests (Task 2) ─────────────────────────────────────
# These tests MUST PASS on unfixed code — passing confirms the baseline behavior
# to preserve after the fix is applied.
# Validates: Requirements 3.1, 3.2, 3.3

from hypothesis import given, settings as h_settings, HealthCheck
import hypothesis.strategies as st


class TestPreservationShortClip:
    """
    Property: Short-clip guard is preserved for all durations in [0.01, 0.29] s.

    For any WAV shorter than 0.3 s, _transcribe_wav MUST return "" immediately
    without running model.transcribe (no Whisper inference).

    Note: On unfixed code, _get_model() IS called at the top of _transcribe_wav
    before the duration check, but model.transcribe is never called — the guard
    returns early. The property asserts transcribe is not called, not _get_model.

    Should PASS on unfixed code — the short-clip guard already works correctly.

    Validates: Requirements 3.1
    """

    @given(duration=st.floats(min_value=0.01, max_value=0.29))
    @h_settings(max_examples=30)
    def test_short_clip_returns_empty_without_transcribe(self, duration: float):
        """
        **Validates: Requirements 3.1**

        For any duration in [0.01, 0.29] s, _transcribe_wav must return ""
        and model.transcribe must never be called (no Whisper inference).
        """
        wav = _make_wav(duration)
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([]), None)
        with patch("app.routes.stt._get_model", return_value=mock_model):
            result = _transcribe_wav(wav)
        assert result == "", (
            f"Expected '' for {duration:.4f}s WAV but got {result!r}"
        )
        mock_model.transcribe.assert_not_called()


class TestPreservationSilence:
    """
    Property: Silent WAVs with duration >= 0.3 s always return {"text": ""} HTTP 200.

    When model.transcribe returns an empty iterator (genuine silence), the route
    must return {"text": ""} with HTTP 200 — not an error.

    Should PASS on unfixed code — the silence path already works correctly.

    Validates: Requirements 3.2
    """

    @given(duration=st.floats(min_value=0.3, max_value=5.0))
    @h_settings(
        max_examples=20,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_silence_returns_empty_200(self, duration: float, client: TestClient):
        """
        **Validates: Requirements 3.2**

        For any silent WAV with duration >= 0.3 s, POST /api/stt must return
        HTTP 200 with {"text": ""} when model.transcribe yields no segments.
        """
        wav = _make_wav(duration)
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([]), None)

        with patch("app.routes.stt._get_model", return_value=mock_model):
            response = client.post(
                "/api/stt",
                content=wav,
                headers={"Content-Type": "audio/wav"},
            )

        assert response.status_code == 200, (
            f"Expected HTTP 200 for silent {duration:.2f}s WAV but got {response.status_code}"
        )
        assert response.json() == {"text": ""}, (
            f"Expected {{\"text\": \"\"}} for silent WAV but got {response.json()!r}"
        )


class TestPreservationValidSpeech:
    """
    Property: Valid speech with a working model always returns the correct transcript.

    When model.transcribe returns a segment with text "hello", the route must
    return {"text": "hello"} — the happy path must be preserved.

    Should PASS on unfixed code — the valid-speech path already works correctly.

    Validates: Requirements 3.3
    """

    def test_valid_speech_returns_transcript(self, client: TestClient):
        """
        **Validates: Requirements 3.3**

        For a 1 s WAV with model.transcribe returning a single segment "hello",
        POST /api/stt must return {"text": "hello"} with HTTP 200.
        """
        wav = _make_wav(1.0)
        mock_seg = MagicMock()
        mock_seg.text = "hello"
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([mock_seg]), None)

        with patch("app.routes.stt._get_model", return_value=mock_model):
            response = client.post(
                "/api/stt",
                content=wav,
                headers={"Content-Type": "audio/wav"},
            )

        assert response.status_code == 200, (
            f"Expected HTTP 200 but got {response.status_code}"
        )
        assert response.json() == {"text": "hello"}, (
            f"Expected {{\"text\": \"hello\"}} but got {response.json()!r}"
        )
