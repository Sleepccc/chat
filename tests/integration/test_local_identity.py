"""HTTP identity boundary acceptance tests supplied by Codex for M01."""

import pytest
from fastapi.testclient import TestClient

from pocket_guardian.api.app import create_app
from pocket_guardian.config import Setting

# Public test fixtures, never use as real service credentials.
TEST_TOKEN = "test-only-identity-" + "x" * 32
OTHER_TOKEN = "test-only-other-" + "y" * 32


def configured_app(token=TEST_TOKEN):
    return create_app(Setting(host="127.0.0.1", port=8000, token=token, _env_file=None))


@pytest.mark.parametrize("authorization", [None, "", "Bearer", "Basic test-only", "Bearer " + OTHER_TOKEN])
def test_identity_rejects_missing_invalid_or_wrong_scheme_credentials(authorization):
    headers = {} if authorization is None else {"Authorization": authorization}
    with TestClient(configured_app(), base_url="http://127.0.0.1:8000") as client:
        response = client.get("/identity", headers=headers)
    assert response.status_code == 401
    assert response.headers.get("www-authenticate") == "Bearer"
    assert TEST_TOKEN not in response.text
    assert OTHER_TOKEN not in response.text


def test_identity_returns_server_assigned_actor_for_valid_credentials():
    with TestClient(configured_app(), base_url="http://127.0.0.1:8000") as client:
        response = client.get("/identity", headers={"Authorization": "Bearer " + TEST_TOKEN})
    assert response.status_code == 200
    assert response.json() == {"actor_id": "local-owner"}


def test_query_token_and_actor_claim_cannot_bypass_authentication():
    with TestClient(configured_app(), base_url="http://127.0.0.1:8000") as client:
        response = client.get("/identity", params={"token": TEST_TOKEN, "actor_id": "local-owner"})
    assert response.status_code == 401
    assert TEST_TOKEN not in response.text


def test_http_authentication_uses_the_current_app_configuration():
    with TestClient(configured_app(), base_url="http://127.0.0.1:8000") as first:
        with TestClient(configured_app(OTHER_TOKEN), base_url="http://127.0.0.1:8000") as second:
            assert first.get("/identity", headers={"Authorization": "Bearer " + TEST_TOKEN}).status_code == 200
            assert second.get("/identity", headers={"Authorization": "Bearer " + TEST_TOKEN}).status_code == 401
            assert second.get("/identity", headers={"Authorization": "Bearer " + OTHER_TOKEN}).status_code == 200
