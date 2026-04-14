FROM python:3.10-slim

# System deps: ffmpeg for video, OpenCV runtime libs, unzip for model setup
# No C++ compiler needed — HQ version uses pre-built ONNX face detectors
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsm6 \
    libxext6 \
    libxrender1 \
    git \
    curl \
    unzip \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Clone wav2lip-onnx-HQ (code only; models mounted at runtime via /app/models)
RUN git clone --depth 1 https://github.com/instant-high/wav2lip-onnx-HQ /app/wav2lip

# Python deps — install before copying app code for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# FastAPI service + entrypoint
COPY main.py .
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# Default face image (public demo presenter — override by mounting /app/face.jpg)
RUN curl -fsSL \
    "https://create-images-results.d-id.com/DefaultPresenters/Noelle_f/image.png" \
    -o /app/face.jpg

# /app/models is bind-mounted from the host at runtime (see docker-compose.yml)
RUN mkdir -p /app/models

EXPOSE 8080

ENTRYPOINT ["/app/entrypoint.sh"]
