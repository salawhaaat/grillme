# Architecture Decisions

## ADR-001 — SQLite over PostgreSQL
**Decision:** SQLite for local dev  
**Why:** No setup, single file, enough for a local tool  
**Trade-off:** Can't scale to multi-user — swap to PostgreSQL later if needed

## ADR-002 — SQLAlchemy async
**Decision:** `create_async_engine` + `aiosqlite`  
**Why:** FastAPI is async — blocking DB calls would defeat the purpose  

## ADR-003 — LLM provider abstraction
**Decision:** `LLMService` class in `services/llm.py` with swappable backends  
**Why:** Support OpenAI / Groq / Gemini without changing routes  

## ADR-004 — pydantic-settings for config
**Decision:** `Settings(BaseSettings)` reads from `.env` automatically  
**Why:** Type-safe config, no manual `os.getenv()` scattered around

## ADR-005 — JD-first over LeetCode-first
**Decision:** Primary entry point is a pasted Job Description, not a LeetCode URL  
**Why:** People prepare for specific companies and roles, not random problems.
JD → tailored mock interview is the real pain point.  
**Trade-off:** LeetCode mode still planned (Milestone 5), but deprioritised

## ADR-006 — Agentic patterns (from Agentic Design Patterns, Gulli)
**Decision:** Build grillme as a progressively agentic system across milestones  
**Why:** Demonstrates real engineering depth on CV; patterns solve real product problems

### Agent level progression

```
Level 0 — Core Reasoning (done)
  POST /api/chat/stream — pure LLM, no memory, no tools

Level 1 — Connected Problem-Solver (Milestone 3)
  Pattern: Prompt Chaining
    JD text → [LLM: extract company/role/skills]
            → [LLM: build interviewer persona]
            → [LLM: generate prep plan]
    Each output feeds the next input.

  Pattern: Tool Use
    LLM decides when to call web_search("Stripe SWE interview reddit")
    Not hardcoded — agent chooses the tool.

  Pattern: Memory (within session)
    Messages saved to DB — agent remembers full conversation history

Level 2 — Strategic Problem-Solver (Milestone 4-5)
  Pattern: Routing
    Amazon JD → LP-heavy persona
    Google JD  → algorithm-heavy persona
    Startup JD → system design + culture fit persona

  Pattern: Planning
    Agent generates structured prep plan before interview starts
    User sees it, can adjust focus areas (Human-in-the-Loop)

  Pattern: Reflection
    After each answer, LLM critiques its own feedback before sending
    → higher quality scoring

Level 3 — Multi-Agent (Milestone 6)
  JD Parser Agent → Research Agent → Interviewer Agent → Scorer Agent
  Specialised agents, structured outputs passed between them
```

### The 5-step agentic loop mapped to one grillme session
```
1. Get the Mission    → user pastes JD
2. Scan the Scene     → Prompt Chaining: parse JD + optional web research
3. Think It Through   → Planning: generate ranked prep plan
4. Take Action        → Routing: pick persona → run interview chat
5. Learn & Get Better → Reflection: score answers → scorecard
                         Memory: persist weak areas for next session
```

### Patterns used per milestone (CV framing)
| Milestone | Patterns | Book chapters |
|---|---|---|
| 3 — JD Session | Prompt Chaining, Tool Use, Memory | Ch 1, 5, 8 |
| 4 — Frontend | Human-in-the-Loop | Ch 13 |
| 5 — Scoring | Reflection, Planning, Parallelization, Routing | Ch 2, 3, 4, 6 |
| 6 — Research | Tool Use (autonomous), Parallelization (web) | Ch 3, 5 |
| 7 — Multi-Agent | Multi-Agent, Inter-Agent Comms | Ch 7, 15 |

## ADR-007 — Idempotent SQLite migrations without Alembic
**Decision:** Runtime `PRAGMA table_info` checks + `ALTER TABLE ADD COLUMN` in `_run_migrations()`  
**Why:** Single-dev project, SQLite only — Alembic adds complexity we don't need yet  
**Trade-off:** No down-migrations, no migration history. Swap to Alembic if team grows or PostgreSQL added

## ADR-008 — Difficulty as system prompt modifier, not separate personas
**Decision:** Three difficulty tiers (rare/medium/well_done) inject a paragraph into the system prompt  
**Why:** Simpler than maintaining 3× persona variants. One persona, three behavioral overlays  
**Trade-off:** Less fine-grained control than full persona per difficulty

