from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, AsyncConnection, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings


engine = create_async_engine(settings.database_url, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with SessionLocal() as session:
        yield session


async def _run_migrations(conn: AsyncConnection) -> None:
    """Idempotent schema migrations for columns added after initial deploy."""
    result = await conn.execute(text("PRAGMA table_info(interview_sessions)"))
    columns = {row[1] for row in result.fetchall()}

    if "difficulty" not in columns:
        await conn.execute(text(
            "ALTER TABLE interview_sessions "
            "ADD COLUMN difficulty VARCHAR(20) NOT NULL DEFAULT 'medium'"
        ))
        await conn.execute(text(
            "UPDATE interview_sessions SET difficulty = 'medium' WHERE difficulty IS NULL"
        ))

    if "prep_plan" not in columns:
        await conn.execute(text(
            "ALTER TABLE interview_sessions ADD COLUMN prep_plan TEXT"
        ))

    if "problem_url" not in columns:
        await conn.execute(text(
            "ALTER TABLE interview_sessions ADD COLUMN problem_url TEXT"
        ))

    if "oa_platform" not in columns:
        await conn.execute(text(
            "ALTER TABLE interview_sessions ADD COLUMN oa_platform VARCHAR(100)"
        ))

    if "cv_text" not in columns:
        await conn.execute(text(
            "ALTER TABLE interview_sessions ADD COLUMN cv_text TEXT"
        ))

    if "prompt_tokens" not in columns:
        await conn.execute(text(
            "ALTER TABLE interview_sessions ADD COLUMN prompt_tokens INTEGER NOT NULL DEFAULT 0"
        ))

    if "completion_tokens" not in columns:
        await conn.execute(text(
            "ALTER TABLE interview_sessions ADD COLUMN completion_tokens INTEGER NOT NULL DEFAULT 0"
        ))

    if "total_tokens" not in columns:
        await conn.execute(text(
            "ALTER TABLE interview_sessions ADD COLUMN total_tokens INTEGER NOT NULL DEFAULT 0"
        ))


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _run_migrations(conn)
