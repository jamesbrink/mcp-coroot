"""Custom dashboards and ad-hoc panel queries."""

from __future__ import annotations

import json
from typing import Any

from .base import BaseAPI, Enveloped, split_envelope
from .errors import CorootNotFoundError
from .ids import encode_segment
from .timerange import TimeInput, time_params


def build_panel(
    queries: list[dict[str, Any]],
    *,
    name: str = "",
    description: str = "",
    display: str = "line",
    stacked: bool = False,
) -> dict[str, Any]:
    """Build a ``DashboardPanel`` for ``/panel/data`` or a dashboard config."""
    return {
        "name": name,
        "description": description,
        "source": {"metrics": {"queries": queries}},
        "widget": {"chart": {"display": display, "stacked": stacked}},
        "box": {"x": 0, "y": 0, "w": 12, "h": 6},
    }


def metrics_query(
    query: str, *, datasource: str = "", legend: str = "", color: str = ""
) -> dict[str, Any]:
    """One PromQL query entry for :func:`build_panel`."""
    return {"datasource": datasource, "query": query, "legend": legend, "color": color}


class DashboardsAPI(BaseAPI):
    async def list(self, project_id: str) -> Enveloped:
        """``data`` = ``[{"id", "name", "description"}]``."""
        payload = await self._t.get(self.project_path(project_id, "dashboards"))
        enveloped = split_envelope(payload)
        if enveloped.data is None:
            enveloped.data = []
        return enveloped

    async def get(self, project_id: str, dashboard_id: str) -> Enveloped:
        """One dashboard including its ``config`` (groups of panels)."""
        payload = await self._t.get(
            self.project_path(project_id, "dashboards", encode_segment(dashboard_id))
        )
        enveloped = split_envelope(payload)
        if not isinstance(enveloped.data, dict):
            raise CorootNotFoundError("Dashboard not found", detail=dashboard_id)
        return enveloped

    async def create(self, project_id: str, *, name: str, description: str = "") -> str:
        """Create an empty dashboard and return its id."""
        return await self._t.request_text(
            "POST",
            self.project_path(project_id, "dashboards"),
            json_body={"action": "create", "name": name, "description": description},
        )

    async def update(
        self,
        project_id: str,
        dashboard_id: str,
        *,
        name: str,
        description: str = "",
    ) -> None:
        """Rename a dashboard / change its description."""
        await self._t.post(
            self.project_path(project_id, "dashboards", encode_segment(dashboard_id)),
            {
                "action": "update",
                "id": dashboard_id,
                "name": name,
                "description": description,
            },
        )

    async def save_config(
        self,
        project_id: str,
        dashboard_id: str,
        *,
        name: str,
        config: dict[str, Any],
        description: str = "",
    ) -> None:
        """Replace the dashboard's panel configuration (``{"groups": [...]}``)."""
        await self._t.post(
            self.project_path(project_id, "dashboards", encode_segment(dashboard_id)),
            {
                "action": "",
                "id": dashboard_id,
                "name": name,
                "description": description,
                "config": config,
            },
        )

    async def delete(
        self, project_id: str, dashboard_id: str, *, name: str | None = None
    ) -> None:
        """Delete a dashboard (Coroot's form validation still requires its name)."""
        if name is None:
            current = await self.get(project_id, dashboard_id)
            name = str(current.data.get("name") or dashboard_id)
        await self._t.post(
            self.project_path(project_id, "dashboards", encode_segment(dashboard_id)),
            {"action": "delete", "id": dashboard_id, "name": name},
        )

    async def panel_data(
        self,
        project_id: str,
        panel: dict[str, Any],
        *,
        from_: TimeInput = None,
        to: TimeInput = None,
    ) -> dict[str, Any]:
        """Evaluate a panel's PromQL queries; returns ``{"chart": Chart | None}``."""
        params: dict[str, Any] = time_params(from_, to)
        params["query"] = json.dumps(panel, separators=(",", ":"))
        data = await self._t.get(
            self.project_path(project_id, "panel", "data"), params=params
        )
        return data if isinstance(data, dict) else {"chart": None}
