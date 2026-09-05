"""MCP server for Coroot."""

from .app import CREATE, DESTRUCTIVE, READ_ONLY, WRITE, build_server

__all__ = ["CREATE", "DESTRUCTIVE", "READ_ONLY", "WRITE", "build_server"]