## ADR-009 — React 19 + Vite over SvelteKit
**Decision:** Switched from planned SvelteKit to React 19 + Vite + shadcn/ui  
**Why:** Broader ecosystem, shadcn/ui component library, better hiring signal on CV  
**Trade-off:** More boilerplate than Svelte, but offset by shadcn/ui primitives

## ADR-010 — Agent-per-concern over monolithic service
**Decision:** Split JDService into ParseAgent, PersonaAgent, ScorerAgent, MemoryAgent + Orchestrator
**Why:** Each agent has a single responsibility, typed I/O via Pydantic, and can be tested/replaced independently. The Orchestrator composes them.
**Trade-off:** More files and indirection than a single service class. Worth it for testability and the multi-agent pattern demonstration.

## ADR-011 — Canonical memory taxonomy with deterministic fallback
**Decision:** Store only canonical weakness tags (communication, problem solving, system design, time complexity, coding speed, debugging, leadership), normalize LLM tags into that taxonomy, and fall back to keyword-based extraction from scorecard text when LLM output is invalid/noisy.
**Why:** Cross-session memory quality is more important than tag expressiveness. Canonical tags reduce drift/noise and produce stable profile recommendations.
**Trade-off:** Less nuanced labels and some loss of specificity compared to free-form tags.

## ADR-012 — Problem-first flow over prep-plan flow
**Decision:** Every grillme user flow terminates at a coding problem statement that the user can start solving immediately. No prep plan is shown as a pre-interview blocker.
**Why:** The product is a mock *interview*, not a *study guide*. A prep plan is friction — the user wants to code, ask clarifying questions, and get grilled. Feedback on what to study belongs in the post-interview scorecard, not before the session.
**Trade-off:** Users lose the "here's what to review first" affordance. Scorecard's `areas_to_improve` + cross-session memory fill that role after the fact.

## ADR-013 — ProblemAgent: paraphrase + cut real LeetCode problems
**Decision:** For JD mode, ProblemAgent picks a real LeetCode problem matching the company's interview style, scrapes it, paraphrases it in the interviewer's voice, and **cuts** the examples / constraints / edge cases. The user only sees the core task; the interviewer has full knowledge and reveals details on request.
**Why:** Real recruiters never hand out the full problem with examples. Candidates must ask clarifying questions to surface bounds, duplicates, edge cases, return format. This drives the `curiosity` scoring axis and matches how real interviews run.
**Trade-off:** LLM has to pick a good problem per company (could be off-style). Alternative — generate original problems — was rejected because real LeetCode problems feel more authentic to candidates.

## ADR-014 — Six-axis scorecard
**Decision:** ScorerAgent evaluates candidates on six axes: `technical_correctness`, `process_of_thought`, `curiosity`, `self_presentation`, `closing_questions`, `code_quality`. Each axis scores 0-10 with a one-line comment. Overall score is a weighted average. Recommendation (hire / no_hire / strong_hire) stays.
**Why:** A single overall score hides important soft-skill dimensions. Real interviewers evaluate on multiple axes. User feedback explicitly called out: process of thought, curiosity in the team/problem, closing questions, and how the candidate talks about themselves as things the scorer must grade.
**Trade-off:** Larger scoring prompts (more tokens), more complex UI to render. Worth it for actionable, realistic feedback.

## ADR-015 — Clarification is scored, not prompted
**Decision:** The interviewer never says "Any questions before you start?" — it presents the cut problem and waits. If the candidate begins coding without asking clarifying questions, their `curiosity` axis is penalized by ScorerAgent.
**Why:** Real interviewers don't hand-hold. Candidates who ask good clarifying questions up front are the strong ones. Explicit prompting would destroy the signal.
**Trade-off:** New users may not realize they're supposed to ask and will get low `curiosity` scores. The scorecard feedback explains why, which teaches the behavior over repeated sessions.

## ADR-016 — Unified input dropdown (JD / URL / Text)
**Decision:** Home page has one dropdown with three sources: `jd` (paste job description), `url` (paste LeetCode URL), `text` (paste raw problem text). All three feed the same ProblemAgent pipeline and land on the same Session UI.
**Why:** One mental model. Removes the "which tab am I on" confusion from the current JD/Problem tab toggle. Single backend code path via `POST /api/sessions/create`.
**Trade-off:** Dropdowns are slightly more click-heavy than tabs. Mitigated by smart default (JD) and keyboard shortcut.

