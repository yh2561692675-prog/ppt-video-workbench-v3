from __future__ import annotations

import argparse

import uvicorn

from workbench.main import create_app


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="workbench")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--host", required=True)
    serve.add_argument("--port", required=True, type=int)
    arguments = parser.parse_args(argv)

    if arguments.command == "serve":
        uvicorn.run(create_app(), host=arguments.host, port=arguments.port)


if __name__ == "__main__":
    main()
