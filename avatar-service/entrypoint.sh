#!/bin/bash
# Copies model files from /app/models (bind-mounted local folder)
# into the correct subdirectories of the wav2lip repo before starting.

set -e

MODELS=/app/models
W=/app/wav2lip

echo "[avatar] Setting up model files..."

place() {
  [ -f "$1" ] || return 0
  mkdir -p "$(dirname "$2")"
  cp -n "$1" "$2" && echo "  placed: $2" || true
}

# Flat .onnx files
place "$MODELS/blendmasker.onnx"     "$W/blendmasker/blendmasker.onnx"
place "$MODELS/recognition.onnx"     "$W/faceID/recognition.onnx"
place "$MODELS/xseg.onnx"            "$W/xseg/xseg.onnx"
place "$MODELS/denoiser.onnx"        "$W/resemble_denoiser/denoiser.onnx"
place "$MODELS/denoiser_fp16.onnx"   "$W/resemble_denoiser/denoiser_fp16.onnx"

# Zips → extract into wav2lip subdirectory
extract() {
  [ -f "$1" ] || return 0
  echo "  extracting: $1 → $2"
  mkdir -p "$2"
  unzip -o -q "$1" -d "$2"
}

extract "$MODELS/wav2lip_onnx_models.zip"    "$W/checkpoints"
extract "$MODELS/wav2lip_insightface_func.zip" "$W/utils"
extract "$MODELS/wav2lip_face_occluder.zip"  "$W/xseg"
extract "$MODELS/wav2lip_seg_mask.zip"       "$W/blendmasker"

echo "[avatar] Model setup done."

exec uvicorn main:app --host 0.0.0.0 --port 8080
