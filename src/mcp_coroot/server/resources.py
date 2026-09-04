"""Resources: reference data clients can attach to a conversation.

Tools do the work; these expose the small, stable lookups (what projects exist,
which checks Coroot runs, how ids are shaped) that are useful as context rather
than as an action.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.mcpserver import MCPServer

from ..client.applications import (
    CHECK_IDS,
    INSTRUMENTATION_DEFAULT_PORTS,
    LOG_SEVERITIES,
)
from ..client.configuration import INTEGRATION_TYPES
from ..client.overview import OVERVIEW_VIEWS
from .compact import fit
from .state import AppState, StateHolder

REFERENCE: dict[str, Any] = {
    "application_id_format": {
        "pattern": "cluster_id:namespace:Kind:name",
        "example": "hwvop6p7:default:Deployment:checkout",
        "notes": [
            "namespace is '_' for workloads outside Kubernetes",
            "the name may itself contain colons",
            "pass ids back exactly as Coroot returned them",
        ],
    },
    "time_arguments": {
        "relative": ["now", "now-1h", "now-30m", "now-2d", "now-1w"],
        "durations": ["30m", "1h30m", "2d"],
        "absolute": ["epoch milliseconds", "epoch seconds", "ISO-8601 dates"],
        "default_window": "the last hour",
    },
    "statuses": ["unknown", "ok", "info", "warning", "critical"],
    "log_severities": list(LOG_SEVERITIES),
    "overview_views": list(OVERVIEW_VIEWS),
    "integration_types": list(INTEGRATION_TYPES),
    "instrumentation_ports": INSTRUMENTATION_DEFAULT_PORTS,
    "check_ids": list(CHECK_IDS),
}


def register(mcp: MCPServer[AppState], holder: StateHolder) -> None:
    """Register every resource on ``mcp``."""

    @mcp.resource(
        "coroot://reference",
        name="Coroot reference",
        description=(
            "Identifier formats, time expressions, statuses, check ids and "
            "integration types this server understands."
        ),
        mime_type="application/json",
    )
    def reference() -> str:
        return json.dumps(REFERENCE, indent=2)

    @mcp.resource(
        "coroot://projects",
        name="Coroot projects",
        description="Projects (clusters) the configured account can see.",
        mime_type="application/json",
    )
    async def projects() -> str:
        state = holder.get()
        found = await state.project_choices(refresh=True)
        payload = {
            "base_url": state.settings.base_url,
            "default_project": state.settings.default_project,
            "projects": found,
        }
        return json.dumps(fit(payload, state.settings.max_output_chars), indent=2)

    @mcp.resource(
        "coroot://project/{project_id}/applications",
        name="Applications in a project",
        description=(
            "Application ids and health for one project, for attaching as "
            "context rather than calling a tool."
        ),
        mime_type="application/json",
    )
    async def applications(project_id: str) -> str:
        state = holder.get()
        result = await state.coroot.overview.applications(project_id)
        apps = [
            {
                "id": app.get("id"),
                "status": app.get("status"),
                "category": app.get("category"),
            }
            for app in (result.data or [])
            if isinstance(app, dict)
        ]
        payload = {"project_id": project_id, "count": len(apps), "applications": apps}
        return json.dumps(fit(payload, state.settings.max_output_chars), indent=2)
