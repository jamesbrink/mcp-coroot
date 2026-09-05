"""Tools for user and role administration."""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
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
    Field(description=("Role name from get_users, e.g. 'Admin', 'Editor', 'Viewer'.")),
]


def register(mcp: MCPServer[AppState], settings: Settings) -> None:
    @mcp.tool(title="Get users and roles", annotations=READ_ONLY)
    @guard
    async def get_users(
        ctx: ToolContext,
        include_permissions: Annotated[
            bool,
            Field(
                description=(
                    "Also return what each role may do, and the scopes and "
                    "actions available."
                )
            ),
        ] = False,
    ) -> dict[str, Any]:
        """List Coroot users and the roles they can hold.

        Requires an account with permission to edit users; other roles get a
        permission error even for reading. Use include_permissions to work out
        which role a new user needs.
        """
        state = context(ctx)
        data = await state.coroot.users.list()
        payload: dict[str, Any] = {
            "users": data.get("users") or [],
            "roles": data.get("roles") or [],
        }
        if include_permissions:
            roles = await state.coroot.users.roles()
            payload["role_permissions"] = (
                roles.get("roles") if isinstance(roles, dict) else None
            )
            payload["scopes"] = roles.get("scopes") if isinstance(roles, dict) else None
        return respond(state, payload)

    if settings.read_only:
        return

    @mcp.tool(title="Create or update a user", annotations=WRITE)
    @guard
    async def save_user(
        ctx: ToolContext,
        email: EmailParam,
        name: NameParam,
        role: RoleParam,
        user_id: Annotated[
            int | None,
            Field(description="Update this user instead of creating one."),
        ] = None,
        password: Annotated[
            str | None,
            Field(
                description=(
                    "The password. Required when creating; omit when updating to "
                    "keep the current one."
                )
            ),
        ] = None,
    ) -> dict[str, Any]:
        """Create a Coroot user, or update one.

        Coroot replaces the whole record, so pass the current values for
        anything that should not change; read them with get_users.
        """
        state = context(ctx)
        if user_id is None:
            if not password:
                raise ToolError("password is required when creating a user")
            await state.coroot.users.create(
                email=email, name=name, role=role, password=password
            )
            return ok(f"Created user {email!r}", email=email, role=role)
        await state.coroot.users.update(
            user_id, email=email, name=name, role=role, password=password
        )
        return ok(f"Updated user {user_id}", user_id=user_id, role=role)

    @mcp.tool(title="Delete a user", annotations=DESTRUCTIVE)
    @guard
    async def delete_user(
        ctx: ToolContext,
        user_id: Annotated[int, Field(description="Numeric user id from get_users.")],
    ) -> dict[str, Any]:
        """Delete a Coroot user. The built-in admin cannot be deleted."""
        state = context(ctx)
        await state.coroot.users.delete(user_id)
        return ok(f"Deleted user {user_id}", user_id=user_id)
