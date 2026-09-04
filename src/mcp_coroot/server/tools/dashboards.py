"""Tools for custom dashboards and ad-hoc panels."""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from ...client.dashboards import build_panel, metrics_query
from ...config import Settings
from ..app import DESTRUCTIVE, READ_ONLY, WRITE
from ..compact import compact_dict
from ..errors import guard
from ..state import AppState, ToolContext
from ._common import FromParam, ProjectIdParam, ToParam, ok, respond, target

DashboardIdParam = Annotated[
    str, Field(description="Dashboard id from list_dashboards.")
]


def register(mcp: MCPServer[AppState], settings: Settings) -> None:
    @mcp.tool(title="List dashboards", annotations=READ_ONLY)
    @guard
    async def list_dashboards(
        ctx: ToolContext, project_id: ProjectIdParam = None
    ) -> dict[str, Any]:
        """List the project's custom dashboards."""
        state, pid = await target(ctx, project_id)
        result = await state.coroot.dashboards.list(pid)
        dashboards = [d for d in (result.data or []) if isinstance(d, dict)]
        return respond(
            state,
            {"project_id": pid, "count": len(dashboards), "dashboards": dashboards},
        )

    @mcp.tool(title="Get a dashboard", annotations=READ_ONLY)
    @guard
    async def get_dashboard(
        ctx: ToolContext,
        dashboard_id: DashboardIdParam,
        project_id: ProjectIdParam = None,
    ) -> dict[str, Any]:
        """Get a dashboard with its panel groups and PromQL queries."""
        state, pid = await target(ctx, project_id)
        result = await state.coroot.dashboards.get(pid, dashboard_id)
        data = result.data if isinstance(result.data, dict) else {}
        return respond(state, {"project_id": pid, **data})

    @mcp.tool(title="Query a dashboard panel", annotations=READ_ONLY)
    @guard
    async def get_panel_data(
        ctx: ToolContext,
        queries: Annotated[
            list[str],
            Field(
                description="PromQL expressions to evaluate as one panel.",
                min_length=1,
            ),
        ],
        project_id: ProjectIdParam = None,
        legend: Annotated[
            str | None,
            Field(
                description=(
                    "Legend template for the series, e.g. '{{instance}}'. Applies "
                    "to every query."
                )
            ),
        ] = None,
        datasource: Annotated[
            str | None,
            Field(
                description=(
                    "Member project name to query, required for multicluster projects."
                )
            ),
        ] = None,
        from_time: FromParam = None,
        to_time: ToParam = None,
    ) -> dict[str, Any]:
        """Evaluate one or more PromQL queries as a chart, the way a panel would.

        For a single expression get_metrics is simpler; use this to compare
        several series in one window.
        """
        state, pid = await target(ctx, project_id)
        panel = build_panel(
            [
                metrics_query(q, legend=legend or "", datasource=datasource or "")
                for q in queries
            ],
            name="ad-hoc",
        )
        data = await state.coroot.dashboards.panel_data(
            pid, panel, from_=from_time, to=to_time
        )
        chart = compact_dict({"chart": data.get("chart")}).get("chart")
        return respond(
            state,
            {
                "project_id": pid,
                "queries": queries,
                "chart": chart,
                "message": None
                if chart
                else "The queries matched no series in this window.",
            },
        )

    if settings.read_only:
        return

    @mcp.tool(title="Create a dashboard", annotations=WRITE)
    @guard
    async def create_dashboard(
        ctx: ToolContext,
        name: Annotated[str, Field(description="Dashboard name.")],
        project_id: ProjectIdParam = None,
        description: Annotated[
            str, Field(description="What the dashboard shows.")
        ] = "",
    ) -> dict[str, Any]:
        """Create an empty dashboard and return its id.

        Add panels afterwards with update_dashboard_panels.
        """
        state, pid = await target(ctx, project_id)
        dashboard_id = await state.coroot.dashboards.create(
            pid, name=name, description=description
        )
        return ok(
            f"Created dashboard {name!r}", project_id=pid, dashboard_id=dashboard_id
        )

    @mcp.tool(title="Rename a dashboard", annotations=WRITE)
    @guard
    async def update_dashboard(
        ctx: ToolContext,
        dashboard_id: DashboardIdParam,
        name: Annotated[str, Field(description="New dashboard name.")],
        project_id: ProjectIdParam = None,
        description: Annotated[str, Field(description="New description.")] = "",
    ) -> dict[str, Any]:
        """Rename a dashboard or change its description. Panels are untouched."""
        state, pid = await target(ctx, project_id)
        await state.coroot.dashboards.update(
            pid, dashboard_id, name=name, description=description
        )
        return ok(f"Updated dashboard {dashboard_id}", project_id=pid, name=name)

    @mcp.tool(title="Replace a dashboard's panels", annotations=WRITE)
    @guard
    async def update_dashboard_panels(
        ctx: ToolContext,
        dashboard_id: DashboardIdParam,
        config: Annotated[
            dict[str, Any],
            Field(
                description=(
                    "The complete panel configuration: "
                    '{"groups": [{"name": "Group", "panels": [{"name": "CPU", '
                    '"source": {"metrics": {"queries": [{"query": "up", '
                    '"legend": "{{instance}}"}]}}, "widget": {"chart": '
                    '{"display": "line"}}, "box": {"x": 0, "y": 0, "w": 12, '
                    '"h": 6}}]}]}. Fetch the current one with get_dashboard.'
                )
            ),
        ],
        project_id: ProjectIdParam = None,
    ) -> dict[str, Any]:
        """Replace a dashboard's panels wholesale.

        This overwrites the existing layout, so read it with get_dashboard and
        send the modified version back.
        """
        state, pid = await target(ctx, project_id)
        current = await state.coroot.dashboards.get(pid, dashboard_id)
        data = current.data if isinstance(current.data, dict) else {}
        await state.coroot.dashboards.save_config(
            pid,
            dashboard_id,
            name=str(data.get("name") or dashboard_id),
            description=str(data.get("description") or ""),
            config=config,
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
