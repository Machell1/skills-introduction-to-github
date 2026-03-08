"""Tests for payments service routes."""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from httpx import ASGITransport, AsyncClient

from shared.database import get_db


@pytest_asyncio.fixture
async def client(db_override, mock_publish_event):
    from payments.app.main import app

    app.dependency_overrides[get_db] = db_override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


class TestAccountSetup:
    async def test_setup_customer_account(self, client):
        with patch("payments.app.routes.create_customer", new_callable=AsyncMock, return_value="cus_test123"):
            response = await client.post("/accounts/setup", json={
                "email": "customer@test.com",
                "name": "Test User",
                "account_type": "customer",
            }, headers={"X-User-ID": "user-cust"})

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == "user-cust"

    async def test_setup_provider_account(self, client):
        with patch("payments.app.routes.create_connect_account", new_callable=AsyncMock, return_value={
            "account_id": "acct_test456",
            "onboarding_url": "https://connect.stripe.com/setup/test",
        }):
            response = await client.post("/accounts/setup", json={
                "email": "provider@test.com",
                "account_type": "provider",
            }, headers={"X-User-ID": "user-prov"})

        assert response.status_code == 200
        data = response.json()
        assert "onboarding_url" in data

    async def test_missing_auth(self, client):
        response = await client.post("/accounts/setup", json={
            "email": "test@test.com",
            "account_type": "customer",
        })
        assert response.status_code == 401


class TestPayment:
    async def test_initiate_payment(self, client):
        with patch("payments.app.routes.create_payment_intent", new_callable=AsyncMock, return_value={
            "payment_intent_id": "pi_test789",
            "client_secret": "pi_test789_secret",
            "amount": 5000,
            "platform_fee": 500,
        }):
            response = await client.post("/pay", json={
                "payee_id": "provider-1",
                "listing_id": "listing-1",
                "amount": 5000,
                "description": "Plumbing repair",
            }, headers={"X-User-ID": "customer-1"})

        assert response.status_code == 201
        data = response.json()
        assert data["amount"] == 5000.0
        assert data["platform_fee"] == 500.0
        assert data["net_amount"] == 4500.0
        assert data["status"] == "pending"

    async def test_cannot_pay_self(self, client):
        response = await client.post("/pay", json={
            "payee_id": "user-self",
            "amount": 1000,
        }, headers={"X-User-ID": "user-self"})
        assert response.status_code == 400

    async def test_invalid_amount(self, client):
        response = await client.post("/pay", json={
            "payee_id": "provider-1",
            "amount": -100,
        }, headers={"X-User-ID": "customer-1"})
        assert response.status_code == 422


class TestTransactions:
    async def test_list_empty_transactions(self, client):
        response = await client.get("/transactions", headers={"X-User-ID": "user-no-txns"})
        assert response.status_code == 200
        assert response.json() == []

    async def test_list_transactions_after_payment(self, client):
        with patch("payments.app.routes.create_payment_intent", new_callable=AsyncMock, return_value={
            "payment_intent_id": "pi_list",
            "client_secret": "secret",
            "amount": 2000,
            "platform_fee": 200,
        }):
            await client.post("/pay", json={
                "payee_id": "provider-list",
                "amount": 2000,
            }, headers={"X-User-ID": "customer-list"})

        response = await client.get("/transactions", headers={"X-User-ID": "customer-list"})
        assert response.status_code == 200
        txns = response.json()
        assert len(txns) == 1
        assert txns[0]["amount"] == 2000.0
