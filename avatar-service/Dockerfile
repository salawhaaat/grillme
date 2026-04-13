FROM python:3.10-slim

# System deps: ffmpeg for video encoding, OpenCV runtime libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsm6 \
    libxext6 \
    libxrender1 \
    git \
    curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Clone wav2lip-onnx (code only; models downloaded separately)
RUN git clone --depth 1 https://github.com/instant-high/wav2lip-onnx /app/wav2lip

# Python deps
# onnxruntime: use standard wheel (arm64 binaries included since v1.16)
# insightface 0.2.1 matches the antelope face-detector bundled in the repo
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Default face image – D-ID's public Noelle presenter (CC-licensed for demos).
# Override by mounting your own at /app/face.jpg or setting FACE_IMAGE env var.
RUN curl -fsSL \
    "https://create-images-results.d-id.com/DefaultPresenters/Noelle_f/image.png" \
    -o /app/face.jpg

# Checkpoints volume mount point (wav2lip_gan.onnx goes here)
RUN mkdir -p /app/checkpoints

# Models directory for insightface antelope face detector (bundled in repo)
# Nothing to copy – the repo clone above already includes insightface_func/

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
