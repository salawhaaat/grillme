"""
Wav2Lip ONNX inference service.

Generates lip-synced video frames from a static avatar image and audio.
Runs entirely on CPU via onnxruntime — no PyTorch required.

Pipeline:
  1. Face detection (SCRFD ONNX, run once per avatar, cached)
  2. Audio → mel spectrogram (librosa)
  3. Wav2Lip ONNX inference (96x96 face crop, ~35ms/frame on Apple Silicon)
  4. Composite lip-synced face back onto original image
  5. Encode frames as MP4 video

Usage:
  service = Wav2LipService("models/wav2lip")
  service.set_avatar("path/to/photo.jpg")   # detect face once
  video_bytes = service.generate(audio_pcm_16k, fps=25)
"""

import io
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import cv2
import librosa
import numpy as np
import onnxruntime as ort

from app.core.logging import setup_logger

logger = setup_logger(__name__)

# ── Mel spectrogram parameters (Wav2Lip hparams) ────────────────────────────
_SAMPLE_RATE = 16000
_N_FFT = 800
_HOP_SIZE = 200
_WIN_SIZE = 800
_NUM_MELS = 80
_FMIN = 55
_FMAX = 7600
_PREEMPHASIS = 0.97
_MIN_LEVEL_DB = -100
_REF_LEVEL_DB = 20
_MAX_ABS_VALUE = 4.0
_MEL_STEP_SIZE = 16


def _preemphasis(wav: np.ndarray, coef: float = _PREEMPHASIS) -> np.ndarray:
    return np.append(wav[0], wav[1:] - coef * wav[:-1])


def _amp_to_db(x: np.ndarray) -> np.ndarray:
    min_level = np.exp(_MIN_LEVEL_DB / 20 * np.log(10))
    return 20 * np.log10(np.maximum(min_level, x))


def _normalize(S: np.ndarray) -> np.ndarray:
    return np.clip(
        (2 * _MAX_ABS_VALUE) * ((S - _MIN_LEVEL_DB) / (-_MIN_LEVEL_DB)) - _MAX_ABS_VALUE,
        -_MAX_ABS_VALUE,
        _MAX_ABS_VALUE,
    )


def _melspectrogram(wav: np.ndarray) -> np.ndarray:
    """Compute Wav2Lip-format mel spectrogram from 16kHz audio."""
    D = librosa.stft(
        y=_preemphasis(wav),
        n_fft=_N_FFT,
        hop_length=_HOP_SIZE,
        win_length=_WIN_SIZE,
    )
    S = _amp_to_db(
        np.dot(
            librosa.filters.mel(
                sr=_SAMPLE_RATE, n_fft=_N_FFT, n_mels=_NUM_MELS, fmin=_FMIN, fmax=_FMAX,
            ),
            np.abs(D),
        )
    ) - _REF_LEVEL_DB
    return _normalize(S)


def _get_mel_chunks(mel: np.ndarray, fps: int = 25) -> list[np.ndarray]:
    """Split mel spectrogram into chunks of MEL_STEP_SIZE for each video frame."""
    mel_idx_multiplier = 80.0 / fps
    chunks = []
    i = 0
    while True:
        start = int(i * mel_idx_multiplier)
        if start + _MEL_STEP_SIZE > mel.shape[1]:
            # Pad last chunk if needed
            chunk = np.zeros((_NUM_MELS, _MEL_STEP_SIZE), dtype=np.float32)
            remaining = mel[:, start:]
            chunk[:, : remaining.shape[1]] = remaining
            chunks.append(chunk)
            break
        chunks.append(mel[:, start : start + _MEL_STEP_SIZE])
        i += 1
    return chunks


def _detect_face_haar(img: np.ndarray) -> Optional[tuple[int, int, int, int]]:
    """Detect the largest face using OpenCV's Haar cascade. Returns (x1,y1,x2,y2)."""
    cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    faces = cascade.detectMultiScale(gray, 1.1, 5, minSize=(20, 20))
    if len(faces) == 0:
        return None
    # Pick largest face
    areas = [w * h for (_, _, w, h) in faces]
    idx = int(np.argmax(areas))
    x, y, w, h = faces[idx]
    return (int(x), int(y), int(x + w), int(y + h))


# ── Wav2Lip Service ──────────────────────────────────────────────────────────


