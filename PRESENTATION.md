# grillme — MVP Presentation

---

## THE VIDEO STRUCTURE

```
0:00–1:00  PITCH      — problem, market gap, what grillme is
1:00–5:00  DEMO       — screen recording of the real app running
```

---

## PART 1 — 1-MINUTE PITCH SCRIPT

> Read this to camera or record voice-over. Tight, punchy, no filler.

---

"The job market right now is brutal.

Entry-level roles get 500 applications. Companies screen with LeetCode.
And to prepare, you're told to pay — Tomodachi, LeetCode Premium, interview coaches —
**fifty dollars a month, just to practice.**

That's wrong.

So we built **grillme** — a fully open-source AI mock interview platform.
You paste a job description. It pulls a **real LeetCode problem** that company actually asks.
Then a talking AI interviewer grills you — in a **voice conversation** — just like the real thing.

No hints. No hand-holding. It asks clarifying questions. It pushes back on vague answers.
At the end, you get a **six-axis scorecard** — not just 'good job', but exactly where you lost points.

It runs **100% locally**. No account. No subscription. No API cost if you use Ollama.
Your code, your voice, your data — stays on your machine.

grillme."

---

## PART 2 — 4-MINUTE DEMO SCRIPT

### Screen 1 — Home page (0:10)
**Show:** Home page with input dropdown

**Say:**
> "You start by pasting a job description — Amazon SDE, Google, whatever you're targeting.
> grillme parses the company, role, and seniority, then picks a problem
> that matches their actual interview history — sourced from real candidate reports on GitHub."

**Action:** Paste a job description. Hit Start.

---

### Screen 2 — Session loading (0:20)
**Show:** Problem generating spinner, interviewer PIP appearing

**Say:**
> "The multi-agent pipeline kicks off in the background —
> a Parser agent, a Problem agent, and a Persona agent all run in sequence.
> Meanwhile, the avatar pre-renders its opening line so there's zero wait."

---

### Screen 3 — Opening / Introduction (0:20)
**Show:** Interviewer speaks opening line via wav2lip, dialogue appears in chat

**Say:**
> "The interviewer introduces themselves and asks you to do the same.
> This is voice-driven — I hold the mic button, speak, release.
> Push-to-talk feeds into a local Whisper STT model — no cloud transcription."

**Action:** Hold mic, say "Hi, I'm [name], I'm a software engineering student…"

---

### Screen 4 — Problem presented (0:30)
**Show:** Problem statement in the left panel (cut version — no examples, no constraints)

**Say:**
> "The interviewer presents the problem — but deliberately cuts the examples and constraints.
> Real interviewers don't hand you everything.
> Asking clarifying questions is part of how you're scored.
> Watch — I'll ask about edge cases."

**Action:** Hold mic, ask "Should I handle negative numbers? What about duplicates?"

**Show:** Interviewer responds, dialogue and avatar sync up.

---

### Screen 5 — Live coding (0:40)
**Show:** Monaco editor, start typing a solution

**Say:**
> "You code in a Monaco editor — same one as VS Code — with Python 3.13.
> You can run code and tests inline. The interviewer watches and reacts —
> if you go silent, it prompts you. If your approach is wrong, it pushes back."

**Action:** Type a partial solution, run it.

---

### Screen 6 — Scorecard (0:30)
**Show:** Six-axis scorecard page

**Say:**
> "After you finish, the scorer agent evaluates you across six axes —
> the same dimensions real interviewers use:
> technical correctness, process of thought, how curious you were,
> how you presented yourself, whether you asked closing questions, and code quality.
> Cross-session weakness tracking means next time, grillme knows what to pressure-test."

---

### Screen 7 — Architecture callout (0:30)
**Show:** `ARCHITECTURE SLIDE` below — or just narrate over the home screen

**Say:**
> "Under the hood: FastAPI backend, React 19 frontend, a five-agent pipeline,
> wav2lip for the talking avatar, faster-whisper for STT, edge-tts for audio.
> LLM is pluggable — Groq, Gemini, OpenAI, or a fully local Ollama model.
> Deployable with one docker compose up.
> Everything you see is open source. Zero dollars to run."

---

## ARCHITECTURE SLIDE

Use this as a visual — paste into Canva / Figma / Google Slides.

