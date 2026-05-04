# grillme

AI mock interview platform. Paste a job description → get a LeetCode problem matched to the company's interview style → practice with a voice-driven AI interviewer → get scored across six axes.

**Stack:** FastAPI (Python 3.13) · React 19 + Vite + TypeScript + shadcn/ui · uv · pnpm · SQLite · edge-tts · Wav2Lip · faster-whisper · Silero VAD

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
# → http://localhost:80
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
| [Groq](https://console.groq.com) | Free | Fastest — `llama-3.3-70b-versatile` |
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
                      VAD (Silero) → STT (faster-whisper) → LLM → wav2lip video
  Scorecard.tsx     — six-axis results after finish
  Settings.tsx      — LLM provider + API key (POST /api/config, runtime override)
  History.tsx       — past sessions
  Notes / Profile / Resources / Whiteboard — utility pages

FastAPI (backend/)
  /api/sessions/*   — session lifecycle (create, get, message, finish, delete)
  /api/converse/*   — voice conversation (respond, stream, stream-text)
  /api/stt          — one-shot STT (POST raw WAV → transcript)
  /api/voice/*      — TTS (edge-tts → MP3)
  /api/avatar/*     — wav2lip job management + video serving
  /api/code/*       — run / test code in sandbox
  /api/problems/*   — LeetCode scraper + question bank
  /api/config       — runtime LLM key override (no restart needed)

  Services: LLMService · AvatarService · STT (faster-whisper) · Wav2LipService
            SentenceSplitter · TTS (edge-tts) · Sandbox · Scraper · QuestionBank

Avatar service (Docker only — avatar-service/)
  POST /generate    — text → edge-tts audio → wav2lip-onnx → MP4
                      quality=interactive (default, 15 FPS, warm worker)
                      quality=final (25 FPS, HQ + optional denoise)
  Runs fully local, no API key needed
```

### Voice pipeline detail

```
SESSION LOAD
  ├─ Poll GET /api/avatar/session/{id}/intro (every 2s)
  │     └─ ready → play wav2lip MP4 (audio + video)
  └─ 3-min timeout → TTS fallback (speakText)
       └─ either path sets openingDone=true → VAD starts

USER SPEAKS
  ├─ Silero VAD detects end-of-speech → Float32Array
  ├─ encodeWAV → POST /api/stt → transcript
  ├─ POST /api/converse/respond → {job_id, text}
  ├─ Pre-fetch TTS blob as fallback
  ├─ Poll GET /api/avatar/job/{job_id} until done → play video
  └─ Timeout fallback → play TTS blob
```

### nginx (Docker frontend)

- CORS headers for `SharedArrayBuffer` (`COOP: same-origin`, `COEP: credentialless`) — required by Silero VAD WASM
- Custom `types {}` block: `application/wasm` for VAD `.wasm` files, `application/javascript` for `.mjs`
- All `/api/*` requests proxied to backend with SSE + WebSocket support

---

## Project status

| Milestone | Feature | Status |
|-----------|---------|--------|
| M1–M4 | Core backend + API | Done |
| M5 | LeetCode URL input | Done |
| M6 | Curated question bank | Done |
| M7 | Multi-agent pipeline | Done |
| M8 | Voice loop (VAD + STT + TTS) | Done |
| M9 | Docker Compose deployment | Done |
| M10 | Wav2Lip local talking head | Done (needs model download) |
| M11 | PostgreSQL + Alembic | Planned |
| M12 | Tool use (web search) | Planned |

### Known limitations

- wav2lip on CPU is still latency-heavy; interactive mode is faster than final/HQ mode
- STT requires mic permission + `SharedArrayBuffer` support in the browser
- API key set via Settings UI persists only until container restart (no DB storage)
- `POST /api/sessions/{id}/message` (legacy) and `POST /api/converse/respond` (new) both save messages; scoring reads from DB so should reflect all turns — verify after a full session
