"""Tools for custom dashboards and ad-hoc panels."""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from ...config import Settings
from ..app import DESTRUCTIVE, READ_ONLY, WRITE
from ..errors import guard
from ..state import AppState, ToolContext
from ._common import ProjectIdParam, ok, respond, target

DashboardIdParam = Annotated[
    str, Field(description="Dashboard id from get_dashboards.")
]


def register(mcp: MCPServer[AppState], settings: Settings) -> None:
    @mcp.tool(title="Get dashboards", annotations=READ_ONLY)
    @guard
    async def get_dashboards(
        ctx: ToolContext,
        project_id: ProjectIdParam = None,
        dashboard_id: Annotated[
            str | None,
            Field(
                description=(
                    "Return one dashboard with its panel groups and queries. "
                    "Omit to list them."
                )
            ),
        ] = None,
    ) -> dict[str, Any]:
        """List the project's custom dashboards, or open one.

        A single dashboard comes back verbatim, so it can be edited and sent
        straight back to save_dashboard.
        """
        state, pid = await target(ctx, project_id)
        if dashboard_id:
            result = await state.coroot.dashboards.get(pid, dashboard_id)
            data = result.data if isinstance(result.data, dict) else {}
            return respond(state, {"project_id": pid, **data}, summarise=False)
        listed = await state.coroot.dashboards.list(pid)
        dashboards = [d for d in (listed.data or []) if isinstance(d, dict)]
        return respond(
            state,
            {"project_id": pid, "count": len(dashboards), "dashboards": dashboards},
        )

    if settings.read_only:
        return

    @mcp.tool(title="Create or update a dashboard", annotations=WRITE)
    @guard
    async def save_dashboard(
        ctx: ToolContext,
        name: Annotated[str, Field(description="Dashboard name.")],
        project_id: ProjectIdParam = None,
        dashboard_id: Annotated[
            str | None,
            Field(description="Update this dashboard instead of creating one."),
        ] = None,
        description: Annotated[
            str, Field(description="What the dashboard shows.")
        ] = "",
        config: Annotated[
            dict[str, Any] | None,
            Field(
                description=(
                    "Replace the panels wholesale: "
                    '{"groups": [{"name": "Group", "panels": [{"name": "CPU", '
                    '"source": {"metrics": {"queries": [{"query": "up", '
                    '"legend": "{{instance}}"}]}}, "widget": {"chart": '
                    '{"display": "line"}}, "box": {"x": 0, "y": 0, "w": 12, '
                    '"h": 6}}]}]}. Omit to leave the existing panels alone. '
                    "Fetch the current layout with get_dashboards first."
                )
            ),
        ] = None,
    ) -> dict[str, Any]:
        """Create a dashboard, rename one, or replace its panels.

        Passing config overwrites the whole layout, so read it with
        get_dashboards and send the modified version back.
        """
        state, pid = await target(ctx, project_id)
        if not dashboard_id:
            new_id = await state.coroot.dashboards.create(
                pid, name=name, description=description
            )
            if config is not None:
                await state.coroot.dashboards.save_config(
                    pid, new_id, name=name, description=description, config=config
                )
            return ok(
                f"Created dashboard {name!r}", project_id=pid, dashboard_id=new_id
            )

        await state.coroot.dashboards.update(
            pid, dashboard_id, name=name, description=description
        )
        if config is None:
            return ok(f"Updated dashboard {dashboard_id}", project_id=pid, name=name)
        await state.coroot.dashboards.save_config(
            pid, dashboard_id, name=name, description=description, config=config
        )
        groups = config.get("groups") or []
        return ok(
            f"Updated dashboard {dashboard_id}",
            project_id=pid,
            dashboard_id=dashboard_id,
            groups=len(groups) if isinstance(groups, list) else None,
        )

    @mcp.tool(title="Delete a dashboard", annotations=DESTRUCTIVE)
    @guard
    async def delete_dashboard(
        ctx: ToolContext,
        dashboard_id: DashboardIdParam,
        project_id: ProjectIdParam = None,
    ) -> dict[str, Any]:
        """Delete a dashboard and its panels."""
        state, pid = await target(ctx, project_id)
        await state.coroot.dashboards.delete(pid, dashboard_id)
        return ok(
            f"Deleted dashboard {dashboard_id}",
            project_id=pid,
            dashboard_id=dashboard_id,
        )