```
┌─────────────────────────────────────────────────────────┐
│                        BROWSER                          │
│  Home.tsx ──► Session.tsx ──► Scorecard.tsx             │
│                │                                        │
│    PTT mic ─►  STT (Whisper) ─► LLM ─► TTS ─► Avatar   │
│    Monaco editor   │            │        │       │       │
│    Dialogue panel  │            │     edge-tts  wav2lip  │
└───────────────────────────────────────────────────────── ┘
          │ fetch /api/*
┌─────────────────────────────────────────────────────────┐
│                    FASTAPI BACKEND                       │
│                                                         │
│  POST /sessions/create                                  │
│    └─► ParseAgent ──► ProblemAgent ──► PersonaAgent     │
│                           │                             │
│                    GitHub question bank                  │
│                    (real company questions)              │
│                                                         │
│  POST /converse/respond                                  │
│    └─► LLMService (Groq│Gemini│OpenAI│Ollama)           │
│    └─► AvatarService.start_response_job()               │
│                           │                             │
│  POST /api/stt  ◄── faster-whisper base.en (local)      │
│  POST /api/voice/speak-text ◄── edge-tts (local)        │
│                                                         │
│  POST /sessions/{id}/finish                             │
│    └─► ScorerAgent (6 axes) ──► MemoryAgent             │
└──────────────────────────────────┬──────────────────────┘
                                   │ HTTP
┌──────────────────────────────────▼──────────────────────┐
│              AVATAR SERVICE (Docker sidecar)             │
│  POST /generate                                         │
│    text ──► edge-tts ──► wav2lip-onnx ──► MP4           │
│    ~30–60s on CPU, ~3s on GPU                           │
└─────────────────────────────────────────────────────────┘
```

---

## KEY DESIGN DECISIONS (for Q&A)

| Decision | What we did | Why |
|----------|-------------|-----|
| **Problem source** | Real GitHub-scraped question banks, frequency-weighted | LLM "guesses" are unreliable and stale |
| **LLM abstraction** | `BaseProvider` → `OpenAICompatProvider` / `GeminiProvider` + factory | Swap providers via env var, zero code change |
| **Voice pipeline** | PTT → faster-whisper (local) → LLM → edge-tts → wav2lip | Fully offline capable, no third-party audio APIs |
| **Scoring** | 6 axes, not a single score | Matches how real interviewers evaluate; actionable feedback |
| **Problem presentation** | Cut version only — no examples or constraints shown | Forces clarifying questions; tests `curiosity` axis |
| **No prep plan** | Session jumps straight to the problem | The product is a mock *interview*, not a study guide |
| **Agent separation** | ParseAgent, ProblemAgent, PersonaAgent, ScorerAgent, MemoryAgent | Each independently testable; Orchestrator wires them |
| **Memory** | Canonical weakness tags across sessions | Reduces noise; stable cross-session recommendations |

---

## COMPETITIVE LANDSCAPE SLIDE

| | **grillme** | Beyz.ai | Tomodachi Prep | Prachub |
|--|-------------|---------|---------------|---------|
| Price | **Free / self-host** | Paid | Paid | Free DB only |
| Voice interview | **Yes** | No | Yes | No |
| Talking avatar | **Yes (wav2lip)** | No | No | No |
| Real company Qs | **Yes (scraped)** | No | Unknown | Yes |
| Local inference | **Yes (Ollama)** | No | No | No |
| Scorecard | **6-axis** | Hints only | Basic | None |
| Open source | **Yes** | No | No | No |
| What it is | Practice | Cheat overlay | Practice | Database |

---

## CLOSING LINE OPTIONS

Pick one for the end of your video:

> *"Prep like it's free. Because it should be."*

> *"The interview is rigged. grillme levels the field."*

> *"Stop paying to practice. grillme is open source. Fork it tonight."*

---

## RECORDING TIPS

- **Record screen + voice separately**, sync in DaVinci Resolve / CapCut
- **Show the avatar speaking** — it's the most visually striking part, linger on it
- **Show the scorecard** — the six axes look impressive and concrete
- **Use a real JD** — Amazon/Google makes it feel authentic
- **Keep the terminal/logs hidden** — looks cleaner for non-technical audience
- **Add subtitles** — auto-generate in CapCut, fix errors manually
