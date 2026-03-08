"""Tests for admin service routes."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from shared.database import get_db


@pytest_asyncio.fixture
async def client(db_override):
    from admin.app.main import app

    app.dependency_overrides[get_db] = db_override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


def admin_headers(user_id="admin-1"):
    return {"X-User-ID": user_id, "X-User-Role": "admin"}


def user_headers(user_id="user-1"):
    return {"X-User-ID": user_id, "X-User-Role": "user"}


class TestAdminAccess:
    async def test_non_admin_blocked(self, client):
        response = await client.get("/dashboard/stats", headers=user_headers())
        assert response.status_code == 403

    async def test_no_auth_blocked(self, client):
        response = await client.get("/dashboard/stats")
        assert response.status_code == 401

    async def test_admin_allowed(self, client):
        response = await client.get("/dashboard/stats", headers=admin_headers())
        assert response.status_code == 200


class TestDashboard:
    async def test_stats(self, client):
        response = await client.get("/dashboard/stats", headers=admin_headers())
        assert response.status_code == 200
        data = response.json()
        assert "pending_moderation" in data
        assert "total_admin_actions" in data


class TestModeration:
    async def test_submit_and_list_report(self, client):
        # Submit a report
        response = await client.post("/report", json={
            "item_type": "review",
            "item_id": "review-bad",
            "reason": "Inappropriate content",
        }, headers=admin_headers())
        assert response.status_code == 201
        item_id = response.json()["id"]

        # List pending items
        response = await client.get("/moderation", headers=admin_headers())
        assert response.status_code == 200
        items = response.json()
        assert len(items) == 1
        assert items[0]["item_id"] == "review-bad"

    async def test_resolve_moderation_item(self, client):
        # Create item
        resp = await client.post("/report", json={
            "item_type": "listing",
            "item_id": "listing-spam",
            "reason": "Spam listing",
        }, headers=admin_headers())
        item_id = resp.json()["id"]

        # Resolve it
        response = await client.post(f"/moderation/{item_id}/resolve", json={
            "action": "remove",
            "reason": "Confirmed spam",
        }, headers=admin_headers())
        assert response.status_code == 200
        assert response.json()["action"] == "remove"


class TestUserActions:
    async def test_suspend_user(self, client):
        response = await client.post("/users/bad-user/action", json={
            "action": "suspend",
            "reason": "Violation of terms of service",
        }, headers=admin_headers())
        assert response.status_code == 200
        assert response.json()["action"] == "suspend"

    async def test_non_admin_cannot_act(self, client):
        response = await client.post("/users/bad-user/action", json={
            "action": "suspend",
            "reason": "Try to suspend",
        }, headers=user_headers())
        assert response.status_code == 403


class TestAuditLog:
    async def test_audit_log_records_actions(self, client):
        # Perform an action
        await client.post("/users/test-user/action", json={
            "action": "warn",
            "reason": "First warning",
        }, headers=admin_headers())

        # Check audit log
        response = await client.get("/audit-log", headers=admin_headers())
        assert response.status_code == 200
        entries = response.json()
        assert len(entries) >= 1
        assert entries[0]["action"] == "user.warn"
        assert entries[0]["target_id"] == "test-user"
