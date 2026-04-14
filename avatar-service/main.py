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
import os
import shutil
import tempfile
import uuid
from pathlib import Path

import edge_tts
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

app = FastAPI(title="avatar-service")

# ── paths (all overridable via env) ──────────────────────────────────────────
WAV2LIP_DIR = Path(os.getenv("WAV2LIP_DIR", "/app/wav2lip"))
CHECKPOINT = Path(os.getenv("WAV2LIP_CHECKPOINT", "/app/checkpoints/wav2lip_gan.onnx"))
FACE_IMAGE = Path(os.getenv("FACE_IMAGE", "/app/face.jpg"))
INFERENCE_SCRIPT = WAV2LIP_DIR / "inference_onnxModel.py"
ENHANCER = os.getenv("WAV2LIP_ENHANCER", "none")  # none | gfpgan | gpen | codeformer | restoreformer


class GenerateRequest(BaseModel):
    text: str
    voice: str = "en-US-JennyNeural"


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "model_ready": CHECKPOINT.exists(),
        "face_ready": FACE_IMAGE.exists(),
        "script_ready": INFERENCE_SCRIPT.exists(),
    }


@app.post("/generate")
async def generate(req: GenerateRequest) -> Response:
    if not CHECKPOINT.exists():
        raise HTTPException(
            503,
            f"Wav2Lip model not found at {CHECKPOINT}. "
            "Download all ONNX checkpoints from https://drive.google.com/drive/folders/1BGl9bmMtlGEMx_wwKufJrZChFyqjnlsQ "
            "and place them in /app/checkpoints/.",
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
        cmd = [
            "python",
            str(INFERENCE_SCRIPT),
            "--checkpoint_path", str(CHECKPOINT),
            "--face", str(FACE_IMAGE),
            "--audio", str(wav_path),
            "--outfile", str(out_path),
            "--fps", "25",
            "--hq_output",
            "--denoise",
            "--enhancer", ENHANCER,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(WAV2LIP_DIR),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0 or not out_path.exists():
            err = stderr.decode(errors="replace")[-500:]
            raise HTTPException(500, f"Wav2Lip inference failed: {err}")

        return Response(content=out_path.read_bytes(), media_type="video/mp4")

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
