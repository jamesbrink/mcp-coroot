"""Server state shared by every tool."""

from __future__ import annotations

from dataclasses import dataclass, field

from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError

from ..client import CorootClient
from ..config import Settings


@dataclass(slots=True)
class AppState:
    """Lifespan state: one pooled client for the whole server."""

    settings: Settings
    coroot: CorootClient
    _projects: list[dict[str, object]] = field(default_factory=list)

    async def project_choices(
        self, *, refresh: bool = False
    ) -> list[dict[str, object]]:
        """Projects visible to the current user (cached for the process lifetime)."""
        if refresh or not self._projects:
            self._projects = list(await self.coroot.projects.list())
        return self._projects

    async def resolve_project(self, project_id: str | None) -> str:
        """Pick the project to act on.

        Explicit argument wins, then ``COROOT_PROJECT``, then the only project the
        user can see. Anything else asks the model to choose.
        """
        if project_id and project_id.strip():
            return project_id.strip()
        if self.settings.default_project:
            return self.settings.default_project
        projects = await self.project_choices()
        if len(projects) == 1:
            return str(projects[0].get("id"))
        if not projects:
            raise ToolError(
                "No Coroot projects are visible to this user. Create one with "
                "create_project, or check the account's permissions."
            )
        listing = ", ".join(f"{p.get('name')} ({p.get('id')})" for p in projects[:20])
        raise ToolError(
            f"project_id is required: this account can see {len(projects)} projects. "
            f"Choose one of: {listing}"
        )


#: The context type injected into tools.
ToolContext = Context[AppState, None]


def state_of(ctx: ToolContext) -> AppState:
    """Extract the lifespan state from a tool's context."""
    return ctx.request_context.lifespan_context
