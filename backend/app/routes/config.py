from fastapi import APIRouter
from pydantic import BaseModel
from app.core.config import set_runtime_config, get_runtime_provider

router = APIRouter(prefix="/api", tags=["config"])


class ConfigBody(BaseModel):
    provider: str
    api_key: str


@router.post("/config")
async def update_config(body: ConfigBody) -> dict:
    set_runtime_config(body.provider, body.api_key)
    return {"ok": True}


@router.get("/config")
async def get_config() -> dict:
    return {"provider": get_runtime_provider() or "not set"}
