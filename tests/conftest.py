"""Pytest fixtures for FNID Portal tests."""

import os
import tempfile

import pytest

from fnid_portal import create_app
from fnid_portal.config import TestingConfig


@pytest.fixture()
def app():
    """Create application for testing with a temporary database."""
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    TestingConfig.DB_PATH = db_path
    TestingConfig.UPLOAD_DIR = tempfile.mkdtemp()
    TestingConfig.EXPORT_DIR = tempfile.mkdtemp()

    app = create_app("testing")

    yield app

    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture()
def client(app):
    """A test client for the app."""
    return app.test_client()


@pytest.fixture()
def logged_in_client(client):
    """A test client that is already logged in."""
    client.post("/login", data={
        "badge_number": "TEST001",
        "full_name": "Test Officer",
        "rank": "Inspector of Police",
        "section": "FNID Headquarters - Area 3",
    })
    return client


@pytest.fixture()
def admin_client(client, app):
    """A test client logged in as admin."""
    client.post("/login", data={
        "badge_number": "ADMIN",
        "password": "admin123",
    })
    return client


@pytest.fixture()
def io_client(client):
    """A test client logged in as an IO."""
    client.post("/login", data={
        "badge_number": "IO-TEST",
        "full_name": "IO Test Officer",
        "rank": "Detective Constable",
        "section": "FNID Headquarters - Area 3",
    })
    return client


@pytest.fixture()
def db(app):
    """Get a database connection for direct testing."""
    from fnid_portal.models import get_db
    conn = get_db()
    yield conn
    conn.close()
