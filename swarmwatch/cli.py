"""Command-line entry point: `swarmwatch up`."""

from __future__ import annotations

import argparse

import uvicorn

from swarmwatch import __version__
from swarmwatch.app import create_app


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="swarmwatch",
        description="A flight recorder for AI agent swarms.",
    )
    parser.add_argument("--version", action="version", version=f"swarmwatch {__version__}")
    sub = parser.add_subparsers(dest="command")

    up = sub.add_parser("up", help="Run the swarmwatch server and serve the UI.")
    up.add_argument("--host", default="127.0.0.1")
    up.add_argument("--port", type=int, default=8000)
    up.add_argument(
        "--trace",
        default=None,
        help="Path to a trace .jsonl (defaults to the bundled planner→worker→judge sample).",
    )

    args = parser.parse_args(argv)

    host = getattr(args, "host", "127.0.0.1")
    port = getattr(args, "port", 8000)
    trace = getattr(args, "trace", None)

    app = create_app(trace)
    print(f"swarmwatch {__version__}  →  http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
