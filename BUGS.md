# GrillMe — Known Bugs & Issues

Last updated: May 3, 2026

---

## CRITICAL — App is broken

### BUG-001: Navigation broken — pages collapse instead of routing
**Symptom:** Clicking "Start Interview" on Home page collapses the form instead of navigating to `/session/{id}`. The router does not move to the session page.

**Root cause (suspected):** The `handleAnalyzeJD` function in `Home.tsx` was refactored to call `navigate()` directly after `api.createSession()`. However the Docker container is still serving a stale cached build (`index-CF6yWea-.css` with `304 Not Modified`). The new JS bundle (`index-CLBcYZdF.js`) is not being served.

**Files affected:**
- `frontend/src/pages/Home.tsx` — `handleAnalyzeJD` function
- Docker nginx cache

**Fix needed:**
1. Force Docker to serve the new build: `docker compose build --no-cache frontend && docker compose up`
2. Hard refresh in Chrome: `Cmd+Shift+R`
3. If still broken: open Chrome DevTools → Application → Storage → Clear site data, then reload

---

## HIGH — Voice / STT broken

### BUG-002: Push-to-talk mic never opens on Mac
**Symptom:** Mac OS mic indicator (orange dot in menu bar) never appears. VAD loads and starts but no audio is captured.

**Root cause:** `getUserMedia` is called eagerly on mount (to trigger the OS permission prompt), but the stream is immediately released. The actual PTT recording via `MediaRecorder` only starts on button press. However, the permission prompt may not fire if the browser already has a cached "denied" state, or if the eager `getUserMedia` call fails silently.

**Files affected:**
- `frontend/src/pages/Session.tsx` — eager `getUserMedia` useEffect on mount
- `frontend/src/lib/hooks/usePushToTalk.ts` — `startRecording()`

**Fix needed:**
- Check Chrome site permissions: `chrome://settings/content/microphone` — ensure `localhost:5173` is not blocked
- Check Mac System Settings → Privacy & Security → Microphone → Chrome must be enabled
- If permission is granted but mic still doesn't work, add console logging to `startRecording()` to see if `getUserMedia` throws

---

### BUG-003: VAD mode fires on background noise / unreliable
**Symptom:** In "Auto" (VAD) mode, the mic triggers on background noise. Speech detection is unreliable.

**Status:** Push-to-talk ("Hold" mode) was implemented as the primary mode. VAD is now opt-in via the mode badge on the mic button. This is a known limitation of Silero VAD in noisy environments.

**Workaround:** Use "Hold" mode (default).

---

## HIGH — Session creation / problem display

### BUG-004: Problem statement and starter code not shown in session
**Symptom:** After navigating to a session, the coding problem area shows "Preparing problem…" spinner indefinitely, or the problem never appears.

**Root cause:** The two-phase problem generation was implemented — `POST /api/sessions/create` now returns immediately with `problem_ready: false` and null `problem_statement`/`starter_code`. A background task runs `_paraphrase_and_cut` + `_generate_code_and_tests` and writes to DB. The frontend polls `GET /api/sessions/{id}/problem-status` every 3s.

**Known issue:** If the background task fails silently (LLM error, timeout), the problem never becomes ready and the spinner runs forever.

**Files affected:**
- `backend/app/routes/sessions.py` — `_process_problem_background()`, `create_session()`
- `frontend/src/pages/Session.tsx` — problem polling `useEffect`

**Fix needed:**
- Add a timeout to the problem polling (e.g. after 120s, show an error)
- Add error handling in `_process_problem_background` that writes a fallback problem to DB on failure
- Add a `GET /api/sessions/{id}/problem-status` response field `error: str | None` so frontend can surface failures

---

### BUG-005: Home page form collapses after session creation (stale build)
**Symptom:** After clicking "Start Interview", the form collapses and nothing happens. The session IS created (backend returns 200) but the router doesn't navigate.

