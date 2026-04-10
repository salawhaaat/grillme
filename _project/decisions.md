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
