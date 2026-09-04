"""Tools for user and role administration."""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from ...config import Settings
from ..app import DESTRUCTIVE, READ_ONLY, WRITE
from ..errors import guard
from ..state import AppState, ToolContext
from ._common import context, ok, respond

EmailParam = Annotated[
    str, Field(description="The user's login (Coroot calls it email).")
]
NameParam = Annotated[str, Field(description="The user's display name.")]
RoleParam = Annotated[
    str,
    Field(description="Role name from list_roles, e.g. 'Admin', 'Editor', 'Viewer'."),
]


def register(mcp: MCPServer[AppState], settings: Settings) -> None:
    @mcp.tool(title="List users", annotations=READ_ONLY)
    @guard
    async def list_users(ctx: ToolContext) -> dict[str, Any]:
        """List Coroot users and the roles available.

        Requires an account with permission to edit users; other roles get a
        permission error even for reading.
        """
        state = context(ctx)
        data = await state.coroot.users.list()
        return respond(state, data)

    @mcp.tool(title="List roles", annotations=READ_ONLY)
    @guard
    async def list_roles(ctx: ToolContext) -> dict[str, Any]:
        """List roles with their permissions, plus the available scopes and actions.

        Useful for working out which role a user needs before create_user.
        """
        state = context(ctx)
        data = await state.coroot.users.roles()
        roles = data.get("roles") if isinstance(data, dict) else None
        return respond(
            state,
            {
                "roles": roles or [],
                "scopes": data.get("scopes") if isinstance(data, dict) else [],
            },
        )

    if settings.read_only:
        return

    @mcp.tool(title="Create a user", annotations=WRITE)
    @guard
    async def create_user(
        ctx: ToolContext,
        email: EmailParam,
        name: NameParam,
        role: RoleParam,
        password: Annotated[
            str, Field(description="Initial password for the account.")
        ],
    ) -> dict[str, Any]:
        """Create a Coroot user."""
        state = context(ctx)
        await state.coroot.users.create(
            email=email, name=name, role=role, password=password
        )
        return ok(f"Created user {email!r}", email=email, role=role)

    @mcp.tool(title="Update a user", annotations=WRITE)
    @guard
    async def update_user(
        ctx: ToolContext,
        user_id: Annotated[int, Field(description="Numeric user id from list_users.")],
        email: EmailParam,
        name: NameParam,
        role: RoleParam,
        password: Annotated[
            str | None,
            Field(description="New password. Omit to keep the current one."),
        ] = None,
    ) -> dict[str, Any]:
        """Update a user's name, login, role or password.

        Every field except password is required: Coroot replaces the whole record,
        so pass the current values for anything that should not change.
        """
        state = context(ctx)
        await state.coroot.users.update(
            user_id, email=email, name=name, role=role, password=password
        )
        return ok(f"Updated user {user_id}", user_id=user_id, role=role)

    @mcp.tool(title="Delete a user", annotations=DESTRUCTIVE)
    @guard
    async def delete_user(
        ctx: ToolContext,
        user_id: Annotated[int, Field(description="Numeric user id from list_users.")],
    ) -> dict[str, Any]:
        """Delete a Coroot user. The built-in admin cannot be deleted."""
        state = context(ctx)
        await state.coroot.users.delete(user_id)
        return ok(f"Deleted user {user_id}", user_id=user_id)

    @mcp.tool(title="Change own password", annotations=WRITE)
    @guard
    async def change_password(
        ctx: ToolContext,
        old_password: Annotated[str, Field(description="The current password.")],
        new_password: Annotated[str, Field(description="The new password.")],
    ) -> dict[str, Any]:
        """Change the password of the account this server authenticates as.

        The configured COROOT_PASSWORD becomes stale afterwards, so update the
        server's environment too.
        """
        state = context(ctx)
        await state.coroot.auth.change_password(old_password, new_password)
        return ok(
            "Password changed. Update COROOT_PASSWORD so the server can log in again."
        )
