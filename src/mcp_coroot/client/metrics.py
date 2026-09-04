"""Metrics: Prometheus-compatible query endpoints.

Two access paths exist:

* the session-authenticated proxy ``/api/project/{id}/prom/api/v1/*`` (``series``,
  ``metadata`` and ``label/{name}/values`` only) and ``/panel/data`` for
  evaluating PromQL expressions;
* the API-key authenticated ``/api/v1/query_range`` (the project is resolved from
  the key).
"""

from __future__ import annotations

import json
from typing import Any

from .base import BaseAPI
from .dashboards import build_panel, metrics_query
from .timerange import TimeInput, resolve_epoch_ms, time_params


class MetricsAPI(BaseAPI):
    def _prom_path(self, project_id: str, *segments: str) -> str:
        return self.project_path(project_id, "prom", "api", "v1", *segments)

    @staticmethod
    def _headers(datasource: str | None) -> dict[str, str] | None:
        return {"X-Datasource": datasource} if datasource else None

    async def series(
        self,
        project_id: str,
        match: list[str],
        *,
        from_: TimeInput = None,
        to: TimeInput = None,
        datasource: str | None = None,
    ) -> dict[str, Any]:
        """``/series`` — label sets matching the selectors (``match[]``)."""
        start = resolve_epoch_ms(from_, default="now-1h") // 1000
        end = resolve_epoch_ms(to, default="now") // 1000
        data = await self._t.request_json(
            "GET",
            self._prom_path(project_id, "series"),
            params={"match[]": match, "start": start, "end": end},
            headers=self._headers(datasource),
        )
        return data if isinstance(data, dict) else {}

    async def metadata(
        self,
        project_id: str,
        *,
        metric: str | None = None,
        datasource: str | None = None,
    ) -> dict[str, Any]:
        data = await self._t.request_json(
            "GET",
            self._prom_path(project_id, "metadata"),
            params={"metric": metric},
            headers=self._headers(datasource),
        )
        return data if isinstance(data, dict) else {}

    async def label_values(
        self,
        project_id: str,
        label: str,
        *,
        match: list[str] | None = None,
        from_: TimeInput = None,
        to: TimeInput = None,
        datasource: str | None = None,
    ) -> dict[str, Any]:
        """``/label/{name}/values`` (``__name__`` lists metric names)."""
        params: dict[str, Any] = {}
        if match:
            params["match[]"] = match
        if from_ is not None:
            params["start"] = resolve_epoch_ms(from_) // 1000
        if to is not None:
            params["end"] = resolve_epoch_ms(to) // 1000
        data = await self._t.request_json(
            "GET",
            self._prom_path(project_id, "label", label, "values"),
            params=params,
            headers=self._headers(datasource),
        )
        return data if isinstance(data, dict) else {}

    async def query(
        self,
        project_id: str,
        query: str,
        *,
        legend: str = "",
        datasource: str = "",
        from_: TimeInput = None,
        to: TimeInput = None,
    ) -> dict[str, Any]:
        """Evaluate a PromQL range query through ``/panel/data`` (session auth).

        Returns ``{"chart": {"ctx": {"from", "to", "step"}, "series": [...]}}``.
        For multicluster projects ``datasource`` must be a member project name.
        """
        panel = build_panel(
            [metrics_query(query, datasource=datasource, legend=legend)],
            name="mcp-coroot",
        )
        params: dict[str, Any] = time_params(from_, to)
        params["query"] = json.dumps(panel, separators=(",", ":"))
        data = await self._t.get(
            self.project_path(project_id, "panel", "data"), params=params
        )
        return data if isinstance(data, dict) else {"chart": None}

    async def query_range(
        self,
        query: str,
        *,
        from_: TimeInput = None,
        to: TimeInput = None,
        step: str | int = "60s",
    ) -> dict[str, Any]:
        """Standard Prometheus ``query_range`` using ``COROOT_API_KEY``."""
        start = resolve_epoch_ms(from_, default="now-1h") / 1000
        end = resolve_epoch_ms(to, default="now") / 1000
        data = await self._t.request_json(
            "GET",
            "/api/v1/query_range",
            params={"query": query, "start": start, "end": end, "step": step},
            use_api_key=True,
        )
        return data if isinstance(data, dict) else {}
