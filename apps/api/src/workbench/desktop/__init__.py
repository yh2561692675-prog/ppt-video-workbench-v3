"""Desktop bootstrap, release-slot and launcher helpers.

The package is the public ``workbench.desktop`` module.  Keep the CLI entry
point here because a sibling legacy ``desktop.py`` script is intentionally
retained for existing PyInstaller specifications; Python imports this package
first when both are present.
"""

from __future__ import annotations

import argparse

import uvicorn

from workbench.main import create_app


def main(argv: list[str] | None = None) -> None:
    """Start the loopback HTTP server used by the packaged desktop launcher."""
    parser = argparse.ArgumentParser(prog="workbench")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--host", required=True)
    serve.add_argument("--port", required=True, type=int)
    arguments = parser.parse_args(argv)

    if arguments.command == "serve":
        uvicorn.run(create_app(), host=arguments.host, port=arguments.port)
