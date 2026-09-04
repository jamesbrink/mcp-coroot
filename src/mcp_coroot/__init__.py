"""MCP server for the Coroot observability platform."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("mcp-coroot")
except PackageNotFoundError:  # pragma: no cover - only when running from source
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
