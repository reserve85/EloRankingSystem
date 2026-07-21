"""Tests for health check endpoint."""



def test_health_endpoint(client):
    """Test that health endpoint returns 200 with correct structure."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data


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
