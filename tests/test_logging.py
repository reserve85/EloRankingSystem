"""Tests for structured request logging and request correlation (Fix L11)."""

import logging


def test_request_logging_sets_request_id_header(client, db_session, caplog):
    """Every non-/health request carries a correlation id in logs + response header."""
    with caplog.at_level(logging.INFO, logger="app.request"):
        resp = client.get("/ui/login")
    assert resp.status_code == 200
    request_id = resp.headers.get("x-request-id")
    assert request_id
    assert "method=GET path=/ui/login status=200" in caplog.text
    assert request_id in caplog.text


def test_health_requests_are_not_logged(client, db_session, caplog):
    """Orchestrator health probes are skipped to keep logs clean."""
    with caplog.at_level(logging.INFO, logger="app.request"):
        resp = client.get("/health")
    assert resp.status_code == 200
    assert "app.request" not in caplog.text


def test_client_supplied_request_id_is_respected(client, db_session, caplog):
    """An inbound X-Request-ID is reused instead of generating a new one."""
    with caplog.at_level(logging.INFO, logger="app.request"):
        resp = client.get("/ui/login", headers={"X-Request-ID": "trace-123"})
    assert resp.status_code == 200
    assert resp.headers.get("x-request-id") == "trace-123"
    assert "trace-123" in caplog.text
