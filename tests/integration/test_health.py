"""Health endpoint acceptance test supplied by Codex for M01."""

import pytest

from fastapi.testclient import TestClient

from pocket_guardian.api.app import create_app
from pocket_guardian.config import Setting


def test_health_is_anonymous_and_returns_only_non_sensitive_status():
    settings = Setting(
        host="127.0.0.1", port=8000,
        token="test-only-health-" + "x" * 32, _env_file=None,
    )
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8000") as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}



@pytest.mark.parametrize("method,path,expected_status", [
    ("GET", "/not-a-route", 404),
    ("POST", "/health", 405),
])
def test_unknown_route_and_unsupported_method(method, path, expected_status):
    settings = Setting(
        host="127.0.0.1", port=8000,
        token="test-only-health-" + "x" * 32, _env_file=None,
    )
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8000") as client:
        response = client.request(method, path)
    assert response.status_code == expected_status
    assert settings.token.get_secret_value() not in response.text
