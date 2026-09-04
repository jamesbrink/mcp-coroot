"""Command line entry point.

Two transports are supported: ``stdio`` (the default, used by desktop MCP
clients that launch the server as a subprocess) and ``http`` (MCP Streamable
HTTP, for running the server as a shared network service).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from dataclasses import replace

from . import __version__
from .config import ConfigError, Settings
from .server import build_server

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mcp-coroot",
        description=(
            "MCP server for the Coroot observability platform. Configure it with "
            "COROOT_BASE_URL and either COROOT_USERNAME/COROOT_PASSWORD or "
            "COROOT_SESSION_COOKIE."
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"mcp-coroot {__version__}"
    )
    parser.add_argument(
        "--transport",
        choices=("stdio", "http"),
        default="stdio",
        help="stdio for a client-launched subprocess, http for Streamable HTTP",
    )
    parser.add_argument(
        "--host", default="127.0.0.1", help="bind address for --transport http"
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="port for --transport http"
    )
    parser.add_argument("--path", default="/mcp", help="URL path for --transport http")
    parser.add_argument(
        "--stateless",
        action="store_true",
        help="handle each HTTP request independently, for load-balanced deployments",
    )
    parser.add_argument(
        "--json-response",
        action="store_true",
        help="reply to HTTP requests with plain JSON instead of an event stream",
    )
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="hide every tool that modifies Coroot (same as COROOT_READ_ONLY=true)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        help="logging verbosity; logs always go to stderr",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="print the effective configuration and exit without serving",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the server. Returns a process exit code."""
    args = build_parser().parse_args(argv)

    # stdout carries the MCP protocol on stdio, so logs must go to stderr.
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format=LOG_FORMAT,
        stream=sys.stderr,
    )

    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        print(f"mcp-coroot: {exc}", file=sys.stderr)
        return 2

    if args.read_only and not settings.read_only:
        settings = replace(settings, read_only=True)

    if args.check:
        print(json.dumps({"version": __version__, **settings.redacted()}, indent=2))
        return 0

    if settings.auth_mode == "none":
        logging.getLogger("mcp_coroot").warning(
            "No Coroot credentials configured; set COROOT_USERNAME and "
            "COROOT_PASSWORD, or COROOT_SESSION_COOKIE. Requests will fail "
            "unless Coroot runs with anonymous access."
        )

    server = build_server(settings)
    if args.transport == "http":
        server.run(
            transport="streamable-http",
            host=args.host,
            port=args.port,
            streamable_http_path=args.path,
            stateless_http=args.stateless,
            json_response=args.json_response,
        )
    else:
        server.run(transport="stdio")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
