"""Root-level pytest fixtures shared across all service tests.

Uses SQLite in-memory for fast unit tests, with async session override.
Services that need Postgres-specific features (PostGIS, JSONB) should
use integration tests with the real database via docker-compose.
"""

import asyncio
import os
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Override env before importing any app code
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["RABBITMQ_URL"] = "amqp://guest:guest@localhost:5672/"
os.environ["JWT_SECRET"] = "test-secret-key"

from shared.database import Base, get_db


@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def test_engine():
    """Create an in-memory SQLite engine for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def test_session(test_engine):
    """Provide a transactional test database session."""
    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def db_override(test_engine):
    """Return a FastAPI dependency override for get_db."""
    session_factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)

    async def _override():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    return _override


@pytest.fixture
def mock_publish_event():
    """Mock the RabbitMQ event publisher for unit tests."""
    with patch("shared.events.publish_event", new_callable=AsyncMock) as mock:
        yield mock


@pytest.fixture
def auth_headers():
    """Generate auth headers with a test JWT token."""
    from shared.auth import create_access_token

    def _make_headers(user_id: str = "test-user-id", role: str = "user"):
        token = create_access_token(user_id, role)
        return {"Authorization": f"Bearer {token}"}

    return _make_headers
