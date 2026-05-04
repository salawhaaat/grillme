import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.database import init_db
from app.core.logging import setup_logger
from app.routes.problems import router as problems_router
from app.routes.chat import router as chat_router
from app.routes.code import router as code_router
from app.routes.sessions import router as sessions_router
from app.routes.voice import router as voice_router
from app.routes.avatar import router as avatar_router
from app.routes.config import router as config_router
from app.routes.stt import router as stt_router
from app.routes.converse import router as converse_router
from app.services.avatar import avatar_service
from app.services.llm import RateLimitError, ProviderError

logger = setup_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()   # создаёт таблицы при старте
    if avatar_service._is_wav2lip_enabled():
        asyncio.create_task(avatar_service.prerender_smalltalk_clips())
        asyncio.create_task(avatar_service.prerender_thinking_clips())
        asyncio.create_task(avatar_service.prerender_scenario_clips())
    yield


app = FastAPI(title="grillme", version="0.1.0", lifespan=lifespan)


@app.exception_handler(RateLimitError)
async def rate_limit_handler(request: Request, exc: RateLimitError) -> JSONResponse:
    return JSONResponse(status_code=429, content={"detail": str(exc)})


@app.exception_handler(ProviderError)
async def provider_error_handler(request: Request, exc: ProviderError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    msg = str(exc)
    if "api_key" in msg.lower() or "API_KEY" in msg or "Settings" in msg:
        return JSONResponse(
            status_code=422,
            content={"detail": msg},
        )
    return JSONResponse(status_code=422, content={"detail": msg})


@app.exception_handler(Exception)
async def generic_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled error on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Something went wrong — please try again."},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(problems_router)
app.include_router(chat_router)
app.include_router(code_router)
app.include_router(sessions_router)
app.include_router(voice_router)
app.include_router(avatar_router)
app.include_router(config_router)
app.include_router(stt_router)
app.include_router(converse_router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
