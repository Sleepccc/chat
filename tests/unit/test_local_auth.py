"""Token verification acceptance tests supplied by Codex for M01."""

import pytest

from pocket_guardian.auth.local import verify_token


# Public fixtures only, never credentials for a running service.
@pytest.mark.parametrize("provided,expected,result", [
    (None, "x" * 32, False),
    ("", "x" * 32, False),
    ("", "", False),
    ("x" * 32, "x" * 32, True),
    ("y" * 32, "x" * 32, False),
    ("x" * 31, "x" * 32, False),
    ("x" * 33, "x" * 32, False),
    (" " + "x" * 32, "x" * 32, False),
    ("令" * 32, "令" * 32, True),
    ("错" * 32, "令" * 32, False),
])
def test_token_verification(provided, expected, result):
    assert verify_token(provided, expected) is result
