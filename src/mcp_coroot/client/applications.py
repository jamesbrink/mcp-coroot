"""Per-application endpoints: reports, logs, traces, profiling, settings, nodes."""

from __future__ import annotations

import json
from typing import Any

from .base import BaseAPI, Enveloped, JsonValue, split_envelope
from .errors import CorootValidationError
from .ids import PROJECT_SCOPE_APP_ID, encode_segment, normalize_app_id
from .timerange import TimeInput, resolve_epoch_ms, time_params

#: ``{type}`` values accepted by the instrumentation endpoint.
INSTRUMENTATION_TYPES: tuple[str, ...] = (
    "postgres",
    "mysql",
    "redis",
    "mongodb",
    "memcached",
)

#: Default ports Coroot uses per database type.
INSTRUMENTATION_DEFAULT_PORTS: dict[str, str] = {
    "postgres": "5432",
    "mysql": "3306",
    "redis": "6379",
    "mongodb": "27017",
    "memcached": "11211",
}

#: Check ids accepted by ``/inspection/{type}/config`` (model.Checks field names).
CHECK_IDS: tuple[str, ...] = (
    "SLOAvailability",
    "SLOLatency",
    "CPUNode",
    "CPUContainer",
    "MemoryOOM",
    "MemoryLeakPercent",
    "MemoryPressure",
    "StorageSpace",
    "StorageIOLoad",
    "NetworkRTT",
    "NetworkRTTExternal",
    "NetworkRTTOtherClusters",
    "NetworkConnectivity",
    "NetworkTCPConnections",
    "InstanceAvailability",
    "DeploymentStatus",
    "InstanceRestarts",
    "RedisAvailability",
    "RedisLatency",
    "MongodbAvailability",
    "MongodbReplicationLag",
    "MongodbLatency",
    "MongodbOplogWindow",
    "MongodbConnections",
    "MongodbSaturation",
    "MongodbFragmentation",
    "MongodbBackups",
    "MemcachedAvailability",
    "PostgresAvailability",
    "PostgresLatency",
    "PostgresReplicationLag",
    "PostgresConnections",
    "PostgresCheckpoint",
    "PostgresWalArchiving",
    "PostgresWraparound",
    "PostgresBloat",
    "PostgresAutovacuum",
    "PostgresStaleStatistics",
    "PostgresBackups",
    "LogErrors",
    "JvmAvailability",
    "JvmSafepointTime",
    "DotNetAvailability",
    "PythonGILWaitingTime",
    "NodejsEventLoopBlockedTime",
    "DnsLatency",
    "DnsServerErrors",
    "DnsNxdomainErrors",
    "MysqlAvailability",
    "MysqlReplicationStatus",
    "MysqlReplicationLag",
    "MysqlConnections",
)

LOG_SEVERITIES: tuple[str, ...] = (
    "unknown",
    "trace",
    "debug",
    "info",
    "warning",
    "error",
    "fatal",
)


