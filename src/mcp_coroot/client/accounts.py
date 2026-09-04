"""Authentication, users, roles and instance-wide settings."""

from __future__ import annotations

from typing import Any

from .base import BaseAPI, JsonValue
from .errors import CorootConnectionError, CorootError


class AuthAPI(BaseAPI):
    """``/api/login``, ``/api/logout`` and ``/api/user``."""

    async def login(self) -> None:
        await self._t.login()

    async def logout(self) -> None:
        await self._t.logout()

    async def current_user(self) -> dict[str, Any]:
        """The authenticated user: email, name, role, readonly flag and projects."""
        data = await self._t.get("/api/user")
        return data if isinstance(data, dict) else {}

    async def change_password(self, old_password: str, new_password: str) -> None:
        await self._t.post(
            "/api/user",
            {"old_password": old_password, "new_password": new_password},
        )


class UsersAPI(BaseAPI):
    """``/api/users`` and ``/api/roles`` (require the ``users:edit`` permission)."""

    async def list(self) -> dict[str, Any]:
        """``{"users": [...], "roles": [...]}``."""
        data = await self._t.get("/api/users")
        return data if isinstance(data, dict) else {"users": [], "roles": []}

    async def create(self, *, email: str, name: str, role: str, password: str) -> None:
        await self._t.post(
            "/api/users",
            {
                "action": "create",
                "email": email,
                "name": name,
                "role": role,
                "password": password,
            },
        )

    async def update(
        self,
        user_id: int,
        *,
        email: str,
        name: str,
        role: str,
        password: str | None = None,
    ) -> None:
        body: dict[str, Any] = {
            "action": "update",
            "id": user_id,
            "email": email,
            "name": name,
            "role": role,
            "password": password or "",
        }
        await self._t.post("/api/users", body)

    async def delete(self, user_id: int) -> None:
        await self._t.post("/api/users", {"action": "delete", "id": user_id})

    async def roles(self) -> dict[str, Any]:
        """Roles with their permissions plus the action/scope matrix."""
        data = await self._t.get("/api/roles")
        return data if isinstance(data, dict) else {}


class SystemAPI(BaseAPI):
    """Instance-wide endpoints: health, SSO, AI and Coroot Cloud settings."""

    async def health(self) -> bool:
        """``GET /health`` — probed without authenticating.

        Coroot serves this route without auth, so the probe must not log in
        first: otherwise bad credentials look like an unreachable instance.
        Any HTTP answer other than 200 means "not this Coroot", which is an
        answer rather than an error, so status errors are reported as ``False``.
        """
        try:
            response = await self._t.request("GET", "/health", anonymous=True)
        except CorootConnectionError:
            raise
        except CorootError:
            return False
        return response.status_code == 200

    async def sso(self) -> JsonValue:
        return await self._t.get("/api/sso")

    async def update_sso(self, config: dict[str, Any]) -> JsonValue:
        return await self._t.post("/api/sso", config)

    async def ai(self) -> JsonValue:
        return await self._t.get("/api/ai")

    async def update_ai(self, config: dict[str, Any]) -> JsonValue:
        return await self._t.post("/api/ai", config)

    async def cloud_status(self) -> dict[str, Any]:
        """``{"status": "configured" | "unconfigured"}``."""
        data = await self._t.get("/api/cloud", params={"query": "status"})
        return data if isinstance(data, dict) else {}

    async def cloud(self) -> JsonValue:
        """Coroot Cloud form and RCA credit information (needs outbound access)."""
        return await self._t.get("/api/cloud")

    async def update_cloud(
        self, *, api_key: str, incidents_auto_investigation: bool
    ) -> None:
        await self._t.post(
            "/api/cloud",
            {
                "api_key": api_key,
                "incidents_auto_investigation": incidents_auto_investigation,
            },
        )
