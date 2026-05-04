"""
Wav2Lip ONNX-HQ avatar microservice.

POST /generate  { text, voice } → MP4 video bytes
GET  /health    → { status, model_ready }

Setup (one-time):
  1. Clone https://github.com/instant-high/wav2lip-onnx-HQ into /app/wav2lip
     (done automatically in Docker image)
  2. Download all ONNX checkpoints from Google Drive into /app/checkpoints/:
     https://drive.google.com/drive/folders/1BGl9bmMtlGEMx_wwKufJrZChFyqjnlsQ
     Required: wav2lip_gan.onnx (≈360 MB) + face detector models
  3. Place a face image at /app/face.jpg  (or set FACE_IMAGE env var)

Optional env vars:
  WAV2LIP_ENHANCER  — face enhancer: none (default) | gfpgan | gpen | codeformer | restoreformer
                      gfpgan gives the best quality but requires its ONNX model in /app/checkpoints/
"""

import asyncio
import importlib
import logging
import os
import shutil
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Literal

import edge_tts
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

app = FastAPI(title="avatar-service")
logger = logging.getLogger(__name__)

# ── paths (all overridable via env) ──────────────────────────────────────────
WAV2LIP_DIR = Path(os.getenv("WAV2LIP_DIR", "/app/wav2lip"))
FACE_IMAGE = Path(os.getenv("FACE_IMAGE", "/app/face.jpg"))
INFERENCE_SCRIPT = WAV2LIP_DIR / "inference_onnxModel.py"
ENHANCER = os.getenv("WAV2LIP_ENHANCER", "none")  # none|gfpgan|gpen|codeformer|restoreformer
LIVE_FPS = int(os.getenv("WAV2LIP_LIVE_FPS", "15"))
FINAL_FPS = int(os.getenv("WAV2LIP_FINAL_FPS", "25"))
LIVE_WORKERS = int(os.getenv("WAV2LIP_LIVE_WORKERS", "1"))


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


FINAL_DENOISE = _env_flag("WAV2LIP_FINAL_DENOISE", True)

_live_executor = ProcessPoolExecutor(max_workers=max(1, LIVE_WORKERS))
_live_worker_ready = False


def _find_checkpoint() -> Path:
    """Return the wav2lip ONNX checkpoint, auto-detecting filename if needed."""
    explicit = os.getenv("WAV2LIP_CHECKPOINT")
    if explicit:
        return Path(explicit)
    checkpoints_dir = WAV2LIP_DIR / "checkpoints"
    # Try common names first
    for name in ("wav2lip_gan.onnx", "wav2lip_384.onnx", "wav2lip.onnx"):
        p = checkpoints_dir / name
        if p.exists():
            return p
    # Fall back to any .onnx in the dir
    candidates = sorted(checkpoints_dir.glob("*.onnx"))
    if candidates:
        return candidates[0]
    return checkpoints_dir / "wav2lip_gan.onnx"  # for error message


CHECKPOINT = _find_checkpoint()


class GenerateRequest(BaseModel):
    text: str
    voice: str = "en-US-JennyNeural"
    persona: str | None = None
    quality: Literal["interactive", "final"] = "interactive"


_WORKER_INFERENCE_MODULE = None


def _ensure_live_worker_ready(
    wav2lip_dir: str,
    checkpoint_path: str,
    face_image: str,
    fps: int,
) -> None:
    global _WORKER_INFERENCE_MODULE
    if _WORKER_INFERENCE_MODULE is not None:
        return

    wav2lip_path = Path(wav2lip_dir)
    os.chdir(wav2lip_path)
    (wav2lip_path / "temp").mkdir(parents=True, exist_ok=True)
    if wav2lip_dir not in sys.path:
        sys.path.insert(0, wav2lip_dir)

    argv_backup = sys.argv[:]
    try:
        # inference_onnxModel.py parses argv at import-time.
        sys.argv = [
            "inference_onnxModel.py",
            "--checkpoint_path", checkpoint_path,
            "--face", face_image,
            "--audio", face_image,  # placeholder required by parser
            "--outfile", str(wav2lip_path / "temp" / "warmup.mp4"),
            "--fps", str(fps),
            "--enhancer", "none",
        ]
        module = importlib.import_module("inference_onnxModel")
    finally:
        sys.argv = argv_backup

    module.args.checkpoint_path = checkpoint_path
    module.args.face = face_image
    module.args.fps = float(fps)
    module.args.enhancer = "none"
    module.args.hq_output = False
    module.args.denoise = False
    # resize_factor: downsample face internally during inference for speed.
    # Face image should be ≥256px; resize_factor=2 halves it to ~256px at runtime.
    if hasattr(module.args, "resize_factor"):
        module.args.resize_factor = 2

    # Keep ONNX model loaded in this long-lived worker process.
    cached_model = module.load_model(module.device)
    module.load_model = lambda _device: cached_model
    _WORKER_INFERENCE_MODULE = module


