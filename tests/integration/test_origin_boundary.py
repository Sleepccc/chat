"""Origin boundary acceptance tests supplied by Codex for M01."""

import pytest
from fastapi.testclient import TestClient

from pocket_guardian.api.app import create_app
from pocket_guardian.config import Setting

TEST_TOKEN = "test-only-origin-" + "x" * 32


def configured_app(port=8000):
    return create_app(Setting(host="127.0.0.1", port=port, token=TEST_TOKEN, _env_file=None))


@pytest.mark.parametrize("path", ["/health", "/identity"])
@pytest.mark.parametrize("origin", [None, "http://127.0.0.1:8000"])
def test_expected_or_absent_origin_allows_normal_request(path, origin):
    headers = {"Authorization": "Bearer " + TEST_TOKEN}
    if origin is not None:
        headers["Origin"] = origin
    with TestClient(configured_app(), base_url="http://127.0.0.1:8000") as client:
        response = client.get(path, headers=headers)
    assert response.status_code == 200


@pytest.mark.parametrize("path", ["/health", "/identity"])
@pytest.mark.parametrize("origin", [
    "https://untrusted.example",
    "http://127.0.0.1:9000",
    "https://127.0.0.1:8000",
    "http://127.0.0.1:8000.untrusted.example",
    "http://127.0.0.1:8000/not-an-origin",
    "null",
    "",
])
def test_explicit_untrusted_origin_is_rejected_even_with_valid_token(path, origin):
    with TestClient(configured_app(), base_url="http://127.0.0.1:8000") as client:
        response = client.get(path, headers={"Origin": origin, "Authorization": "Bearer " + TEST_TOKEN})
    assert response.status_code == 403
    assert TEST_TOKEN not in response.text


@pytest.mark.parametrize("origin", [None, "http://127.0.0.1:8000"])
def test_origin_allowance_does_not_replace_token_authentication(origin):
    headers = {} if origin is None else {"Origin": origin}
    with TestClient(configured_app(), base_url="http://127.0.0.1:8000") as client:
        response = client.get("/identity", headers=headers)
    assert response.status_code == 401


@pytest.mark.parametrize("port,origin", [(9000, "http://127.0.0.1:9000"), (80, "http://127.0.0.1")])
def test_expected_origin_follows_configured_port_and_http_default_port(port, origin):
    with TestClient(configured_app(port), base_url=origin) as client:
        response = client.get("/health", headers={"Origin": origin})
    assert response.status_code == 200
