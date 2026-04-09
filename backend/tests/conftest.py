import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.database import Base, get_db
from app.main import app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
def client():
    engine = create_async_engine(TEST_DATABASE_URL)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    async def init_test_db():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    app.dependency_overrides[get_db] = override_get_db

    with patch("app.main.init_db", side_effect=init_test_db):
        with TestClient(app) as c:
            yield c

    app.dependency_overrides.clear()


@pytest.fixture
def mock_llm():
    with patch("app.services.llm.LLMService.stream_chat") as mock:
        mock.return_value = AsyncMock(
            return_value=iter(["Hello ", "candidate. ", "Let's begin."])
        )
        yield mock
