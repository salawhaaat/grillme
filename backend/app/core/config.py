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

    database_url: str = "sqlite+aiosqlite:///./app/data/grillme.db"


settings = Settings()
