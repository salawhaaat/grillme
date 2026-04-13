FROM python:3.10-slim

# System deps: ffmpeg for video, OpenCV runtime libs, C++ compiler for insightface
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsm6 \
    libxext6 \
    libxrender1 \
    git \
    curl \
    build-essential \
    cmake \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Clone wav2lip-onnx (code only; models downloaded separately into a volume)
RUN git clone --depth 1 https://github.com/instant-high/wav2lip-onnx /app/wav2lip

# Python deps — install before copying app code for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# FastAPI service entrypoint
COPY main.py .

# Default face image (public demo presenter — override by mounting /app/face.jpg)
RUN curl -fsSL \
    "https://create-images-results.d-id.com/DefaultPresenters/Noelle_f/image.png" \
    -o /app/face.jpg

# Volume mount point for wav2lip_gan.onnx
RUN mkdir -p /app/checkpoints

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
