"""Tool registration.

Tools are grouped so a deployment can carry only what it needs: the whole
surface costs real context in every conversation, and most of it configures
Coroot rather than investigating a running system. ``COROOT_TOOLSETS`` selects
the groups; mutating tools are additionally skipped when ``COROOT_READ_ONLY``
is set, so neither ever reaches ``tools/list``.
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
    """Register the tools this configuration exposes."""
    # Always present: without these a client cannot find a project at all.
    projects.register(mcp, settings)

    if settings.enabled("diagnose"):
        applications.register(mcp, settings)
        telemetry.register(mcp, settings)
    if settings.enabled("diagnose") or settings.enabled("alerts"):
        incidents.register(mcp, settings)
    if settings.enabled("config") or settings.enabled("diagnose"):
        configuration.register(mcp, settings)
    if settings.enabled("dashboards"):
        dashboards.register(mcp, settings)
    if settings.enabled("admin"):
        users.register(mcp, settings)


__all__ = ["register_all"]
