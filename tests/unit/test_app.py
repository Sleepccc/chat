"""Application factory checks supplied by Codex for M01."""

from fastapi import FastAPI

from pocket_guardian.api.app import create_app
from pocket_guardian.config import Setting


# Public fixture only; not a credential for an actual service.
def make_settings(port=8000, token="test-only-first-" + "x" * 32):
    return Setting(host="127.0.0.1", port=port, token=token, _env_file=None)


def test_factory_uses_supplied_settings_without_reloading_environment(monkeypatch):
    settings = make_settings()
    monkeypatch.setenv("PG_PORT", "70000")
    monkeypatch.setenv("PG_HOST", "0.0.0.0")
    monkeypatch.setenv("PG_TOKEN", "invalid")
    app = create_app(settings)
    assert isinstance(app, FastAPI)
    assert app.state.settings is settings


def test_each_application_keeps_its_own_settings():
    first_settings = make_settings()
    second_settings = make_settings(port=9000, token="test-only-second-" + "y" * 32)
    first = create_app(first_settings)
    second = create_app(second_settings)
    assert first is not second
    assert first.state.settings is first_settings
    assert second.state.settings is second_settings
    assert first.state.settings.token != second.state.settings.token
