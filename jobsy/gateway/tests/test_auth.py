"""Tests for gateway authentication routes."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from shared.auth import create_access_token, create_refresh_token, hash_password
from shared.database import get_db


@pytest_asyncio.fixture
async def client(db_override):
    """Create a test client with database override."""
    # Import here to avoid module-level DB connection
    from gateway.app.main import app
    from gateway.app.models import User

    app.dependency_overrides[get_db] = db_override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def seeded_user(test_session):
    """Seed a test user in the database."""
    from gateway.app.models import User
    from datetime import datetime, timezone

    user = User(
        id="test-user-123",
        phone="+18761234567",
        email="test@jobsy.app",
        password_hash=hash_password("TestPass123!"),
        role="user",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    test_session.add(user)
    await test_session.commit()
    return user


class TestRegister:
    async def test_register_success(self, client):
        response = await client.post("/auth/register", json={
            "phone": "+18769876543",
            "password": "SecurePass1!",
            "role": "user",
        })
        assert response.status_code == 201
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data

    async def test_register_duplicate_phone(self, client, seeded_user):
        response = await client.post("/auth/register", json={
            "phone": "+18761234567",
            "password": "SecurePass1!",
            "role": "user",
        })
        assert response.status_code == 409


class TestLogin:
    async def test_login_success(self, client, seeded_user):
        response = await client.post("/auth/login", json={
            "phone": "+18761234567",
            "password": "TestPass123!",
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data

    async def test_login_wrong_password(self, client, seeded_user):
        response = await client.post("/auth/login", json={
            "phone": "+18761234567",
            "password": "WrongPass!",
        })
        assert response.status_code == 401

    async def test_login_nonexistent_user(self, client):
        response = await client.post("/auth/login", json={
            "phone": "+18760000000",
            "password": "SomePass!",
        })
        assert response.status_code == 401


class TestRefresh:
    async def test_refresh_success(self, client, seeded_user):
        refresh = create_refresh_token(seeded_user.id)
        response = await client.post(f"/auth/refresh?refresh_token={refresh}")
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data

    async def test_refresh_with_access_token_fails(self, client, seeded_user):
        access = create_access_token(seeded_user.id)
        response = await client.post(f"/auth/refresh?refresh_token={access}")
        assert response.status_code == 401


class TestHealthCheck:
    async def test_health(self, client):
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
