"""M01 configuration acceptance tests supplied by Codex; implementation by the learner."""

import os

import pytest
from pydantic import ValidationError

from pocket_guardian.config import Setting, load_settings

# Public fixture only; never use this as a running service credential.
TEST_TOKEN = "test-only-" + "x" * 32


@pytest.fixture(autouse=True)
def isolate_config_environment(monkeypatch):
    # Change only this test process, so existing configuration variables cannot affect defaults.
    for name in tuple(os.environ):
        if name.lower() in {"port", "host", "token"} or name.lower().startswith("pg_"):
            monkeypatch.delenv(name)


def test_port_defaults_to_8000():
    assert Setting(token=TEST_TOKEN, _env_file=None).port == 8000


@pytest.mark.parametrize("port", [1, 9000, 65535])
def test_accepts_port_boundaries_and_normal_value(port):
    assert Setting(token=TEST_TOKEN, port=port, _env_file=None).port == port


@pytest.mark.parametrize("port", [-1, 0, 65536, 70000, "not-a-number", 8000.5])
def test_rejects_invalid_port(port):
    with pytest.raises(ValidationError) as caught:
        Setting(token=TEST_TOKEN, port=port, _env_file=None)
    assert any(error["loc"] == ("port",) for error in caught.value.errors())



def test_host_defaults_to_ipv4_loopback():
    assert Setting(token=TEST_TOKEN, _env_file=None).host == "127.0.0.1"


def test_accepts_explicit_ipv4_loopback_host():
    assert Setting(token=TEST_TOKEN, host="127.0.0.1", _env_file=None).host == "127.0.0.1"


@pytest.mark.parametrize("host", ["0.0.0.0", "192.0.2.1", "::1", "localhost", "", "not-an-ip"])
def test_rejects_hosts_outside_m01_ipv4_loopback_policy(host):
    with pytest.raises(ValidationError) as caught:
        Setting(token=TEST_TOKEN, host=host, _env_file=None)
    assert any(error["loc"] == ("host",) for error in caught.value.errors())



def test_token_is_required():
    with pytest.raises(ValidationError) as caught:
        Setting(_env_file=None)
    assert any(error["loc"] == ("token",) and error["type"] == "missing" for error in caught.value.errors())


@pytest.mark.parametrize("token", ["", "x" * 31])
def test_rejects_token_below_minimum_length(token):
    with pytest.raises(ValidationError) as caught:
        Setting(token=token, _env_file=None)
    assert any(error["loc"] == ("token",) for error in caught.value.errors())


@pytest.mark.parametrize("token", ["x" * 32, TEST_TOKEN])
def test_accepts_token_at_or_above_minimum_length(token):
    settings = Setting(token=token, _env_file=None)
    assert settings.token.get_secret_value() == token


def test_valid_token_is_not_exposed_in_common_representations():
    settings = Setting(token=TEST_TOKEN, _env_file=None)
    assert TEST_TOKEN not in repr(settings)
    assert TEST_TOKEN not in settings.model_dump_json()


def test_invalid_token_error_does_not_display_input_value():
    public_test_value = "test-only-short-token"
    with pytest.raises(ValidationError) as caught:
        Setting(token=public_test_value, _env_file=None)
    assert public_test_value not in str(caught.value)



def test_load_settings_reads_prefixed_environment(monkeypatch):
    monkeypatch.setenv("PG_PORT", "9000")
    monkeypatch.setenv("PG_HOST", "127.0.0.1")
    monkeypatch.setenv("PG_TOKEN", TEST_TOKEN)
    settings = load_settings()
    assert isinstance(settings, Setting)
    assert settings.port == 9000
    assert settings.host == "127.0.0.1"
    assert settings.token.get_secret_value() == TEST_TOKEN


def test_load_settings_uses_defaults_and_ignores_generic_environment(monkeypatch):
    monkeypatch.setenv("PG_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("PORT", "70000")
    monkeypatch.setenv("HOST", "0.0.0.0")
    settings = load_settings()
    assert settings.port == 8000
    assert settings.host == "127.0.0.1"


def test_load_settings_requires_prefixed_token(monkeypatch):
    monkeypatch.setenv("TOKEN", TEST_TOKEN)
    with pytest.raises(ValidationError) as caught:
        load_settings()
    assert any(error["loc"] == ("token",) and error["type"] == "missing" for error in caught.value.errors())


@pytest.mark.parametrize("name,value,field", [
    ("PG_PORT", "70000", "port"),
    ("PG_HOST", "0.0.0.0", "host"),
    ("PG_TOKEN", "test-only-short-token", "token"),
])
def test_load_settings_rejects_invalid_environment(monkeypatch, name, value, field):
    monkeypatch.setenv("PG_TOKEN", TEST_TOKEN)
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError) as caught:
        load_settings()
    assert any(error["loc"] == (field,) for error in caught.value.errors())
    if field == "token":
        assert value not in str(caught.value)


def test_explicit_constructor_values_override_environment(monkeypatch):
    monkeypatch.setenv("PG_PORT", "9000")
    monkeypatch.setenv("PG_TOKEN", TEST_TOKEN)
    assert Setting(port=8001, _env_file=None).port == 8001


def test_load_settings_reads_current_environment_each_call(monkeypatch):
    monkeypatch.setenv("PG_TOKEN", TEST_TOKEN)
    monkeypatch.setenv("PG_PORT", "9000")
    first = load_settings()
    monkeypatch.setenv("PG_PORT", "9001")
    second = load_settings()
    assert first.port == 9000
    assert second.port == 9001
    assert first is not second
