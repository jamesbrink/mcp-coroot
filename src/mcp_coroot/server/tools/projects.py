"""Tools for connectivity, accounts, projects and API keys."""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from ...config import Settings
from ..app import CREATE, DESTRUCTIVE, READ_ONLY, WRITE
from ..errors import guard
from ..state import AppState, ToolContext
from ._common import ProjectIdParam, context, ok, respond, target


def register(mcp: MCPServer[AppState], settings: Settings) -> None:
    @mcp.tool(title="Check Coroot connectivity", annotations=READ_ONLY)
    @guard
    async def health_check(ctx: ToolContext) -> dict[str, Any]:
        """Check that the configured Coroot instance is reachable.

        Use this first when other tools fail, to tell a connectivity or
        credentials problem apart from a Coroot-side one.
        """
        state = context(ctx)
        healthy = await state.coroot.system.health()
        return {
            "healthy": healthy,
            "base_url": state.settings.base_url,
            "auth_mode": state.settings.auth_mode,
            "read_only": state.settings.read_only,
        }

    @mcp.tool(title="Show the current user", annotations=READ_ONLY)
    @guard
    async def whoami(ctx: ToolContext) -> dict[str, Any]:
        """Show the authenticated Coroot user, their role and their projects.

        A permission error from another tool usually means this user's role is
        too narrow.
        """
        state = context(ctx)
        user = await state.coroot.auth.current_user()
        return respond(
            state,
            {
                "email": user.get("email"),
                "name": user.get("name"),
                "role": user.get("role"),
                "anonymous": bool(user.get("anonymous")),
                "readonly": bool(user.get("readonly")),
                "projects": user.get("projects") or [],
            },
        )

    @mcp.tool(title="List projects", annotations=READ_ONLY)
    @guard
    async def list_projects(ctx: ToolContext) -> dict[str, Any]:
        """List the Coroot projects (clusters) this account can see.

        Call this before anything that needs a project_id.
        """
        state = context(ctx)
        projects = await state.project_choices(refresh=True)
        return respond(
            state,
            {
                "projects": projects,
                "count": len(projects),
                "default_project": state.settings.default_project,
            },
        )

    @mcp.tool(title="Get project settings", annotations=READ_ONLY)
    @guard
    async def get_project(
        ctx: ToolContext, project_id: ProjectIdParam = None
    ) -> dict[str, Any]:
        """Get a project's settings: name, refresh interval and API keys.

        API key values are hidden unless the account may edit project settings.
        """
        state, pid = await target(ctx, project_id)
        project = await state.coroot.projects.get(pid)
        return respond(state, {"id": pid, **project})

    @mcp.tool(title="Get project health", annotations=READ_ONLY)
    @guard
    async def get_project_status(
        ctx: ToolContext, project_id: ProjectIdParam = None
    ) -> dict[str, Any]:
        """Check whether a project is actually collecting telemetry.

        Reports the metrics source (Prometheus or ClickHouse), the node agent and
        kube-state-metrics. Use it when other tools return empty data: a
        prometheus action of 'configure' means no metrics source is set up, and
        'wait' means the cache is still filling.
        """
        state, pid = await target(ctx, project_id)
        result = await state.coroot.projects.status(pid)
        data = result.data if isinstance(result.data, dict) else {}
        return respond(
            state,
            {
                "project_id": pid,
                "status": data.get("status"),
                "error": data.get("error") or None,
                "prometheus": data.get("prometheus"),
                "node_agent": data.get("node_agent"),
                "kube_state_metrics": data.get("kube_state_metrics"),
                "open_incidents": result.context.get("incidents") or {},
                "firing_alerts": result.context.get("alerts") or {},
            },
        )

    @mcp.tool(title="List project API keys", annotations=READ_ONLY)
    @guard
    async def list_api_keys(
        ctx: ToolContext, project_id: ProjectIdParam = None
    ) -> dict[str, Any]:
        """List a project's telemetry ingestion API keys.

        Key values are only returned to accounts that may edit project settings.
        """
        state, pid = await target(ctx, project_id)
        keys = await state.coroot.projects.api_keys(pid)
        return respond(state, {"project_id": pid, **keys})

    if settings.read_only:
        return

    @mcp.tool(title="Create a project", annotations=WRITE)
    @guard
    async def create_project(
        ctx: ToolContext,
        name: Annotated[
            str,
            Field(
                description=(
                    "Project name: at least 3 characters of lowercase letters, "
                    "digits, '-' or '_'."
                )
            ),
        ],
        member_projects: Annotated[
            list[str] | None,
            Field(
                description=(
                    "Names of existing projects to aggregate into a multicluster "
                    "project. Leave empty for a normal project."
                )
            ),
        ] = None,
    ) -> dict[str, Any]:
        """Create a Coroot project and return its id.

        Coroot generates a default API key and the built-in alerting rules for the
        new project.
        """
        state = context(ctx)
        project_id = await state.coroot.projects.create(
            name, member_projects=member_projects
        )
        await state.project_choices(refresh=True)
        return ok(f"Created project {name!r}", project_id=project_id, name=name)

    @mcp.tool(title="Rename a project", annotations=WRITE)
    @guard
    async def update_project(
        ctx: ToolContext,
        name: Annotated[str, Field(description="New project name (slug format).")],
        project_id: ProjectIdParam = None,
        member_projects: Annotated[
            list[str] | None,
            Field(description="Replacement list of member projects, if multicluster."),
        ] = None,
    ) -> dict[str, Any]:
        """Rename a project or change its member projects."""
        state, pid = await target(ctx, project_id)
        await state.coroot.projects.update(
            pid, name=name, member_projects=member_projects
        )
        await state.project_choices(refresh=True)
        return ok(f"Updated project {pid}", project_id=pid, name=name)

    @mcp.tool(title="Delete a project", annotations=DESTRUCTIVE)
    @guard
    async def delete_project(
        ctx: ToolContext,
        project_id: Annotated[
            str, Field(description="Id of the project to delete. Required, no default.")
        ],
    ) -> dict[str, Any]:
        """Delete a project and everything in it.

        Irreversible: incidents, alerts, dashboards, alerting rules and settings go
        with it. The project id must be passed explicitly.
        """
        state = context(ctx)
        await state.coroot.projects.delete(project_id)
        await state.project_choices(refresh=True)
        return ok(f"Deleted project {project_id}", project_id=project_id)

    @mcp.tool(title="Create an API key", annotations=CREATE)
    @guard
    async def create_api_key(
        ctx: ToolContext,
        description: Annotated[
            str, Field(description="What the key is for, e.g. 'staging node agents'.")
        ],
        project_id: ProjectIdParam = None,
    ) -> dict[str, Any]:
        """Generate a telemetry ingestion API key for a project."""
        state, pid = await target(ctx, project_id)
        created = await state.coroot.projects.generate_api_key(pid, description)
        return ok(
            "Created API key",
            project_id=pid,
            key=(created or {}).get("key"),
            description=description,
        )

    @mcp.tool(title="Delete an API key", annotations=DESTRUCTIVE)
    @guard
    async def delete_api_key(
        ctx: ToolContext,
        key: Annotated[str, Field(description="The API key value from list_api_keys.")],
        project_id: ProjectIdParam = None,
    ) -> dict[str, Any]:
        """Revoke an API key. Agents using it stop being able to send telemetry."""
        state, pid = await target(ctx, project_id)
        await state.coroot.projects.delete_api_key(pid, key)
        return ok("Deleted API key", project_id=pid)
