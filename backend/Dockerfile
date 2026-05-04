FROM python:3.13-slim

# ffmpeg is required by faster-whisper to decode webm/opus audio from MediaRecorder
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Dependency layer — cached unless pyproject.toml / uv.lock change
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-cache

# Pre-download the Whisper model at build time so first STT request is instant
# Uses base.en (~150 MB) — override with STT_MODEL build arg if needed
ARG STT_MODEL=base.en
RUN uv run python -c "from faster_whisper import WhisperModel; WhisperModel('${STT_MODEL}', device='cpu', compute_type='int8'); print('Whisper model downloaded.')"

# App code
COPY app/ ./app/

# Ensure DB and video directories exist (overridden by Docker volumes at runtime)
RUN mkdir -p app/data /app/videos

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
