"""M01 launch scaffold supplied by Codex; service logic is learner-authored."""

import sys

import uvicorn
from pydantic import ValidationError

from pocket_guardian.api.app import create_app
from pocket_guardian.config import Setting, load_settings


def build_server(settings: Setting) -> uvicorn.Server:
    """Build the server that will listen using the validated local configuration."""
    return uvicorn.Server(uvicorn.Config(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        proxy_headers=False,
        server_header=False,
        access_log=False,
    ))


def main() -> int:
    """Load settings and run until shutdown; invalid configuration exits clearly."""
    try:
        settings = load_settings()
    except ValidationError as exc:
        # Setting.hide_input_in_errors hides input values in this text form.
        # Do not substitute exc.errors(), which can contain raw inputs.
        print(f"Invalid PocketGuardian configuration:\n{exc}", file=sys.stderr)
        return 2
    try:
        build_server(settings).run()
    except KeyboardInterrupt:
        # Uvicorn already performed graceful shutdown before re-raising SIGINT.
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
