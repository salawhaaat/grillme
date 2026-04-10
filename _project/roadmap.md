# Roadmap

## Milestone 1 — Backend Foundation ✅
- [x] FastAPI app skeleton + health endpoint
- [x] Project structure (routes / services / core / models)
- [x] SQLite + SQLAlchemy async
- [x] Logger, config, .env at project root
- [x] LeetCode scraper (POST /api/problems/scrape)

## Milestone 2 — LLM Service ✅
- [x] LLMService abstraction (OpenAI / Gemini)
- [x] POST /api/chat/stream — stateless streaming
- [x] Error handling (rate limit 429, provider errors, missing key)

## Milestone 3 — JD Interview Session ✅
**Agentic patterns:** Prompt Chaining · Tool Use · Memory (Ch 1, 5, 8)

- [x] InterviewSession model — mode, jd_raw, company, role, level, persona, scorecard, messages
- [x] `services/jd.py` — JDService: parse JD → build persona → generate question bank (Prompt Chaining)
- [x] POST /api/sessions/from-jd — create session, return opening message
- [x] POST /api/sessions/{id}/message — stream AI response, save messages to DB
- [x] GET /api/sessions/{id} — fetch session + full message history
- [x] GET /api/sessions/ — list all sessions with scores
- [x] POST /api/sessions/{id}/finish — LLM generates structured scorecard

## Milestone 4 — Frontend MVP ✅
**Agentic patterns:** Human-in-the-Loop (Ch 13)

- [x] React 19 + Vite + TypeScript + Tailwind + shadcn/ui setup
- [x] 10 pages: Home, Session, Scorecard, Feedback, History, Profile, Settings, Notes, Resources, Whiteboard
- [x] Paste JD → review extracted info → start session
- [x] Streaming chat UI
- [x] Scorecard + Feedback screens
- [x] Sidebar navigation, branding (Exo 2 wordmark, Coolors palette)
- [x] Settings: provider toggle (sliding segmented control), API key input
- [x] Session history with scores + difficulty badges

## Milestone 5 — Scoring & Strategy ✅
**Agentic patterns:** Reflection · Planning · Parallelization · Routing (Ch 2, 3, 4, 6)

- [x] Routing: difficulty-based persona (rare/medium/well_done) with distinct system prompts
- [x] Planning: prep_plan generated alongside persona, shown before interview
- [x] Parallelization: `asyncio.gather` for persona + question bank + prep plan after JD parse
- [x] Reflection: 2-step scorecard — draft → calibration reviewer refines
- [x] Problem mode: POST /api/sessions/from-problem (LeetCode URL → scrape → interview)
- [x] DB migration: idempotent ALTER TABLE for difficulty, prep_plan, problem_url columns
- [x] 50 backend tests passing

## Milestone 6 — Research & Web Tools ✅
**Agentic patterns:** Tool Use · Parallelization (Ch 3, 5)

- [x] Web research service — search Reddit/Glassdoor for company interview experiences
- [x] LLM uses web_search tool autonomously (Tool Use pattern)
- [x] Parallel web research: multiple sources scraped concurrently
- [x] OA platform detection (HackerRank, CodeSignal, etc.)
- [x] Previously scraped problems cache (Problem model + GET /api/problems)
- [x] Frontend: prep plan display + "From Problem" tab

## Milestone 7 — Multi-Agent ✅
**Agentic patterns:** Multi-Agent · Inter-Agent Communication (Ch 7, 15)

- [x] Agent base class + Pydantic schemas for inter-agent contracts
- [x] ParseAgent, PersonaAgent, ScorerAgent, MemoryAgent
- [x] Orchestrator pipeline replacing JDService.process_jd()
- [x] Cross-session memory — UserMemory model, weakness tracking
- [x] Frontend: Profile page learning insights + score trends

## Milestone 8 — Code Execution
**Agentic patterns:** Tool Use (Ch 5) — interviewer reacts to real code output

- [ ] Sandbox service — async subprocess with timeout, output capture
- [ ] POST /api/code/run + POST /api/code/test routes
- [ ] LLM-generated test cases + starter code for problem sessions
- [ ] Monaco editor in Session page (problem mode)
- [ ] Terminal panel: run output + test results (pass/fail per case)
- [ ] Interviewer code awareness — AI sees code + results, gives feedback

## Milestone 9 — Talking Head + Voice
**Agentic patterns:** Human-in-the-Loop (Ch 13) — voice-based interaction

- [ ] TTS service (edge-tts) — text → audio for AI responses
- [ ] Browser STT (Web Speech API) — voice input, no backend needed
- [ ] Animated avatar (CSS 2D for MVP, TalkingHead.js stretch goal)
- [ ] Full voice loop: speak → transcribe → LLM → TTS → avatar speaks
- [ ] Voice settings: toggle, voice selection

## Milestone 10 — Polish
- [ ] Export session as PDF / markdown
- [ ] Mobile-responsive layout
- [ ] Performance optimisation (lazy loading, caching)
