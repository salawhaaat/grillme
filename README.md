# grillme

Local AI mock interviewer — FastAPI + SvelteKit + TalkingHead avatar

## Free LLM Providers

No paid API required. Pick any provider below and drop the key in `backend/.env`.

### Recommended for grillme

| Provider | Best for | Speed | Notes |
|---|---|---|---|
| [Google AI Studio](https://aistudio.google.com/) | Default — generous free tier | Fast | `gemini-2.0-flash` recommended |
| [Groq](https://console.groq.com/) | Streaming — fastest inference available | Fastest | `llama-3.3-70b-versatile` |
| [OpenRouter](https://openrouter.ai/) | Unified API — switch models without code changes | Varies | Many free models available |
| [GitHub Models](https://github.com/marketplace/models) | Free if you have GitHub account | Fast | GPT-4o, Llama, Mistral |

### Full list of free APIs

1. [All Free APIs (community list)](https://github.com/cheahjs/free-llm-api-resources)
2. [NVIDIA NIM](https://build.nvidia.com/)
3. [Ollama Cloud](https://ollama.com/settings)
4. [Groq](https://console.groq.com/)
5. [GitHub Models](https://github.com/marketplace/models)
6. [Google AI Studio](https://aistudio.google.com/)
7. [OpenRouter](https://openrouter.ai/)
8. [Cloudflare Workers AI](https://developers.cloudflare.com/workers-ai/)
9. [Cerebras](https://cloud.cerebras.ai/)
10. [Mistral / Codestral](https://codestral.mistral.ai/)
11. [Taalas](https://taalas.com/api-request-form/)

## Setup

```bash
# 1. Copy env and fill in your key
cp .env.example .env

# 2. Set provider and model in .env
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.0-flash
GEMINI_API_KEY=your_key_here

# 3. Run backend
cd backend && uv run uvicorn app.main:app --reload
```

## Data

SQLite database is stored locally — never committed to git.

```
backend/app/data/grillme.db
```

Delete it to reset all sessions and recreate the schema on next server start.

## API Docs

With the server running:

- `http://localhost:8000/docs` — Swagger UI (interactive)
- `http://localhost:8000/redoc` — ReDoc (readable)
- `http://localhost:8000/openapi.json` — import into Postman or Insomnia
