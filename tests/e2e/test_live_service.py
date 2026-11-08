"""Real loopback HTTP/CLI checks supplied and executed by Codex for M01."""

import http.client
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import threading
import time

import pytest

from pocket_guardian.__main__ import build_server
from pocket_guardian.config import Setting

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_TOKEN = "test-only-cli-" + "x" * 32


def cli_environment(**overrides):
    env = {key: value for key, value in os.environ.items() if not key.lower().startswith("pg_")}
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8", PG_TOKEN=TEST_TOKEN)
    for key, value in overrides.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = str(value)
    return env


def run_cli(**overrides):
    return subprocess.run(
        [sys.executable, "-B", "-m", "pocket_guardian"],
        cwd=PROJECT_ROOT, env=cli_environment(**overrides),
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
    )


def request_over_tcp(port, path, headers=None, method="GET"):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        connection.request(method, path, headers=headers or {})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read().decode("utf-8")
    finally:
        connection.close()


@pytest.fixture(scope="module")
def live_service():
    # Release an OS-selected free port before Uvicorn binds it itself. On a race,
    # fail clearly rather than terminating any program that wins the port.
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        port = candidate.getsockname()[1]
    token = secrets.token_urlsafe(32)
    server = build_server(Setting(host="127.0.0.1", port=port, token=token, _env_file=None))
    failures = []

    def run_server():
        try:
            server.run()
        except BaseException as exc:
            failures.append(type(exc).__name__)

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert server.started and not failures, f"Uvicorn did not start: {failures}"
        yield port, token
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        assert not thread.is_alive(), "Uvicorn failed to shut down gracefully"
        assert not failures, f"Uvicorn failed: {failures}"
        with socket.socket() as probe:
            probe.settimeout(0.5)
            assert probe.connect_ex(("127.0.0.1", port)) != 0, "Port remained open after shutdown"


def test_real_health_and_authenticated_identity(live_service):
    port, token = live_service
    status, _, body = request_over_tcp(port, "/health")
    assert status == 200 and json.loads(body) == {"status": "ok"}
    status, _, body = request_over_tcp(port, "/identity", {"Authorization": "Bearer " + token})
    assert status == 200 and json.loads(body) == {"actor_id": "local-owner"}
    assert token not in body


@pytest.mark.parametrize("authorization", [None, "Bearer test-only-wrong-token"])
def test_real_identity_rejects_invalid_credentials(live_service, authorization):
    port, token = live_service
    headers = {} if authorization is None else {"Authorization": authorization}
    status, response_headers, body = request_over_tcp(port, "/identity", headers)
    assert status == 401
    assert {key.lower(): value for key, value in response_headers.items()}["www-authenticate"] == "Bearer"
    assert token not in body


@pytest.mark.parametrize("header,value,status", [
    ("Host", "untrusted.example", 400),
    ("Origin", "https://untrusted.example", 403),
])
def test_real_request_boundaries(live_service, header, value, status):
    port, token = live_service
    actual, _, body = request_over_tcp(port, "/identity", {
        header: value, "Authorization": "Bearer " + token,
    })
    assert actual == status
    assert token not in body


def test_real_trusted_origin(live_service):
    port, token = live_service
    status, _, _ = request_over_tcp(port, "/identity", {
        "Origin": f"http://127.0.0.1:{port}", "Authorization": "Bearer " + token,
    })
    assert status == 200


@pytest.mark.skipif(sys.platform != "win32", reason="Windows socket ownership verification")
def test_windows_listener_is_only_loopback(live_service):
    port, _ = live_service
    output = subprocess.run(["netstat", "-ano", "-p", "tcp"],
        capture_output=True, text=True, errors="replace", check=True, timeout=10).stdout
    matching = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) >= 5 and fields[0] == "TCP" and fields[-1] == str(os.getpid()):
            if fields[1].endswith(f":{port}") and fields[3] == "LISTENING":
                matching.append(fields[1])
    assert matching == [f"127.0.0.1:{port}"]


@pytest.mark.parametrize("overrides,field", [
    ({"PG_PORT": "70000"}, "port"),
    ({"PG_HOST": "0.0.0.0"}, "host"),
    ({"PG_TOKEN": "test-only-short"}, "token"),
    ({"PG_TOKEN": None}, "token"),
])
def test_actual_cli_rejects_invalid_configuration_without_secrets(overrides, field):
    result = run_cli(**overrides)
    assert result.returncode == 2
    assert "Invalid PocketGuardian configuration" in result.stderr
    assert field in result.stderr
    assert TEST_TOKEN not in result.stderr + result.stdout
    assert "test-only-short" not in result.stderr + result.stdout


def test_actual_cli_reports_occupied_port_without_terminating_owner():
    with socket.socket() as occupied:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            occupied.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        occupied.bind(("127.0.0.1", 0))
        occupied.listen(1)
        port = occupied.getsockname()[1]
        result = run_cli(PG_PORT=port)
        # Uvicorn chooses its startup-failure code; the contract is a failed exit.
        assert result.returncode != 0
        assert "bind" in result.stderr.lower()
        assert str(port) in result.stderr
        assert occupied.getsockname() == ("127.0.0.1", port)
        assert occupied.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN) == 1
        assert TEST_TOKEN not in result.stderr + result.stdout
