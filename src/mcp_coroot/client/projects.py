"""Projects, project status and project API keys."""

from __future__ import annotations

from typing import Any

from .base import BaseAPI, Enveloped, split_envelope
from .errors import CorootNotFoundError

#: Aliases used inside classes that define a ``list`` method (which would
#: otherwise shadow the builtin in annotations).
JsonDicts = list[dict[str, Any]]
StrList = list[str]


class ProjectsAPI(BaseAPI):
    async def list(self) -> JsonDicts:
        """Projects visible to the current user as ``[{"id", "name"}]``."""
        user = await self._t.get("/api/user")
        projects = user.get("projects") if isinstance(user, dict) else None
        return [p for p in projects or [] if isinstance(p, dict)]

    async def get(self, project_id: str) -> dict[str, Any]:
        """Project settings (name, api keys, refresh interval, member projects).

        Coroot answers an unknown id with an empty 200 body; that is turned into
        :class:`CorootNotFoundError` here.
        """
        path = self.project_path(project_id)
        data = await self._t.get(path)
        if not isinstance(data, dict):
            raise CorootNotFoundError("Project not found", detail=project_id, path=path)
        return data

    async def create(self, name: str, *, member_projects: StrList | None = None) -> str:
        """Create a project and return its id."""
        body: dict[str, Any] = {"name": name, "member_projects": member_projects or []}
        return await self._t.request_text("POST", "/api/project/", json_body=body)

    async def update(
        self,
        project_id: str,
        *,
        name: str,
        member_projects: StrList | None = None,
    ) -> str:
        body: dict[str, Any] = {"name": name, "member_projects": member_projects or []}
        return await self._t.request_text(
            "POST", self.project_path(project_id), json_body=body
        )

    async def delete(self, project_id: str) -> None:
        await self._t.delete(self.project_path(project_id))

    async def status(self, project_id: str) -> Enveloped:
        """Metrics-source, node-agent and kube-state-metrics health."""
        payload = await self._t.get(self.project_path(project_id, "status"))
        return split_envelope(payload)

    # -- API keys -------------------------------------------------------------

    async def api_keys(self, project_id: str) -> dict[str, Any]:
        """``{"editable": bool, "keys": [{"key", "description"}]}``.

        Coroot serialises an unset key list as ``null`` (multicluster and
        config-file projects never get a default key), so ``keys`` is normalised
        to a list here.
        """
        data = await self._t.get(self.project_path(project_id, "api_keys"))
        if not isinstance(data, dict):
            return {"editable": False, "keys": []}
        keys = data.get("keys")
        data["keys"] = [k for k in keys if isinstance(k, dict)] if keys else []
        return data

    async def generate_api_key(
        self, project_id: str, description: str
    ) -> dict[str, Any] | None:
        """Generate a key and return the new entry (Coroot does not echo it)."""
        before = {k.get("key") for k in (await self.api_keys(project_id))["keys"]}
        await self._t.post(
            self.project_path(project_id, "api_keys"),
            {"action": "generate", "description": description},
        )
        after = await self.api_keys(project_id)
        for entry in after.get("keys", []):
            if isinstance(entry, dict) and entry.get("key") not in before:
                return entry
        return None

    async def delete_api_key(self, project_id: str, key: str) -> None:
        await self._t.post(
            self.project_path(project_id, "api_keys"),
            {"action": "delete", "key": key},
        )

    async def edit_api_key(self, project_id: str, key: str, description: str) -> None:
        await self._t.post(
            self.project_path(project_id, "api_keys"),
            {"action": "edit", "key": key, "description": description},
        )
