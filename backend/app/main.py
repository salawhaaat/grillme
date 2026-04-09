from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.database import init_db
from app.routes.problems import router as problems_router
from app.routes.chat import router as chat_router
from app.routes.sessions import router as sessions_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()   # создаёт таблицы при старте
    yield


app = FastAPI(title="grillme", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(problems_router)
app.include_router(chat_router)
app.include_router(sessions_router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
