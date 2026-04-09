"""
Regression tests for the interview_sessions.difficulty migration.

Covers the code-review checklist:
  - Schema migration adds difficulty to a pre-existing table
  - Existing rows are backfilled to 'medium'
  - Migration is idempotent (safe to run twice)
  - Old DB boots cleanly and session endpoints still work
"""
import pytest
from unittest.mock import patch
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from fastapi.testclient import TestClient

from app.core.database import Base, get_db, _run_migrations
from app.main import app

# Schema as it existed before difficulty was added
_OLD_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS interview_sessions (
    id            INTEGER  PRIMARY KEY AUTOINCREMENT,
    mode          VARCHAR(20)  NOT NULL DEFAULT 'jd',
    jd_raw        TEXT,
    company       VARCHAR(200),
    role          VARCHAR(200),
    level         VARCHAR(50),
    persona       TEXT,
    question_bank TEXT,
    scorecard     TEXT,
    messages      TEXT     NOT NULL DEFAULT '[]',
    created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at   DATETIME
)
"""

_INSERT_OLD_ROW = (
    "INSERT INTO interview_sessions (mode, company, role, level, messages) "
    "VALUES ('jd', 'Acme', 'SWE', 'mid', '[]')"
)


# ── fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
async def old_engine():
    """In-memory engine with pre-difficulty schema and one existing row."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.execute(text(_OLD_SCHEMA_SQL))
        await conn.execute(text(_INSERT_OLD_ROW))
    yield engine
    await engine.dispose()


# ── unit tests for _run_migrations ──────────────────────────────────────────

async def test_migration_adds_difficulty_column(old_engine):
    """difficulty column must be absent before and present after migration."""
    async with old_engine.begin() as conn:
        res = await conn.execute(text("PRAGMA table_info(interview_sessions)"))
        assert "difficulty" not in {r[1] for r in res.fetchall()}

        await _run_migrations(conn)

        res = await conn.execute(text("PRAGMA table_info(interview_sessions)"))
        assert "difficulty" in {r[1] for r in res.fetchall()}


async def test_migration_backfills_existing_rows(old_engine):
    """All pre-existing rows must have difficulty='medium' after migration."""
    async with old_engine.begin() as conn:
        await _run_migrations(conn)
        res = await conn.execute(text("SELECT difficulty FROM interview_sessions"))
        rows = res.fetchall()

    assert len(rows) == 1
    assert rows[0][0] == "medium"


async def test_migration_is_idempotent(old_engine):
    """Running _run_migrations twice must not raise or corrupt data."""
    async with old_engine.begin() as conn:
        await _run_migrations(conn)
    async with old_engine.begin() as conn:
        await _run_migrations(conn)  # second run — no-op

    async with old_engine.connect() as conn:
        res = await conn.execute(text("SELECT difficulty FROM interview_sessions"))
        assert res.fetchone()[0] == "medium"


# ── integration test: old DB + migration + live endpoints ───────────────────

def test_session_endpoints_work_after_migration():
    """
    Startup path: old DB schema → migration → session list/get must return
    correct difficulty values without 500/422 errors.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def init_old_then_migrate():
        async with engine.begin() as conn:
            # Simulate a DB that pre-dates the difficulty column
            await conn.execute(text(_OLD_SCHEMA_SQL))
            await conn.execute(text(_INSERT_OLD_ROW))
            await _run_migrations(conn)
            # create_all picks up any other tables (problems, etc.)
            await conn.run_sync(Base.metadata.create_all)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with patch("app.main.init_db", new=init_old_then_migrate):
            with TestClient(app) as client:
                # List sessions
                resp = client.get("/api/sessions/")
                assert resp.status_code == 200
                sessions = resp.json()
                assert len(sessions) == 1
                assert sessions[0]["difficulty"] == "medium"
                assert sessions[0]["company"] == "Acme"

                # Get single session
                sid = sessions[0]["id"]
                resp2 = client.get(f"/api/sessions/{sid}")
                assert resp2.status_code == 200
                data = resp2.json()
                assert data["difficulty"] == "medium"
                assert data["company"] == "Acme"
    finally:
        app.dependency_overrides.clear()
