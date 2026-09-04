"""Incidents, alerts and alerting rules."""

from __future__ import annotations

from typing import Any

from .base import BaseAPI, Enveloped, JsonValue, split_envelope
from .errors import CorootNotFoundError
from .ids import encode_segment
from .timerange import TimeInput, time_params

#: Alias used inside classes that define a ``list`` method.
StrList = list[str]


class IncidentsAPI(BaseAPI):
    async def list(
        self,
        project_id: str,
        *,
        limit: int = 100,
        from_: TimeInput = None,
        to: TimeInput = None,
    ) -> Enveloped:
        """SLO incidents, open ones first then newest."""
        params: dict[str, Any] = time_params(from_, to)
        params["limit"] = limit
        payload = await self._t.get(
            self.project_path(project_id, "incidents"), params=params
        )
        return split_envelope(payload)

    async def get(self, project_id: str, key: str) -> Enveloped:
        """One incident with SLO details, RCA and widgets (window = incident)."""
        payload = await self._t.get(
            self.project_path(project_id, "incident", encode_segment(key.strip()))
        )
        return split_envelope(payload)


class AlertsAPI(BaseAPI):
    async def list(
        self,
        project_id: str,
        *,
        include_resolved: bool = False,
        search: str | None = None,
        sort_by: str | None = None,
        sort_desc: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> Enveloped:
        """``data`` = ``{"alerts": [...], "total", "firing", "resolved"}``."""
        params: dict[str, Any] = {
            "include_resolved": include_resolved,
            "search": search,
            "sort_by": sort_by,
            "sort_desc": sort_desc,
            "limit": limit,
            "offset": offset,
        }
        payload = await self._t.get(
            self.project_path(project_id, "alerts"), params=params
        )
        return split_envelope(payload)

    async def get(self, project_id: str, alert_id: str) -> Enveloped:
        """One alert with its widgets; the time window is the alert's own."""
        alert_id = alert_id.strip()
        payload = await self._t.get(
            self.project_path(project_id, "alerts", encode_segment(alert_id)),
            params={"alert": alert_id},
        )
        return split_envelope(payload)

    async def resolve(self, project_id: str, ids: StrList) -> None:
        await self._t.post(
            self.project_path(project_id, "alerts", "resolve"), {"ids": ids}
        )

    async def suppress(self, project_id: str, ids: StrList) -> None:
        await self._t.post(
            self.project_path(project_id, "alerts", "suppress"), {"ids": ids}
        )

    async def reopen(self, project_id: str, ids: StrList) -> None:
        await self._t.post(
            self.project_path(project_id, "alerts", "reopen"), {"ids": ids}
        )


class AlertingRulesAPI(BaseAPI):
    async def list(self, project_id: str) -> Enveloped:
        """``data`` = ``{"rules", "checks", "categories", "alert_counts"}``."""
        payload = await self._t.get(self.project_path(project_id, "alerting-rules"))
        return split_envelope(payload)

    async def get(self, project_id: str, rule_id: str) -> dict[str, Any]:
        path = self.project_path(project_id, "alerting-rules", encode_segment(rule_id))
        data = await self._t.get(path)
        if not isinstance(data, dict):
            raise CorootNotFoundError("Rule not found", detail=rule_id, path=path)
        return data

    async def create(self, project_id: str, rule: dict[str, Any]) -> JsonValue:
        """Create a rule; Coroot assigns the id and returns the stored rule."""
        return await self._t.post(self.project_path(project_id, "alerting-rules"), rule)

    async def update(
        self, project_id: str, rule_id: str, rule: dict[str, Any]
    ) -> JsonValue:
        return await self._t.put(
            self.project_path(project_id, "alerting-rules", encode_segment(rule_id)),
            rule,
        )

    async def delete(self, project_id: str, rule_id: str) -> None:
        await self._t.delete(
            self.project_path(project_id, "alerting-rules", encode_segment(rule_id))
        )

    async def export(self, project_id: str) -> str:
        """All rules as a YAML document for the config file."""
        data = await self._t.get(
            self.project_path(project_id, "alerting-rules", "export")
        )
        if isinstance(data, dict):
            return str(data.get("yaml") or "")
        return ""
