#!/usr/bin/env bash
# Downloads wav2lip-onnx-HQ models from Google Drive into ./models/
# Run once before `docker compose build`.
set -e

echo "Installing gdown..."
pip install -q gdown

echo "Downloading models (this will take a few minutes)..."
gdown --folder "1BGl9bmMtlGEMx_wwKufJrZChFyqjnlsQ" -O ./models/ --fuzzy

echo ""
echo "Done. Run: docker compose build && docker compose up"
