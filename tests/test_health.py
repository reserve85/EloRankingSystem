"""Tests for health check endpoint."""



def test_health_endpoint(client):
    """Test that health endpoint returns 200 with correct structure."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data


def test_health_endpoint_reports_db_failure(client, monkeypatch, caplog):
    """A failed database check must return 503 unhealthy (Fix L2).

    The raw exception is logged server side but never echoed to the caller,
    so unauthenticated health probes cannot leak database internals (Fix L1).
    """
    import logging
    import app.api.routes.health as health

    class _BrokenEngine:
        def connect(self):
            raise RuntimeError("database is down")

    monkeypatch.setattr(health, "engine", _BrokenEngine())
    with caplog.at_level(logging.ERROR, logger="app.api.routes.health"):
        response = client.get("/health")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["detail"] == "database unavailable"
    # The exception detail is surfaced in the server log, not the response.
    assert "database is down" in caplog.text


def test_root_redirects_to_login(client):
    """Test that root URL redirects to login page."""
    response = client.get("/", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert "/ui/login" in response.headers.get("location", "")


def test_openapi_docs(client):
    """Test that OpenAPI docs are accessible."""
    response = client.get("/docs")
    assert response.status_code == 200


def test_redoc(client):
    """Test that ReDoc is accessible."""
    response = client.get("/redoc")
    assert response.status_code == 200
