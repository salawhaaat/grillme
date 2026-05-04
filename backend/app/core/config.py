from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve to project root (.env sits next to backend/)
_env_path = Path(__file__).parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_env_path)

    llm_provider: str = "openai"
    llm_model: str = "gpt-4o-mini"

    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    groq_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    ollama_api_key: str = ""
    ollama_cloud_base_url: str = "https://ollama.com/v1"
    avatar_provider: str = "wav2lip"
    avatar_service_url: str = "http://localhost:8080"
    videos_dir: str = "/tmp/grillme_videos"

    database_url: str = "sqlite+aiosqlite:///./app/data/grillme.db"


settings = Settings()

# ── Runtime overrides (set via POST /api/config, beat .env) ──────────────────
_runtime: dict[str, str] = {}


def set_runtime_config(provider: str, api_key: str) -> None:
    _runtime["provider"] = provider
    _runtime["api_key"] = api_key


def get_runtime_provider() -> str:
    return _runtime.get("provider", "")


def get_runtime_api_key() -> str:
    return _runtime.get("api_key", "")
