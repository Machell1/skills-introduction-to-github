"""Tests for reviews service routes."""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from shared.database import get_db


@pytest_asyncio.fixture
async def client(db_override, mock_publish_event):
    from reviews.app.main import app

    app.dependency_overrides[get_db] = db_override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


class TestCreateReview:
    async def test_create_review_success(self, client):
        response = await client.post("/", json={
            "reviewee_id": "provider-456",
            "rating": 5,
            "title": "Great plumber!",
            "body": "Fixed my sink quickly and professionally.",
            "quality_rating": 5,
            "punctuality_rating": 4,
            "communication_rating": 5,
        }, headers={"X-User-ID": "customer-123"})

        assert response.status_code == 201
        data = response.json()
        assert data["rating"] == 5
        assert "id" in data

    async def test_cannot_review_self(self, client):
        response = await client.post("/", json={
            "reviewee_id": "user-1",
            "rating": 5,
        }, headers={"X-User-ID": "user-1"})
        assert response.status_code == 400

    async def test_rating_out_of_range(self, client):
        response = await client.post("/", json={
            "reviewee_id": "provider-456",
            "rating": 6,
        }, headers={"X-User-ID": "customer-123"})
        assert response.status_code == 422

    async def test_missing_auth_header(self, client):
        response = await client.post("/", json={
            "reviewee_id": "provider-456",
            "rating": 5,
        })
        assert response.status_code == 401


class TestGetReviews:
    async def test_get_empty_reviews(self, client):
        response = await client.get("/user/nonexistent-user")
        assert response.status_code == 200
        assert response.json() == []

    async def test_get_reviews_after_create(self, client):
        # Create a review first
        await client.post("/", json={
            "reviewee_id": "provider-789",
            "rating": 4,
            "title": "Good work",
        }, headers={"X-User-ID": "customer-111"})

        response = await client.get("/user/provider-789")
        assert response.status_code == 200
        reviews = response.json()
        assert len(reviews) == 1
        assert reviews[0]["rating"] == 4


class TestRatingSummary:
    async def test_summary_no_reviews(self, client):
        response = await client.get("/user/no-reviews/summary")
        assert response.status_code == 200
        data = response.json()
        assert data["total_reviews"] == 0

    async def test_summary_with_reviews(self, client):
        # Create two reviews
        for rating in [4, 5]:
            await client.post("/", json={
                "reviewee_id": "provider-sum",
                "rating": rating,
            }, headers={"X-User-ID": f"customer-{rating}"})

        response = await client.get("/user/provider-sum/summary")
        assert response.status_code == 200
        data = response.json()
        assert data["total_reviews"] == 2
        assert data["average_rating"] == 4.5


class TestReviewResponse:
    async def test_respond_to_review(self, client):
        # Create review
        create_resp = await client.post("/", json={
            "reviewee_id": "provider-resp",
            "rating": 3,
            "body": "Okay service",
        }, headers={"X-User-ID": "customer-resp"})
        review_id = create_resp.json()["id"]

        # Respond as the reviewee
        response = await client.post(f"/{review_id}/respond", json={
            "body": "Thank you for the feedback!",
        }, headers={"X-User-ID": "provider-resp"})
        assert response.status_code == 201

    async def test_non_reviewee_cannot_respond(self, client):
        create_resp = await client.post("/", json={
            "reviewee_id": "provider-no",
            "rating": 3,
        }, headers={"X-User-ID": "customer-no"})
        review_id = create_resp.json()["id"]

        response = await client.post(f"/{review_id}/respond", json={
            "body": "Not my review",
        }, headers={"X-User-ID": "random-user"})
        assert response.status_code == 403


class TestFlagReview:
    async def test_flag_review(self, client):
        create_resp = await client.post("/", json={
            "reviewee_id": "provider-flag",
            "rating": 1,
            "body": "Inappropriate content",
        }, headers={"X-User-ID": "customer-flag"})
        review_id = create_resp.json()["id"]

        response = await client.post(f"/{review_id}/flag", headers={"X-User-ID": "someone"})
        assert response.status_code == 200
        assert response.json()["status"] == "flagged"
