# grillme

AI mock interview platform. Paste a job description → get a real LeetCode problem matched to the company's interview style → practice with a voice-driven AI interviewer → get scored across six axes.

**Stack:** FastAPI (Python 3.13) · React 19 + Vite + TypeScript · uv · pnpm · SQLite · edge-tts · Wav2Lip

---

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.13+ | [python.org](https://python.org) |
| uv | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Node.js | 20+ | [nodejs.org](https://nodejs.org) |
| pnpm | latest | `npm install -g pnpm` |
| Docker + Compose | latest | [docker.com](https://docs.docker.com/get-docker/) — only needed for the avatar service |

---

## Option A — Local dev (fastest, no Docker)

### 1. Clone & configure

```bash
git clone <repo-url> grillme
cd grillme
cp .env.example .env        # then edit .env with your API key (see below)
```

### 2. Pick a free LLM provider and add the key to `.env`

Open `.env` and set **one** of these:

```env
# ── Groq (recommended — free, fast) ─────────────────────────────────
LLM_PROVIDER=groq
LLM_MODEL=llama-3.3-70b-versatile
GROQ_API_KEY=gsk_...          # get free key at console.groq.com

# ── Google Gemini (generous free tier) ──────────────────────────────
# LLM_PROVIDER=gemini
# LLM_MODEL=gemini-2.0-flash
# GEMINI_API_KEY=AIza...      # get free key at aistudio.google.com

# ── OpenAI ──────────────────────────────────────────────────────────
# LLM_PROVIDER=openai
# LLM_MODEL=gpt-4o-mini
# OPENAI_API_KEY=sk-...
```

Other `.env` values (leave as-is for local dev):
```env
DATABASE_URL=sqlite+aiosqlite:///./app/data/grillme.db
AVATAR_PROVIDER=local         # change to wav2lip once Docker avatar is set up
```

### 3. Run the backend

```bash
cd backend
uv sync                       # installs dependencies (first run only)
uv run uvicorn app.main:app --reload
# → http://localhost:8000
# → API docs: http://localhost:8000/docs
```

### 4. Run the frontend

```bash
cd frontend
pnpm install                  # first run only
pnpm dev
# → http://localhost:5173
```

Open **http://localhost:5173**, paste a job description, and start interviewing.

---

## Option B — Docker Compose (full stack + talking head)

### 1. Configure `.env`

Same as Option A — create `.env` in the project root with your LLM key.

### 2. Build images

```bash
docker compose build
```

> The avatar-service image clones [wav2lip-onnx](https://github.com/instant-high/wav2lip-onnx) and installs ONNX runtime. First build takes ~5 minutes.

### 3. Download the Wav2Lip model (one-time, ~360 MB)

1. Open the [wav2lip-onnx repo](https://github.com/instant-high/wav2lip-onnx) → README → download `wav2lip_gan.onnx` from the Google Drive link
2. Load it into the Docker volume:

```bash
docker run --rm \
  -v grillme_avatar_models:/dst \
  -v /absolute/path/to/wav2lip_gan.onnx:/src/model.onnx \
  alpine cp /src/model.onnx /dst/wav2lip_gan.onnx
```

### 4. Start everything

```bash
docker compose up
# → http://localhost:5173
```

> Without the model file the avatar service returns a 503 and the app falls back to the animated SVG avatar — everything else still works.

---

## `.env` reference

```env
# LLM provider (required — pick one)
LLM_PROVIDER=groq
LLM_MODEL=llama-3.3-70b-versatile

OPENAI_API_KEY=
GROQ_API_KEY=
GEMINI_API_KEY=

# Database
DATABASE_URL=sqlite+aiosqlite:///./app/data/grillme.db

# Avatar (optional — wav2lip needs Docker setup above)
AVATAR_PROVIDER=local               # local | wav2lip
AVATAR_SERVICE_URL=http://localhost:8080
VIDEOS_DIR=/tmp/grillme_videos
```

---

## Free LLM providers

| Provider | Sign-up | Notes |
|----------|---------|-------|
| [Groq](https://console.groq.com) | Free | Fastest streaming — `llama-3.3-70b-versatile` |
| [Google AI Studio](https://aistudio.google.com) | Free | `gemini-2.0-flash`, generous daily limits |
| [OpenRouter](https://openrouter.ai) | Free tier | Many models via one API key |

---

## Running tests

```bash
cd backend && uv run pytest -x -q
```

---

## Architecture

```
Browser
  Home.tsx          — JD / URL / text input → create session
  Session.tsx       — live interview: editor + voice loop + avatar PIP
  Scorecard.tsx     — six-axis results
  Settings.tsx      — voice & LLM preferences

FastAPI
  /api/sessions/*   — session lifecycle
  /api/code/*       — run / test code in sandbox
  /api/voice/*      — TTS (edge-tts → MP3)
  /api/avatar/*     — talking head video generation + serving

  Agents: Parse → Problem → Persona → Score → Memory
  LLMService: OpenAI | Groq | Gemini (swap via .env)

Avatar service (Docker only)
  POST /generate    — text → edge-tts audio → wav2lip-onnx → MP4
  Runs fully local, no API key needed
```

---

## Project status

| Milestone | Feature | Status |
|-----------|---------|--------|
| M1–M4 | Core backend + API | Done |
| M5 | LeetCode URL input | Done |
| M6 | Curated question bank | Done |
| M7 | Multi-agent pipeline | Done |
| M8 | Voice loop + animated avatar | Done |
| M9 | Docker Compose deployment | Done |
| M10 | Wav2Lip local talking head | Done (needs model download) |
| M11 | PostgreSQL + Alembic | Planned |
| M12 | Tool use (web search) | Planned |