**Root cause:** Same as BUG-001 — stale Docker build. The new `Home.tsx` calls `navigate()` directly but the old bundle still runs the old code that sets `formCollapsed(true)` and waits for a "Start Interview" button click.

**Fix:** Same as BUG-001 — force rebuild.

---

## MEDIUM — Performance

### BUG-006: LLM inference too slow (local Ollama qwen2.5:7b)
**Symptom:** Session creation takes 15-30s. Conversation turns take 5-25s depending on context length. Scorer takes 45-80s.

**Root cause:** qwen2.5:7b on Apple M1 Pro Metal is ~5s for short prompts, ~20s for medium, ~60s for long. Context window is 4096 tokens and fills up quickly.

**Mitigations already applied:**
- Persona generation skipped (hardcoded Elon)
- `_paraphrase_and_cut` + `_generate_code_and_tests` run in parallel
- Problem generation deferred to background task
- Message history trimmed to 12 turns
- CV context trimmed to 500 chars
- Full problem only included during coding phase
- Scorer refine pass skipped for Ollama

**Remaining options:**
- Switch to `qwen2.5:3b` or `llama3.2:3b` for ~2x speedup
- Use Groq (free tier, ~0.5s per call) — set `LLM_PROVIDER=groq` in `.env`

---

## MEDIUM — Pre-render setup

### BUG-007: Pre-render setup overlay shows stale data
**Symptom:** Setup overlay shows "38/38 clips ready — finishing up…" and never dismisses, OR shows 0/38 and never starts.

**Root cause:** Race condition between backend pre-render task starting and frontend first poll. The `_prerender_status` dict starts as `running: False, total: 0` — if the frontend polls before the task sets `running: True`, it sees 0 clips and either dismisses too early or loops.

**Files affected:**
- `frontend/src/pages/Home.tsx` — prerender polling `useEffect`
- `backend/app/services/avatar.py` — `prerender_scenario_clips()`

**Fix needed:** Backend should set `running: True` and `total: N` atomically BEFORE starting the render loop, not inside it.

---

## LOW — UI / UX

### BUG-008: Timer resets on page reload
**Status:** FIXED — timer now persists via `sessionStorage` keyed by session ID.

---

### BUG-009: Scorecard shows hallucinated feedback on short sessions
**Status:** FIXED — scorer returns neutral 5/10 scorecard if fewer than 2 user turns.

---

### BUG-010: "Rendering clip 39 of 38" off-by-one in setup overlay
**Status:** FIXED — now shows "All N clips rendered — finishing up…" when done.

---

## LOW — Backend

### BUG-011: `_build_system_prompt` crashes if `question_bank` is None during coding phase check
**Symptom:** 500 error on conversation turns for sessions created without a question bank.

**Root cause:** The coding phase detection in `_build_system_prompt` parses `session.question_bank` — if it's `None`, the code handles it correctly now, but the logic is fragile.

**Files affected:**
- `backend/app/routes/sessions.py` — `_build_system_prompt()`

**Status:** Fixed in latest code but not yet deployed (pending Docker rebuild).

---

## Environment notes

- **LLM:** Ollama `qwen2.5:7b` running locally, Docker reaches via `host.docker.internal:11434`
- **Avatar:** wav2lip in Docker, Elon `face.jpg`
- **STT:** `faster-whisper` `base.en` model, pre-downloaded in Docker image
- **Tests:** 193 passing, 1 skipped (backend)
- **Frontend build:** Clean (`pnpm build` exits 0)

## How to do a clean restart

```bash
# Stop everything
docker compose down

# Remove stale volumes (forces re-render of scenario clips)
docker volume rm grillme_avatar_videos grillme_db_data

# Full rebuild (no cache)
docker compose build --no-cache

# Start Ollama first
ollama serve

# Then start Docker
docker compose up
```

Open http://localhost:5173 — hard refresh with Cmd+Shift+R.
