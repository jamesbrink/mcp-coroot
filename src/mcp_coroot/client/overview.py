"""Project-wide overview views (``/overview/{view}``)."""

from __future__ import annotations

import json
from typing import Any, Literal

from .base import BaseAPI, Enveloped, split_envelope
from .timerange import TimeInput, time_params

OverviewView = Literal[
    "applications",
    "map",
    "nodes",
    "deployments",
    "traces",
    "logs",
    "costs",
    "risks",
    "fluxcd",
    "argocd",
]

OVERVIEW_VIEWS: tuple[str, ...] = (
    "applications",
    "map",
    "nodes",
    "deployments",
    "traces",
    "logs",
    "costs",
    "risks",
    "fluxcd",
    "argocd",
)


class OverviewAPI(BaseAPI):
    async def get(
        self,
        project_id: str,
        view: str,
        *,
        from_: TimeInput = None,
        to: TimeInput = None,
        query: dict[str, Any] | None = None,
    ) -> Enveloped:
        """Fetch one overview view; ``data`` is that view's payload only.

        Coroot returns the whole ``Overview`` struct with only the requested key
        populated, so the other (null) keys are dropped. ``categories`` (custom
        application categories) is exposed via ``context["categories"]``.
        """
        params: dict[str, Any] = time_params(from_, to)
        if query is not None:
            params["query"] = json.dumps(query, separators=(",", ":"))
        payload = await self._t.get(
            self.project_path(project_id, "overview", view), params=params
        )
        enveloped = split_envelope(payload)
        struct = enveloped.data if isinstance(enveloped.data, dict) else {}
        enveloped.context["categories"] = struct.get("categories") or []
        enveloped.data = struct.get(view)
        return enveloped

    async def applications(
        self, project_id: str, *, from_: TimeInput = None, to: TimeInput = None
    ) -> Enveloped:
        return await self.get(project_id, "applications", from_=from_, to=to)

    async def service_map(
        self, project_id: str, *, from_: TimeInput = None, to: TimeInput = None
    ) -> Enveloped:
        return await self.get(project_id, "map", from_=from_, to=to)

    async def nodes(
        self, project_id: str, *, from_: TimeInput = None, to: TimeInput = None
    ) -> Enveloped:
        return await self.get(project_id, "nodes", from_=from_, to=to)

    async def deployments(
        self, project_id: str, *, from_: TimeInput = None, to: TimeInput = None
    ) -> Enveloped:
        return await self.get(project_id, "deployments", from_=from_, to=to)

    async def costs(
        self, project_id: str, *, from_: TimeInput = None, to: TimeInput = None
    ) -> Enveloped:
        return await self.get(project_id, "costs", from_=from_, to=to)

    async def risks(
        self, project_id: str, *, from_: TimeInput = None, to: TimeInput = None
    ) -> Enveloped:
        return await self.get(project_id, "risks", from_=from_, to=to)

    async def traces(
        self,
        project_id: str,
        *,
        view: str = "summary",
        filters: list[dict[str, str]] | None = None,
        trace_id: str | None = None,
        dur_from: str | None = None,
        dur_to: str | None = None,
        include_aux: bool = False,
        diff: bool = False,
        from_: TimeInput = None,
        to: TimeInput = None,
    ) -> Enveloped:
        """Distributed tracing overview.

        ``view`` is one of ``summary`` (per-endpoint stats), ``traces`` (root
        spans), ``attributes``, ``errors`` or ``latency`` (flame graph). Filters
        are ``{"field": "ServiceName", "op": "=", "value": "checkout"}``.
        """
        query: dict[str, Any] = {
            "view": view,
            "filters": filters or [],
            "include_aux": include_aux,
            "diff": diff,
        }
        if trace_id:
            query["trace_id"] = trace_id
        if dur_from:
            query["dur_from"] = dur_from
        if dur_to:
            query["dur_to"] = dur_to
        return await self.get(project_id, "traces", from_=from_, to=to, query=query)

    async def logs(
        self,
        project_id: str,
        *,
        filters: list[dict[str, str]] | None = None,
        limit: int = 100,
        agent: bool = True,
        otel: bool = True,
        suggest: str | None = None,
        since: str | None = None,
        from_: TimeInput = None,
        to: TimeInput = None,
    ) -> Enveloped:
        """Project-wide log search across agent and OpenTelemetry sources."""
        query: dict[str, Any] = {
            "view": "messages",
            "agent": agent,
            "otel": otel,
            "filters": filters or [],
            "limit": limit,
        }
        if suggest is not None:
            query["suggest"] = suggest
        if since:
            query["since"] = since
        return await self.get(project_id, "logs", from_=from_, to=to, query=query)