class Wav2LipService:
    """Wav2Lip ONNX inference for lip-synced avatar video generation."""

    def __init__(self, models_dir: str = "models/wav2lip") -> None:
        models_path = Path(models_dir)

        # Load Wav2Lip model
        wav2lip_path = models_path / "wav2lip.onnx"
        if not wav2lip_path.exists():
            raise FileNotFoundError(f"Wav2Lip model not found: {wav2lip_path}")
        self._wav2lip = ort.InferenceSession(
            str(wav2lip_path), providers=["CPUExecutionProvider"]
        )

        # Cached avatar data
        self._avatar_img: Optional[np.ndarray] = None
        self._face_box: Optional[tuple[int, int, int, int]] = None
        self._face_crop: Optional[np.ndarray] = None  # 96x96 BGR

        logger.info("Wav2LipService initialized (models_dir=%s)", models_dir)

    def set_avatar(self, image_path: str) -> bool:
        """
        Load avatar image and detect/cache the face region.
        Call once per avatar. Returns True if face was detected.
        """
        img = cv2.imread(image_path)
        if img is None:
            logger.error("Failed to load avatar image: %s", image_path)
            return False

        self._avatar_img = img

        box = _detect_face_haar(img)
        if box is not None:
            x1, y1, x2, y2 = box
            # Add padding for better compositing
            pad = int((x2 - x1) * 0.1)
            h, w = img.shape[:2]
            y1 = max(0, y1 - pad)
            x1 = max(0, x1 - pad)
            x2 = min(w, x2 + pad)
            y2 = min(h, y2 + pad)
            self._face_box = (x1, y1, x2, y2)
            face = img[y1:y2, x1:x2]
            self._face_crop = cv2.resize(face, (96, 96))
            logger.info("Face detected at (%d,%d,%d,%d)", x1, y1, x2, y2)
            return True

        # Fallback: use center crop
        h, w = img.shape[:2]
        size = min(h, w) // 2
        cx, cy = w // 2, h // 3
        x1 = max(0, cx - size // 2)
        y1 = max(0, cy - size // 2)
        x2 = min(w, cx + size // 2)
        y2 = min(h, cy + size // 2)
        self._face_box = (x1, y1, x2, y2)
        face = img[y1:y2, x1:x2]
        self._face_crop = cv2.resize(face, (96, 96))
        logger.warning("No face detected, using center crop")
        return True

    def generate(
        self,
        audio_pcm_16k: np.ndarray,
        fps: int = 25,
    ) -> bytes:
        """
        Generate lip-synced MP4 video from audio.

        Args:
            audio_pcm_16k: float32 audio at 16kHz
            fps: output video frame rate

        Returns:
            MP4 video bytes
        """
        if self._avatar_img is None or self._face_crop is None:
            raise RuntimeError("Avatar not set. Call set_avatar() first.")

        # 1. Audio → mel spectrogram → chunks
        mel = _melspectrogram(audio_pcm_16k)
        mel_chunks = _get_mel_chunks(mel, fps)

        # 2. Prepare face input (same for every frame since avatar is static)
        face = self._face_crop.copy()  # 96x96 BGR
        face_masked = face.copy()
        face_masked[48:, :] = 0  # zero out bottom half (mouth region)

        # Normalize and stack: [masked, original] → (6, 96, 96)
        face_input = np.concatenate(
            [face_masked, face], axis=2
        ).transpose(2, 0, 1).astype(np.float32) / 255.0

        # 3. Run inference per frame
        frames = []
        x1, y1, x2, y2 = self._face_box  # type: ignore[misc]
        avatar = self._avatar_img

        for mel_chunk in mel_chunks:
            mel_batch = mel_chunk[np.newaxis, np.newaxis, :, :].astype(np.float32)
            img_batch = face_input[np.newaxis, :, :, :]

            pred = self._wav2lip.run(
                None,
                {"mel_spectrogram": mel_batch, "video_frames": img_batch},
            )[0][0]  # (3, 96, 96)

            # CHW → HWC, denormalize
            pred_face = (pred.transpose(1, 2, 0) * 255).clip(0, 255).astype(np.uint8)

            # Resize predicted face back to original face region size
            face_h = y2 - y1
            face_w = x2 - x1
            pred_resized = cv2.resize(pred_face, (face_w, face_h))

            # Composite onto avatar
            frame = avatar.copy()
            frame[y1:y2, x1:x2] = pred_resized
            frames.append(frame)

        # 4. Encode to MP4 using ffmpeg
        return self._encode_mp4(frames, fps)

    def _encode_mp4(self, frames: list[np.ndarray], fps: int) -> bytes:
        """Encode frames to MP4 bytes using ffmpeg pipe."""
        if not frames:
            return b""

        h, w = frames[0].shape[:2]

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            cmd = [
                "ffmpeg", "-y",
                "-f", "rawvideo",
                "-vcodec", "rawvideo",
                "-pix_fmt", "bgr24",
                "-s", f"{w}x{h}",
                "-r", str(fps),
                "-i", "pipe:0",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-tune", "zerolatency",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart+frag_keyframe+empty_moov",
                "-f", "mp4",
                tmp_path,
            ]

            proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            raw = b"".join(f.tobytes() for f in frames)
            _, stderr = proc.communicate(input=raw)

            if proc.returncode != 0:
                logger.error("ffmpeg error: %s", stderr.decode(errors="replace"))
                return b""

            with open(tmp_path, "rb") as f:
                return f.read()
        finally:
            os.unlink(tmp_path)


# ── Module-level singleton ───────────────────────────────────────────────────

_service: Optional[Wav2LipService] = None


def get_wav2lip_service() -> Wav2LipService:
    """Get or create the Wav2Lip service singleton."""
    global _service
    if _service is None:
        # Try common model locations
        for path in ["models/wav2lip", "../models/wav2lip"]:
            if Path(path).exists():
                _service = Wav2LipService(path)
                break
        if _service is None:
            raise FileNotFoundError(
                "Wav2Lip models not found. Expected at models/wav2lip/"
            )
    return _service
