"""MCP server for the Coroot observability platform.

The MCP server is the primary entry point (``mcp-coroot`` on the command line),
but :class:`CorootClient` is usable on its own as an async client for Coroot's
API::

    from mcp_coroot import CorootClient, Settings

    async with CorootClient(Settings.from_env()) as coroot:
        projects = await coroot.projects.list()
"""

from ._version import __version__
from .client import (
    ApplicationId,
    CorootAuthenticationError,
    CorootClient,
    CorootConflictError,
    CorootConnectionError,
    CorootError,
    CorootNotFoundError,
    CorootPermissionError,
    CorootServerError,
    CorootUnsupportedError,
    CorootValidationError,
    normalize_app_id,
)
from .config import ConfigError, Settings

__all__ = [
    "ApplicationId",
    "ConfigError",
    "CorootAuthenticationError",
    "CorootClient",
    "CorootConflictError",
    "CorootConnectionError",
    "CorootError",
    "CorootNotFoundError",
    "CorootPermissionError",
    "CorootServerError",
    "CorootUnsupportedError",
    "CorootValidationError",
    "Settings",
    "__version__",
    "normalize_app_id",
]