def _absolute(value: TimeInput) -> str:
    """Render a time bound as epoch milliseconds, or "" when it is unset."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return ""
    return str(resolve_epoch_ms(value))


def build_trace_param(
    *,
    source: str = "",
    trace_id: str = "",
    ts_from: TimeInput = None,
    ts_to: TimeInput = None,
    dur_from: str | float | None = None,
    dur_to: str | float | None = None,
) -> str:
    """Encode the ``trace`` query parameter.

    Format: ``source:traceId:tsFrom-tsTo:durFrom-durTo``. ``dur_from``/``dur_to``
    are seconds (floats) or the markers ``inf`` / ``err`` (errors only).

    Coroot splits the timestamp range on its first ``-``, so relative bounds are
    resolved to epoch milliseconds before they are joined.
    """
    start = _absolute(ts_from)
    end = _absolute(ts_to)
    ts = f"{start}-{end}" if (start or end) else ""
    d_from = "" if dur_from is None else str(dur_from)
    d_to = "" if dur_to is None else str(dur_to)
    dur = f"{d_from}-{d_to}" if (d_from or d_to) else ""
    return f"{source}:{trace_id}:{ts}:{dur}"


class ApplicationsAPI(BaseAPI):
    def _app_path(self, project_id: str, app_id: str, *segments: str) -> str:
        full_id = normalize_app_id(app_id, project_id=project_id)
        return self.project_path(project_id, "app", encode_segment(full_id), *segments)

    async def get(
        self,
        project_id: str,
        app_id: str,
        *,
        from_: TimeInput = None,
        to: TimeInput = None,
        incident: str | None = None,
        alert: str | None = None,
    ) -> Enveloped:
        """The full application view: ``app_map`` plus every audit ``report``."""
        params = time_params(from_, to, incident=incident, alert=alert)
        payload = await self._t.get(self._app_path(project_id, app_id), params=params)
        return split_envelope(payload)

    # -- telemetry ------------------------------------------------------------

    async def logs(
        self,
        project_id: str,
        app_id: str,
        *,
        view: str = "messages",
        source: str = "",
        filters: list[dict[str, str]] | None = None,
        limit: int = 100,
        suggest: str | None = None,
        since: str | None = None,
        from_: TimeInput = None,
        to: TimeInput = None,
    ) -> Enveloped:
        """Log entries or log patterns for one application."""
        query: dict[str, Any] = {
            "source": source,
            "view": view,
            "filters": filters or [],
            "limit": limit,
        }
        if suggest is not None:
            query["suggest"] = suggest
        if since:
            query["since"] = since
        params: dict[str, Any] = time_params(from_, to)
        params["query"] = json.dumps(query, separators=(",", ":"))
        payload = await self._t.get(
            self._app_path(project_id, app_id, "logs"), params=params
        )
        return split_envelope(payload)

    async def tracing(
        self,
        project_id: str,
        app_id: str,
        *,
        trace: str | None = None,
        from_: TimeInput = None,
        to: TimeInput = None,
    ) -> Enveloped:
        """Spans for one application (``trace`` from :func:`build_trace_param`)."""
        params: dict[str, Any] = time_params(from_, to)
        if trace:
            params["trace"] = trace
        payload = await self._t.get(
            self._app_path(project_id, app_id, "tracing"), params=params
        )
        return split_envelope(payload)

    async def profiling(
        self,
        project_id: str,
        app_id: str,
        *,
        query: str | dict[str, Any] | None = None,
        from_: TimeInput = None,
        to: TimeInput = None,
    ) -> Enveloped:
        """Flame graph data. ``query`` is ``cpu``/``memory``/``lock`` or a JSON spec."""
        params: dict[str, Any] = time_params(from_, to)
        if isinstance(query, dict):
            params["query"] = json.dumps(query, separators=(",", ":"))
        elif query:
            params["query"] = query
        payload = await self._t.get(
            self._app_path(project_id, app_id, "profiling"), params=params
        )
        return split_envelope(payload)

    async def rca(
        self,
        project_id: str,
        app_id: str,
        *,
        from_: TimeInput = None,
        to: TimeInput = None,
    ) -> JsonValue:
        """AI root-cause analysis (backed by Coroot Cloud; status is in the body)."""
        return await self._t.get(
            self._app_path(project_id, app_id, "rca"), params=time_params(from_, to)
        )

    # -- settings -------------------------------------------------------------

    async def set_profiling_service(
        self, project_id: str, app_id: str, service: str
    ) -> None:
        await self._t.post(
            self._app_path(project_id, app_id, "profiling"), {"service": service}
        )

    async def set_tracing_service(
        self, project_id: str, app_id: str, service: str
    ) -> None:
        await self._t.post(
            self._app_path(project_id, app_id, "tracing"), {"service": service}
        )

    async def set_logs_service(
        self, project_id: str, app_id: str, service: str
    ) -> None:
        await self._t.post(
            self._app_path(project_id, app_id, "logs"), {"service": service}
        )

    async def get_inspection_config(
        self, project_id: str, app_id: str, check_id: str
    ) -> dict[str, Any]:
        """``{"form": ..., "integrations": [...]}`` for one check.

        Use ``app_id="::"`` for the project-wide defaults.
        """
        data = await self._t.get(
            self._app_path(project_id, app_id, "inspection", check_id, "config")
        )
        return data if isinstance(data, dict) else {}

    async def set_inspection_config(
        self, project_id: str, app_id: str, check_id: str, form: dict[str, Any]
    ) -> None:
        await self._t.post(
            self._app_path(project_id, app_id, "inspection", check_id, "config"),
            form,
        )

    async def get_instrumentation(
        self, project_id: str, app_id: str, db_type: str
    ) -> dict[str, Any]:
        data = await self._t.get(
            self._app_path(project_id, app_id, "instrumentation", db_type)
        )
        return data if isinstance(data, dict) else {}

    async def set_instrumentation(
        self, project_id: str, app_id: str, config: dict[str, Any]
    ) -> None:
        """Save database instrumentation; ``config["type"]`` is what Coroot stores."""
        db_type = str(config.get("type") or "")
        if not db_type:
            raise CorootValidationError(
                "Invalid request", detail="instrumentation config needs a 'type'"
            )
        await self._t.post(
            self._app_path(project_id, app_id, "instrumentation", db_type), config
        )

    async def set_risk_override(
        self,
        project_id: str,
        app_id: str,
        *,
        action: str,
        category: str,
        risk_type: str,
        reason: str = "",
    ) -> None:
        """Dismiss (``dismiss``) or re-activate (``mark_as_active``) a risk."""
        await self._t.post(
            self._app_path(project_id, app_id, "risks"),
            {
                "action": action,
                "key": {"category": category, "type": risk_type},
                "reason": reason,
            },
        )

    @staticmethod
    def project_scope() -> str:
        return PROJECT_SCOPE_APP_ID


class NodesAPI(BaseAPI):
    async def get(
        self,
        project_id: str,
        node: str,
        *,
        from_: TimeInput = None,
        to: TimeInput = None,
    ) -> Enveloped:
        """The node audit report (CPU, memory, disk, network checks and charts)."""
        payload = await self._t.get(
            self.project_path(project_id, "node", encode_segment(node.strip())),
            params=time_params(from_, to),
        )
        return split_envelope(payload)