def _render_interactive_video(
    wav2lip_dir: str,
    checkpoint_path: str,
    face_image: str,
    audio_path: str,
    output_path: str,
    fps: int,
) -> None:
    _ensure_live_worker_ready(
        wav2lip_dir=wav2lip_dir,
        checkpoint_path=checkpoint_path,
        face_image=face_image,
        fps=fps,
    )

    module = _WORKER_INFERENCE_MODULE
    module.args.checkpoint_path = checkpoint_path
    module.args.face = face_image
    module.args.audio = audio_path
    module.args.outfile = output_path
    module.args.fps = float(fps)
    module.args.enhancer = "none"
    module.args.hq_output = False
    module.args.denoise = False
    if hasattr(module.args, "resize_factor"):
        module.args.resize_factor = 2
    module.main()


async def _video_codec(path: Path) -> str:
    proc = await asyncio.create_subprocess_exec(
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        err = stderr.decode(errors="replace")[-500:]
        raise HTTPException(500, f"ffprobe failed: {err}")
    codec = stdout.decode(errors="replace").strip()
    if not codec:
        raise HTTPException(500, "Could not detect output video codec")
    return codec


async def _ensure_web_playable_mp4(path: Path) -> None:
    codec = await _video_codec(path)
    if codec == "h264":
        return

    normalized = path.with_name(f"{path.stem}_web.mp4")
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-y",
        "-i",
        str(path),
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        str(normalized),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0 or not normalized.exists():
        err = stderr.decode(errors="replace")[-500:]
        raise HTTPException(500, f"ffmpeg transcode failed: {err}")
    normalized.replace(path)


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "model_ready": CHECKPOINT.exists(),
        "face_ready": FACE_IMAGE.exists(),
        "script_ready": INFERENCE_SCRIPT.exists(),
        "live_worker_ready": _live_worker_ready,
    }


@app.post("/generate")
async def generate(req: GenerateRequest) -> Response:
    if req.persona:
        logger.debug("persona=%s", req.persona)
    if not CHECKPOINT.exists():
        raise HTTPException(
            503,
            f"Wav2Lip model not found at {CHECKPOINT}. "
            "Download ONNX checkpoints from Google Drive (see README) "
            "and place them in the models/ folder.",
        )
    if not FACE_IMAGE.exists():
        raise HTTPException(
            503,
            f"Face image not found at {FACE_IMAGE}. "
            "Place a portrait JPG at /app/face.jpg or set the FACE_IMAGE env var.",
        )
    if not INFERENCE_SCRIPT.exists():
        raise HTTPException(
            503,
            f"Wav2Lip script not found at {INFERENCE_SCRIPT}. "
            "Clone https://github.com/instant-high/wav2lip-onnx-HQ into /app/wav2lip.",
        )

    tmp_dir = Path(tempfile.mkdtemp(prefix="av_"))
    wav_path = tmp_dir / "speech.wav"
    out_path = tmp_dir / "output.mp4"

    try:
        # 1. Text → WAV via edge-tts
        tts = edge_tts.Communicate(text=req.text, voice=req.voice)
        await tts.save(str(wav_path))

        if not wav_path.exists() or wav_path.stat().st_size == 0:
            raise HTTPException(500, "TTS failed to produce audio")

        # 2. WAV + face image → MP4 via Wav2Lip ONNX-HQ
        if req.quality == "interactive":
            loop = asyncio.get_running_loop()
            try:
                await loop.run_in_executor(
                    _live_executor,
                    _render_interactive_video,
                    str(WAV2LIP_DIR),
                    str(CHECKPOINT),
                    str(FACE_IMAGE),
                    str(wav_path),
                    str(out_path),
                    LIVE_FPS,
                )
            except Exception as exc:
                raise HTTPException(500, f"Wav2Lip interactive inference failed: {exc}") from exc
        else:
            cmd = [
                "python",
                str(INFERENCE_SCRIPT),
                "--checkpoint_path", str(CHECKPOINT),
                "--face", str(FACE_IMAGE),
                "--audio", str(wav_path),
                "--outfile", str(out_path),
                "--fps", str(FINAL_FPS),
                "--hq_output",
                "--enhancer", ENHANCER,
            ]
            if FINAL_DENOISE and (WAV2LIP_DIR / "resemble_denoiser" / "denoiser.onnx").exists():
                cmd.append("--denoise")
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(WAV2LIP_DIR),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()

            if proc.returncode != 0 or not out_path.exists():
                err = stderr.decode(errors="replace")[-500:]
                raise HTTPException(500, f"Wav2Lip final inference failed: {err}")

        if not out_path.exists() or out_path.stat().st_size == 0:
            raise HTTPException(500, "Wav2Lip failed to produce video output")

        await _ensure_web_playable_mp4(out_path)

        return Response(content=out_path.read_bytes(), media_type="video/mp4")

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@app.on_event("startup")
async def warm_interactive_worker() -> None:
    global _live_worker_ready
    if not CHECKPOINT.exists() or not FACE_IMAGE.exists() or not INFERENCE_SCRIPT.exists():
        _live_worker_ready = False
        return
    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(
            _live_executor,
            _ensure_live_worker_ready,
            str(WAV2LIP_DIR),
            str(CHECKPOINT),
            str(FACE_IMAGE),
            LIVE_FPS,
        )
        _live_worker_ready = True
    except Exception:
        logger.exception("Failed to warm interactive wav2lip worker")
        _live_worker_ready = False


@app.on_event("shutdown")
async def shutdown_live_worker() -> None:
    _live_executor.shutdown(wait=False, cancel_futures=True)
