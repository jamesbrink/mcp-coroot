"""Tools for connectivity, accounts, projects and API keys."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

from ...client import CorootError
from ...config import Settings
from ..app import DESTRUCTIVE, READ_ONLY, WRITE
from ..errors import guard
from ..state import AppState, ToolContext
from ._common import ProjectIdParam, context, ok, respond, target


def register(mcp: MCPServer[AppState], settings: Settings) -> None:
    @mcp.tool(title="Check the Coroot connection", annotations=READ_ONLY)
    @guard
    async def get_connection(ctx: ToolContext) -> dict[str, Any]:
        """Check that Coroot is reachable and see who this server is.

        Start here when other tools fail: it separates a connectivity problem
        from a credentials one, and reports the role, which decides what will be
        allowed. Reachability is probed without authenticating, so it answers
        even when the credentials are wrong.
        """
        state = context(ctx)
        healthy = await state.coroot.system.health()
        payload: dict[str, Any] = {
            "healthy": healthy,
            "base_url": state.settings.base_url,
            "auth_mode": state.settings.auth_mode,
            "read_only": state.settings.read_only,
            "toolsets": sorted(state.settings.toolsets),
        }
        if healthy:
            try:
                user = await state.coroot.auth.current_user()
            except CorootError as exc:
                payload["authenticated"] = False
                payload["auth_error"] = str(exc)
            else:
                payload["authenticated"] = True
                payload["user"] = {
                    "email": user.get("email"),
                    "name": user.get("name"),
                    "role": user.get("role"),
                    "anonymous": bool(user.get("anonymous")),
                }
                payload["projects"] = user.get("projects") or []
        return respond(state, payload)

    @mcp.tool(title="Get projects", annotations=READ_ONLY)
    @guard
    async def get_projects(
        ctx: ToolContext,
        project_id: Annotated[
            str | None,
            Field(
                description=(
                    "Report one project in detail: its settings, whether it is "
                    "collecting telemetry, and its ingestion keys. Omit to list "
                    "the projects this account can see."
                )
            ),
        ] = None,
    ) -> dict[str, Any]:
        """List Coroot projects, or report one in detail.

        A project is a cluster. Call this before anything needing a project_id.
        The detail view is also the way to tell whether a project is receiving
        data at all: a prometheus action of 'configure' means no metrics source
        is set up, and 'wait' means the cache is still filling.
        """
        state = context(ctx)
        if not project_id:
            projects = await state.project_choices(refresh=True)
            return respond(
                state,
                {
                    "projects": projects,
                    "count": len(projects),
                    "default_project": state.settings.default_project,
                },
            )

        pid = await state.resolve_project(project_id)
        project = await state.coroot.projects.get(pid)
        status = await state.coroot.projects.status(pid)
        data = status.data if isinstance(status.data, dict) else {}
        payload: dict[str, Any] = {
            "id": pid,
            **project,
            "telemetry": {
                "status": data.get("status"),
                "error": data.get("error") or None,
                "prometheus": data.get("prometheus"),
                "node_agent": data.get("node_agent"),
                "kube_state_metrics": data.get("kube_state_metrics"),
            },
            "open_incidents": status.context.get("incidents") or {},
            "firing_alerts": status.context.get("alerts") or {},
        }
        if settings.enabled("admin"):
            payload["api_keys"] = await state.coroot.projects.api_keys(pid)
        return respond(state, payload)

    if settings.read_only or not settings.enabled("admin"):
        return

    @mcp.tool(title="Create or rename a project", annotations=WRITE)
    @guard
    async def save_project(
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
        project_id: Annotated[
            str | None,
            Field(description="Rename this project instead of creating one."),
        ] = None,
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
        """Create a Coroot project, or rename an existing one.

        A new project gets a default ingestion key and the built-in alerting
        rules.
        """
        state = context(ctx)
        if project_id:
            await state.coroot.projects.update(
                project_id, name=name, member_projects=member_projects
            )
            await state.project_choices(refresh=True)
            return ok(f"Renamed project to {name!r}", project_id=project_id, name=name)
        new_id = await state.coroot.projects.create(
            name, member_projects=member_projects
        )
        await state.project_choices(refresh=True)
        return ok(f"Created project {name!r}", project_id=new_id, name=name)

    @mcp.tool(title="Delete a project", annotations=DESTRUCTIVE)
    @guard
    async def delete_project(
        ctx: ToolContext,
        project_id: Annotated[
            str, Field(description="Id of the project to delete. Required, no default.")
        ],
    ) -> dict[str, Any]:
        """Delete a project and everything in it.

        Irreversible: incidents, alerts, dashboards, alerting rules and settings
        go with it. The project id must be passed explicitly.
        """
        state = context(ctx)
        await state.coroot.projects.delete(project_id)
        await state.project_choices(refresh=True)
        return ok(f"Deleted project {project_id}", project_id=project_id)

    @mcp.tool(title="Create or delete an ingestion key", annotations=WRITE)
    @guard
    async def manage_api_key(
        ctx: ToolContext,
        action: Annotated[
            Literal["create", "delete"],
            Field(description="Whether to generate a key or revoke one."),
        ],
        description: Annotated[
            str | None,
            Field(
                description=(
                    "What a new key is for, e.g. 'staging node agents'. Required "
                    "when creating."
                )
            ),
        ] = None,
        key: Annotated[
            str | None,
            Field(description="The key value to revoke. Required when deleting."),
        ] = None,
        project_id: ProjectIdParam = None,
    ) -> dict[str, Any]:
        """Generate or revoke a telemetry ingestion key.

        Agents send telemetry with these. Revoking one stops whatever is using
        it from reporting; read the current keys with get_projects.
        """
        state, pid = await target(ctx, project_id)
        if action == "create":
            if not description:
                raise ToolError("description is required when creating a key")
            created = await state.coroot.projects.generate_api_key(pid, description)
            return ok(
                "Created ingestion key",
                project_id=pid,
                key=(created or {}).get("key"),
                description=description,
            )
        if not key:
            raise ToolError("key is required when deleting")
        await state.coroot.projects.delete_api_key(pid, key)
        return ok("Revoked ingestion key", project_id=pid)
