#!/usr/bin/env bash
# Downloads wav2lip-onnx-HQ models from Google Drive into ./models/
# Run once before `docker compose build`.
set -e

echo "Installing gdown..."
pip install -q gdown

echo "Downloading models (this will take a few minutes)..."
gdown --folder "1BGl9bmMtlGEMx_wwKufJrZChFyqjnlsQ" -O ./models/

# gdown creates a subfolder named after the Drive folder — flatten it
SUBFOLDER=$(ls -d ./models/*/ 2>/dev/null | grep -v '^\./models/$' | head -1)
if [ -n "$SUBFOLDER" ]; then
    echo "Flattening $SUBFOLDER into models/..."
    mv "$SUBFOLDER"* ./models/ 2>/dev/null || true
    rmdir "$SUBFOLDER" 2>/dev/null || true
fi

echo ""
echo "Done. Run: docker compose build && docker compose up"
