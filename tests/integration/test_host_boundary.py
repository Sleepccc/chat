"""Host request boundary acceptance tests supplied by Codex for M01."""

import pytest
from fastapi.testclient import TestClient

from pocket_guardian.api.app import create_app
from pocket_guardian.config import Setting


@pytest.mark.parametrize("path", ["/health", "/identity"])
@pytest.mark.parametrize("untrusted_host", ["untrusted.example", "127.0.0.1.untrusted.example", "localhost"])
def test_untrusted_host_is_rejected_even_with_valid_token(path, untrusted_host):
    test_token = "test-only-host-" + "x" * 32
    settings = Setting(host="127.0.0.1", port=8000, token=test_token, _env_file=None)
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8000") as client:
        response = client.get(path, headers={
            "Host": untrusted_host,
            "Authorization": "Bearer " + test_token,
        })
    assert response.status_code == 400
    assert test_token not in response.text
