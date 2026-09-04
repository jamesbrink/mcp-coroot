"""Tool registration.

Each module registers one domain. Mutating tools are skipped entirely when
``COROOT_READ_ONLY`` is set, so they never appear in ``tools/list``.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from ...config import Settings
from ..state import AppState
from . import (
    applications,
    configuration,
    dashboards,
    incidents,
    projects,
    telemetry,
    users,
)


def register_all(mcp: MCPServer[AppState], settings: Settings) -> None:
    """Register every tool on ``mcp``."""
    projects.register(mcp, settings)
    applications.register(mcp, settings)
    telemetry.register(mcp, settings)
    incidents.register(mcp, settings)
    configuration.register(mcp, settings)
    dashboards.register(mcp, settings)
    users.register(mcp, settings)


__all__ = ["register_all"]
