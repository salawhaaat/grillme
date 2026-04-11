# grillme

AI-powered mock interview platform. Paste a job description, get a real LeetCode problem matched to that company's interview style, and practice with a voice-driven AI interviewer that scores you across six axes.

**Stack:** FastAPI (Python 3.13) · React 19 + Vite + shadcn/ui (TypeScript) · uv · pnpm · SQLite · edge-tts

---

## Quick Start

```bash
# Backend
cp backend/.env.example backend/.env   # fill in LLM_PROVIDER + API key
cd backend && uv run uvicorn app.main:app --reload

# Frontend
cd frontend && pnpm install && pnpm dev

# Tests
cd backend && uv run pytest -x -q
```

**`.env` (pick one provider):**
```
LLM_PROVIDER=gemini          # openai | groq | gemini | ollama
LLM_MODEL=gemini-2.0-flash
GEMINI_API_KEY=your_key_here
DATABASE_URL=sqlite+aiosqlite:///./app/data/grillme.db
```

**Free LLM providers (no credit card):**

| Provider | Notes |
|----------|-------|
| [Google AI Studio](https://aistudio.google.com/) | Generous free tier — `gemini-2.0-flash` recommended |
| [Groq](https://console.groq.com/) | Fastest streaming — `llama-3.3-70b-versatile` |
| [GitHub Models](https://github.com/marketplace/models) | Free with GitHub account — GPT-4o, Llama, Mistral |
| [OpenRouter](https://openrouter.ai/) | Unified API — many free models |
| Ollama (local) | Zero cost, lower quality — set `OLLAMA_BASE_URL=http://localhost:11434` |

More options: [free-llm-api-resources](https://github.com/cheahjs/free-llm-api-resources)

**API docs** (server running): `http://localhost:8000/docs`

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│  Browser                                                            │
│  ┌──────────┐  ┌──────────────────────────────────────────────┐    │
│  │ Home.tsx │  │ Session.tsx (live interview)                 │    │
│  │  JD/URL/ │  │ ┌─────────────┐ ┌───────────┐ ┌──────────┐ │    │
│  │  Text    │  │ │ Problem     │ │  Monaco   │ │ Avatar   │ │    │
│  │  input   │  │ │ statement   │ │  Editor   │ │ PIP      │ │    │
│  │          │  │ │ (cut vers.) │ │           │ │ (status) │ │    │
│  │          │  │ │ + transcript│ │ Run/Test  │ │          │ │    │
│  └────┬─────┘  │ └─────────────┘ └───────────┘ └──────────┘ │    │
│       │        │                 Terminal (stdout/test results)│    │
│       │        └─────────────┬────────────────────────────────┘    │
│       │                      │  Web Speech API   HTML5 Audio       │
└───────┼──────────────────────┼─────────────────────────────────────┘
        │ REST + SSE           │
┌───────▼──────────────────────▼─────────────────────────────────────┐
│  FastAPI                                                            │
│                                                                     │
│  routes/sessions.py   routes/code.py   routes/voice.py             │
│       │                     │                │                      │
│  Orchestrator           SandboxService    TTSService                │
│  ├─ ParseAgent          (subprocess,     (edge-tts                  │
│  ├─ ProblemAgent         10s timeout)     MP3 bytes)                │
│  ├─ PersonaAgent                                                    │
│  ├─ ScorerAgent (six-axis + reflection)                             │
│  └─ MemoryAgent (weakness taxonomy)                                 │
│                                                                     │
│  LLMService (OpenAI | Groq | Gemini | Ollama)                       │
│  SQLite + aiosqlite (InterviewSession, Problem, UserMemory)         │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Backend

### Directory

```
backend/app/
├── main.py                   FastAPI app + lifespan (DB init)
├── core/
│   ├── config.py             Pydantic Settings (env vars)
│   ├── database.py           Async SQLAlchemy + idempotent migrations
│   └── logging.py
├── agents/
│   ├── base.py               Abstract BaseAgent
│   ├── orchestrator.py       Composes agents into pipelines
│   ├── parser.py             Extract company/role/skills from JD
│   ├── problem.py            Pick + paraphrase + cut LeetCode problem
│   ├── persona.py            Build interviewer persona + question bank
│   ├── scorer.py             Six-axis scoring with reflection loop
│   ├── memory.py             Normalize weaknesses to canonical taxonomy
│   └── schemas.py            Pydantic I/O types for all agents
├── models/
│   ├── session.py            InterviewSession ORM model
│   ├── problem.py            Problem cache (scraped LeetCode)
│   └── user_memory.py        Cross-session weakness tracking
├── routes/
│   ├── sessions.py           Session lifecycle endpoints
│   ├── chat.py               Pure LLM streaming (non-session)
│   ├── code.py               Run / test / share code
│   └── voice.py              TTS endpoint
└── services/
    ├── llm.py                LLMService (provider abstraction)
    ├── tts.py                TTSService (edge-tts wrapper)
    ├── sandbox.py            SandboxService (subprocess isolation)
    ├── scraper.py            LeetCode GraphQL scraper
    ├── question_bank.py      Curated question bank (GitHub data)
    ├── github_scraper.py     Scrapes GitHub interview question repos
    ├── research.py           Web search enrichment (stub)
    ├── jd.py                 OA platform detection utils
    └── tools.py              Tool registry (future tool-use)
```

### Agent Pipeline

Each session creation triggers a sequential + parallel agent pipeline:

```
ParseAgent                       (if source=jd)
  Input : raw JD text
  Output: ParsedJD { company, role, level, key_skills, focus_areas }
  Method: LLM JSON mode + Pydantic validation

ProblemAgent
  Input : ParsedJD + user_weaknesses (from UserMemory)
  Steps :
    1. _pick_slug_for_company()
       - QuestionBankService.get_for_company()   ← GitHub-scraped bank
       - _weighted_pick()                         ← 2x weight if matches user weakness
       - _llm_guess_slug()                        ← fallback if company unknown
    2. ScraperService.scrape(leetcode_url)        ← LeetCode GraphQL
    3. _paraphrase_and_cut()                      ← LLM rewrites in interviewer voice
                                                    removes examples/constraints from user view
    4. _generate_code_and_tests()                 ← LLM generates starter code + 5-8 test cases
  Output: CodingProblem { title, difficulty, problem_statement,
                          full_problem, starter_code, test_cases }

PersonaAgent
  Input : ParsedJD + optional research intel + user_weaknesses
  Runs asyncio.gather():
    - Generate interviewer persona (name, background, style)
    - Generate question bank (warmup / trivia / culture_fit / coding / closing)
    - Generate prep plan (ranked study topics)
  Output: PersonaOutput { persona_text, question_bank, prep_plan, oa_platform }

ScorerAgent  (called at session finish)
  Two-step reflection:
    1. Draft  — LLM scores all 6 axes with one-line comments
    2. Refine — second LLM call calibrates scores (avoids hallucination drift)
  Six axes:
    technical_correctness  25%  — did the solution work?
    process_of_thought     20%  — clarity of reasoning and approach
    curiosity              15%  — quality of clarifying questions asked upfront
    self_presentation      15%  — explained trade-offs, communicated clearly
    code_quality           15%  — readability, style, edge cases
    closing_questions      10%  — specific, thoughtful questions at end
  Output: ScorecardV2 { overall_score, axes, strengths, areas_to_improve, recommendation }

MemoryAgent  (called after scoring)
  Input : ScorecardV2.areas_to_improve
  Task  : Extract 2-4 canonical weakness tags
  Tags  : communication | problem_solving | system_design | time_complexity
          coding_speed | debugging | leadership
  Fallback: keyword extraction if LLM output is noisy
  Output: list[str] → upserted into UserMemory table (frequency tracking)
```

### HTTP Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/sessions/create` | Create session (JD / URL / text) |
| `POST` | `/api/sessions/from-jd` | Legacy JD-only session |
| `POST` | `/api/sessions/{id}/message` | Send message, stream LLM response (SSE) |
| `POST` | `/api/sessions/{id}/finish` | Score interview, extract weaknesses |
| `GET`  | `/api/sessions/` | List all sessions |
| `GET`  | `/api/sessions/{id}` | Fetch full session |
| `DELETE` | `/api/sessions/{id}` | Delete session |
| `POST` | `/api/code/run` | Execute code in sandbox (10s timeout) |
| `POST` | `/api/code/test` | Run test suite against solution |
| `POST` | `/api/code/share` | Log code + results into session messages |
| `POST` | `/api/voice/speak-session/{id}` | Synthesize latest assistant message → MP3 |

**Session creation** (`POST /api/sessions/create`):
```
1. Load top-5 user weaknesses from UserMemory
2. orchestrator.run_interview_pipeline(source, content, weaknesses)
3. LLM generates opening message (presents problem in persona's voice)
4. Persist InterviewSession to DB
5. Return { session_id, problem, starter_code, opening_message }
```

**Message handler** (`POST /api/sessions/{id}/message`):
```
1. Load session.messages (full history as JSON)
2. _build_system_prompt():
   - Persona text + difficulty modifiers (rare=hints offered, well_done=harsh)
   - full_problem injected (hidden from user; LLM has complete spec)
   - Rule: "Only reveal constraints when candidate explicitly asks"
   - Latest shared code block (if any)
   - Question bank structure (if JD mode: warmup → trivia → culture → coding → closing)
3. LLMService.stream_chat() → SSE chunks to frontend
4. On complete: save message + update token counts
```

### Database Models

**InterviewSession**
```
id, mode (jd/problem/url), difficulty (rare/medium/well_done)
company, role, level
persona, question_bank (JSON), prep_plan
jd_raw, problem_url, problem_statement, full_problem
starter_code, test_cases (JSON), method_name
messages (JSON array), scorecard (JSON)
prompt_tokens, completion_tokens, total_tokens
created_at, finished_at
```

**Problem** — LeetCode scrape cache (`title, difficulty, url, description, scraped_at`)

**UserMemory** — cross-session weakness tracking (`area, frequency, last_session_id, updated_at`)

---

## Frontend

### Directory

```
frontend/src/
├── App.tsx                   React Router setup
├── pages/
│   ├── Home.tsx              Session creation (JD / URL / text input)
│   ├── Session.tsx           Live interview (editor + voice + avatar)  ← main UI
│   ├── Scorecard.tsx         Six-axis results display
│   ├── History.tsx           Past sessions list + replay
│   └── Settings.tsx          Voice/TTS preferences
├── components/
│   ├── Sidebar.tsx           Navigation
│   └── ui/                   shadcn/ui primitives
└── lib/
    ├── api/client.ts         All API calls (fetch wrapper + types)
    ├── hooks/
    │   └── useSpeechRecognition.ts   Web Speech API hook
    ├── constants/difficulty.ts
    └── utils.ts              cn(), color helpers
```

### Session.tsx — The Core Interview UI

Three-pane layout:
- **Left** — problem statement (cut version) + live speech transcript
- **Center-top** — Monaco editor (Python)
- **Center-bottom** — terminal (stdout / test results tabs)
- **Right** — floating avatar PIP (draggable, repositionable)

**Voice interview loop:**
```
1. Speech recognition captures user speech → transcript
2. isListening → false on silence
3. Auto-send transcript → POST /api/sessions/{id}/message
4. LLM streams response (captured internally)
5. playAssistantAudio() → POST /api/voice/speak-session/{id} → MP3 blob
6. HTML5 Audio plays → avatarSpeaking = true, mic disabled
7. Audio ends → avatarSpeaking = false, mic re-enables
8. Loop
```

**Code execution loop:**
```
1. User writes code in Monaco editor
2. "Run Code" → POST /api/code/run → stdout/stderr in terminal
3. "Run Tests" → POST /api/code/test → per-test pass/fail
4. Auto-call POST /api/code/share (appends [CODE UPDATE] block to messages)
5. Next LLM response references the submitted code and results
```

### useSpeechRecognition.ts

Wraps browser `SpeechRecognition` / `webkitSpeechRecognition`:
```typescript
{
  transcript: string    // current recognized text (interim + final combined)
  isListening: boolean  // mic active
  start(): void
  stop(): void
  isSupported: boolean
}
// Config: continuous=false, interimResults=true, lang="en-US"
```

**Session.tsx integration:**
```typescript
// Pause mic while avatar speaks or LLM is streaming
useEffect(() => {
  if (avatarSpeaking || streaming) stopListening()
  else startListening()
}, [avatarSpeaking, streaming])

// Auto-send on silence (continuous=false triggers onend)
useEffect(() => {
  if (isListening) { pendingTranscriptRef.current = transcript; return }
  const text = pendingTranscriptRef.current.trim()
  if (!text || streaming || avatarSpeaking) return
  pendingTranscriptRef.current = ""
  handleSend(text)
}, [isListening])
```

### api/client.ts

All HTTP calls go through this module — components never call `fetch()` directly.

```typescript
api.createSession(source, content, difficulty)  → CreateSessionResponse
api.getSession(id)                              → Session
api.listSessions()                              → SessionListItem[]
api.finishSession(id)                           → { scorecard }
api.runCode(code, stdin_input?)                 → RunResult
api.runTests(code, session_id)                  → TestResult
api.shareCode(session_id, code, run?, test?)    → { ok }
api.speakSession(session_id, voice?)            → Blob (audio/mpeg)
// streamMessage(sessionId, content) → AsyncGenerator<string>  (SSE)
```

---

## The Talking Head — Current State vs Target

### What it does today

`Session.tsx` renders a floating PIP in the bottom-right corner. It is a **pure status indicator**:

| State | Icon | Color | Text |
|-------|------|-------|------|
| Idle (audio off) | face | gray | "Audio off" |
| Idle (audio on) | face | gray | "Ready" |
| Listening | mic / waveform | blue | "Listening…" |
| Speaking | record_voice_over | orange | "Speaking" |

The avatar reacts to `avatarSpeaking` (true while MP3 plays) and `isListening` (from speech hook). It is draggable. **There is no facial animation, no lip sync, no expressions.** The AI interviewer's voice exists only in the TTS audio channel — the face is decoration.

### What it should do

The talking head should **simulate a live interviewer**:

1. **Lip sync** — mouth movements timed to TTS audio phonemes
2. **Eye contact + blinking** — idle animations to feel present
3. **Micro-expressions** — smile when praising, frown when challenging, raised eyebrow at an unclear answer
4. **Gaze direction** — looks at "camera" while speaking, looks down while "thinking"
5. **Personality-consistent rendering** — persona name/style influences avatar appearance

### The gap

```
Current:  transcript → LLM stream → TTS audio → HTML5 Audio.play()
                                               └─ avatarSpeaking = true (icon changes)

Target:   transcript → LLM stream → TTS audio + phoneme data
                                               ├─ HTML5 Audio.play()
                                               └─ 3D/2D face model
                                                  ├─ lip sync from phoneme timeline
                                                  ├─ idle animations (blink, breath)
                                                  └─ emotion keyframes (LLM tone → expression)
```

**Candidate approaches (not yet decided):**
- **Three.js + ready-player-me** avatar with `@readyplayerme/visage` lip sync
- **rhubarb-lip-sync** to generate mouth cue files from the MP3
- **HeyGen / D-ID API** for photorealistic talking head (adds latency + cost)
- **Simple 2D sprite** with mouth-open/closed frames synced to audio amplitude (fastest path)

The avatar block lives inline in `Session.tsx`. Replacing it requires:
1. Extract PIP block → `components/Avatar.tsx`
2. Pass `avatarSpeaking`, `isListening`, and audio ref as props
3. Implement face rendering inside that component

---

## Data Flow

### Session Creation

```
Home.tsx
  POST /api/sessions/create { source, content, difficulty }
    │
    ├─ LoadUserMemory (top-5 weaknesses)
    ├─ ParseAgent → ParsedJD
    ├─ ProblemAgent → CodingProblem
    │    ├─ QuestionBank → slug (frequency + weakness weighted)
    │    ├─ LeetCode GraphQL → full problem text
    │    ├─ LLM paraphrase → cut problem statement (user view)
    │    └─ LLM generate → starter_code + test_cases
    └─ PersonaAgent.build_voice() → persona_text
    
  Create InterviewSession in DB
  LLM → opening_message (presents problem in persona's voice)
  
  Response → { session_id, problem_statement, starter_code, opening_message }
  Navigate to /session/{id}
```

### Interview Loop

```
User speaks
  │
  useSpeechRecognition → transcript
  │
  handleSend(transcript)
  POST /api/sessions/{id}/message
    │
    _build_system_prompt:
      - persona + difficulty modifiers
      - full_problem (never shown to user)
      - "reveal constraints only when asked"
      - latest shared code (if any)
    │
    LLMService.stream_chat() → SSE chunks
    Save assistant message to session.messages
    │
  playAssistantAudio()
  POST /api/voice/speak-session/{id}?voice=GuyNeural
    │
    TTSService.synthesize(latest_message) → MP3 bytes
    │
  Audio plays → avatarSpeaking=true → mic disabled
  Audio ends  → avatarSpeaking=false → mic re-enables → loop
```

### Scoring

```
POST /api/sessions/{id}/finish
  │
  ScorerAgent.score_six_axes(messages, persona, problem)
    ├─ Draft scorecard (LLM pass 1)
    └─ Refine scorecard (LLM pass 2 — reflection/calibration)
  │
  MemoryAgent.extract_weaknesses(areas_to_improve)
    └─ Normalize → canonical tags → upsert UserMemory
  │
  Save scorecard + finished_at to session
  Response → ScorecardV2

Scorecard.tsx
  ├─ Overall score (ring, color-coded)
  ├─ Six-axis bars (0-10 per axis + one-line comment each)
  ├─ Strengths + areas_to_improve bullets
  └─ Recommendation (hire / no_hire / strong_hire)
```

---

## Key Architecture Decisions

See [`_project/decisions.md`](_project/decisions.md) for full ADRs. Summary:

| ADR | Decision | Reason |
|-----|----------|--------|
| 001 | SQLite (not PostgreSQL) | Single-dev, local-first; swap later |
| 003 | LLMService abstraction | Change provider via `.env`, no code changes |
| 005 | JD-first entry (not LeetCode URL) | Mirrors how candidates actually prep |
| 012 | Problem-first flow (no pre-interview prep plan) | Interview starts immediately |
| 013 | Paraphrase + cut real problems | LLM has full spec; user only sees cut version |
| 014 | Six-axis scorecard | Actionable, multi-dimensional feedback |
| 015 | Curiosity is scored, not prompted | Realistic — interviewer never announces it |
| 016 | Unified `/create` endpoint (JD/URL/text) | One backend path |
| 018 | Avatar PIP is placeholder | Real talking head is M11; not started |
| 019 | GitHub question bank as primary source | Frequency data beats LLM guessing |
| 020 | Ollama as first-class provider | Zero API cost for local dev |

---

## Project Status

| Milestone | Feature | Status |
|-----------|---------|--------|
| M1–M4 | Core backend + API | Done |
| M5 | LeetCode URL input | Done |
| M6 | Curated question bank | Done |
| M7 | Multi-agent pipeline (parse, problem, persona, score, memory) | Done |
| M8 | Voice loop (speech recognition + TTS + avatar PIP) | Done — avatar is status-only |
| M9 | Docker deployment | Planned |
| M10 | PostgreSQL + Alembic migrations | Planned |
| **M11** | **Talking head with lip sync + expressions** | **Not started — core product gap** |
| M12 | Tool use (agent calls web search) | Planned |

---

## Data Storage

SQLite database — stored locally, never committed to git:
```
backend/app/data/grillme.db
```
Delete it to reset all sessions. Schema recreates automatically on next server start.

## Testing

```bash
cd backend && uv run pytest -x -q                              # all tests
cd backend && uv run pytest tests/test_problem_agent.py        # one file
```

Test files: `test_agents`, `test_problem_agent`, `test_scorer_six_axes`, `test_interview_pipeline`, `test_sandbox`, `test_memory`, `test_tts`
