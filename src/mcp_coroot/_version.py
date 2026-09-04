"""Package version, resolved once.

This lives apart from ``__init__`` so modules deep in the package can read it
without importing the package root, which re-exports the client and would form a
cycle.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("mcp-coroot")
except PackageNotFoundError:  # pragma: no cover - only when running from source
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