## ADR-017 — Unified Session UI (coding-first for all modes)
**Decision:** Session page always shows Monaco editor + terminal + chat side by side, regardless of input source. The `mode` field (`jd` / `problem`) becomes informational only — layout no longer branches on it.
**Why:** Every session is a coding interview now (ADR-012, ADR-013). Splitting the UI by mode was confusing — JD mode had chat but no editor, problem mode had editor but no chat prominence. One layout, one experience.
**Trade-off:** JD sessions that were previously chat-only now expose an editor the user may not fill in. Acceptable — the interviewer drives the candidate toward code via the generated problem.

## ADR-018 — Kill the floating AI interviewer PIP
**Decision:** Remove the draggable "AI Interviewer" picture-in-picture from the Home page. The real avatar lives inside the Session page layout and will be implemented properly in M11 (Talking Head).
**Why:** The floating PIP was decorative and confusing — it became "part of the frame" when transitioning to Session, breaking the mental model. Better to have no fake avatar than a fake one that looks broken in two places.
**Trade-off:** Home page loses a piece of visual flair. Replaced by a cleaner problem preview card.

## ADR-019 — Curated question bank as primary problem source, LLM guess as fallback
**Decision:** For JD mode, ProblemAgent picks problems from a curated `QuestionBank` built by scraping GitHub repos (swolecoder/Amazon-Online-Assessment-Questions-LeetCode, KushalVijay/AmazonCrackedResource, raleighlittles/Amazon-SDE-Interview-Assessments for Amazon; similar repos can be added per company). Selection is weighted by cross-source frequency (problems listed by more repos rank higher) and optionally biased by the user's cross-session weaknesses (ADR-011). LLM-guessed slug (existing M8 behavior) is a fallback only when the company is not in the bank.
**Why:** LLM training data is stale and its "what company X asks" is unreliable. GitHub repos curated by candidates who actually interviewed are ground truth. Multi-source frequency filters noise — a problem listed by 3 repos is more likely to actually be asked than one listed by 1. This also mirrors the existing M6 pattern (Reddit/Glassdoor scraping via ResearchService) — just another data source in the ingestion layer.
**Trade-off:** Seed data goes stale without manual refresh. Mitigated by `python -m app.cli.refresh_questions` CLI for scheduled/manual rebuilds. Biased toward companies with active GitHub coverage (Amazon > small startups). Startups and niche companies still fall through to LLM guess.

## ADR-020 — Local inference via Ollama as a first-class LLM provider
**Decision:** Add Ollama as a supported backend in `LLMService` alongside OpenAI / Groq / Gemini. Users can run grillme end-to-end with zero API cost by setting `LLM_PROVIDER=ollama` and `LLM_MODEL=llama3.1` (or any local model, e.g. `qwen2.5-coder:7b`).
**Why:** Token efficiency matters — interview practice sessions rack up real API costs fast (10+ sessions/week × 50k+ tokens each). Ollama gives free, private, offline inference with acceptable quality for mock interviews. It also proves the provider-abstraction pattern from ADR-003 actually pays off (swap backends via env var, routes don't change). CV framing: "production-ready multi-provider LLM architecture with local-first fallback" reads well to hiring managers.
**Trade-off:** Local models (llama3.1 8B, qwen2.5-coder 7B) are meaningfully worse than GPT-4o / Claude Opus for nuanced paraphrasing, 6-axis scoring calibration, and persona building. Acceptable degradation for practice runs; users who want a "final" polished session still use cloud providers. Ollama also requires the user to have Ollama installed + a model pulled (one-time setup cost).

## ADR-021 — Docker-first deployment with docker-compose for local dev
**Decision:** Ship grillme as multi-stage Docker images — backend on `python:3.13-slim`, frontend as a Node build step that produces static files served by nginx. A `docker-compose.yml` at the repo root composes backend + frontend + an optional Ollama sidecar for single-command local dev.
**Why:** Deployment target is portable — runs unchanged on Fly.io, Railway, Render, self-hosted VPS, or a developer laptop. Multi-stage builds keep production images small (backend ~150MB, frontend ~50MB). Compose eliminates "works on my machine" friction and gives new contributors a one-command startup. A production-ready container setup is a strong CV signal for a personal project.
**Trade-off:** Docker adds a build step, image registry considerations, and layer caching concerns. Worth it for portability and the production-ready positioning.
