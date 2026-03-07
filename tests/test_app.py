"""Smoke tests for the FNID Portal application."""


def test_login_page_loads(client):
    """Login page should be accessible."""
    response = client.get("/login")
    assert response.status_code == 200
    assert b"FNID" in response.data


def test_home_redirects_when_not_logged_in(client):
    """Home page should redirect to login when not authenticated."""
    response = client.get("/")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_login_creates_session(logged_in_client):
    """Posting valid credentials should create a session and redirect."""
    response = logged_in_client.get("/")
    assert response.status_code == 200
    assert b"Test Officer" in response.data


def test_home_loads_when_logged_in(logged_in_client):
    """Home page should load when logged in."""
    response = logged_in_client.get("/")
    assert response.status_code == 200
    assert b"Intelligence Unit" in response.data


def test_unit_pages_load(logged_in_client):
    """Each unit home page should load successfully."""
    for unit in ["intel", "operations", "seizures", "arrests", "forensics", "registry"]:
        response = logged_in_client.get(f"/unit/{unit}")
        assert response.status_code == 200, f"Unit {unit} failed to load"


def test_unit_dashboards_load(logged_in_client):
    """Each unit dashboard should load successfully."""
    for unit in ["intel", "operations", "seizures", "arrests", "forensics", "registry"]:
        response = logged_in_client.get(f"/unit/{unit}/dashboard")
        assert response.status_code == 200, f"Dashboard {unit} failed to load"


def test_command_dashboard_loads(logged_in_client):
    """Command dashboard should load successfully."""
    response = logged_in_client.get("/command")
    assert response.status_code == 200


def test_api_stats_returns_json(logged_in_client):
    """API stats endpoint should return JSON."""
    response = logged_in_client.get("/api/stats/command")
    assert response.status_code == 200
    data = response.get_json()
    assert "intel" in data
    assert "cases" in data


def test_invalid_unit_redirects(logged_in_client):
    """Accessing an invalid unit should redirect."""
    response = logged_in_client.get("/unit/nonexistent")
    assert response.status_code == 302


def test_logout_clears_session(logged_in_client):
    """Logout should clear the session."""
    response = logged_in_client.get("/logout")
    assert response.status_code == 302
    # After logout, home should redirect to login
    response = logged_in_client.get("/")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_new_record_form_loads(logged_in_client):
    """New record form should load for each unit."""
    response = logged_in_client.get("/unit/intel/new")
    assert response.status_code == 200


def test_import_page_loads(logged_in_client):
    """Import page should load."""
    response = logged_in_client.get("/import")
    assert response.status_code == 200
