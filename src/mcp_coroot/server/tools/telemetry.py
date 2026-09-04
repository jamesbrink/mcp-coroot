"""Tools for logs, traces, profiles and metrics."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from ...client.applications import LOG_SEVERITIES, build_trace_param
from ...client.ids import normalize_app_id
from ...client.timerange import ms_to_iso, parse_duration_ms
from ...config import Settings
from ..app import READ_ONLY
from ..compact import compact, compact_dict, flamegraph_summary, limit_items
from ..errors import guard
from ..state import AppState, ToolContext
from ._common import AppIdParam, FromParam, ProjectIdParam, ToParam, respond, target

#: Profile categories Coroot resolves to a featured profile type.
PROFILE_CATEGORIES: tuple[str, ...] = ("cpu", "memory", "lock")


def _seconds(value: float) -> str:
    """Render a duration the way Coroot's heatmap parser expects: float seconds."""
    return f"{value:g}"


ServiceParam = Annotated[
    str | None,
    Field(description="Filter to one OpenTelemetry service name, e.g. 'checkout'."),
]
SpanParam = Annotated[
    str | None,
    Field(description="Filter to one span (endpoint) name, e.g. 'GET /cart'."),
]


def _log_filters(
    severity: list[str] | None, search: str | None, trace_id: str | None
) -> list[dict[str, str]]:
    filters: list[dict[str, str]] = []
    for level in severity or []:
        filters.append({"name": "Severity", "op": "=", "value": level.strip().lower()})
    if search:
        filters.append({"name": "Message", "op": "contains", "value": search})
    if trace_id:
        filters.append({"name": "TraceId", "op": "=", "value": trace_id})
    return filters


def _trace_filters(service: str | None, span: str | None) -> list[dict[str, str]]:
    filters: list[dict[str, str]] = []
    if service:
        filters.append({"field": "ServiceName", "op": "=", "value": service})
    if span:
        filters.append({"field": "SpanName", "op": "=", "value": span})
    return filters


def _endpoint_digest(stat: dict[str, Any]) -> dict[str, Any]:
    """Keep the numbers that rank an endpoint, drop its per-pod charts."""
    total = stat.get("total") or 0
    failed = stat.get("failed") or 0
    quantiles = {
        f"p{int(float(q.get('quantile', 0)) * 100)}": q.get("value")
        for q in (stat.get("duration_quantiles") or [])
        if isinstance(q, dict) and q.get("quantile") is not None
    }
    return {
        "service": stat.get("service_name"),
        "span": stat.get("span_name"),
        "requests": total,
        "failed": failed,
        "error_rate": round(failed / total, 4) if total else None,
        "latency_seconds": quantiles or None,
    }


def _endpoint_sort_key(kind: str) -> Any:
    def key(entry: dict[str, Any]) -> float:
        if kind == "errors":
            return float(entry.get("failed") or 0)
        if kind == "latency":
            latency = entry.get("latency_seconds") or {}
            return float(latency.get("p99") or latency.get("p95") or 0)
        return float(entry.get("requests") or 0)

    return key


def _entry_digest(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": ms_to_iso(entry.get("timestamp")),
        "severity": entry.get("severity"),
        "message": entry.get("message"),
        "application": entry.get("application"),
        "trace_id": entry.get("trace_id") or None,
    }


def register(mcp: MCPServer[AppState], settings: Settings) -> None:
    @mcp.tool(title="Search logs", annotations=READ_ONLY)
    @guard
    async def get_logs(
        ctx: ToolContext,
        project_id: ProjectIdParam = None,
        app_id: Annotated[
            str | None,
            Field(
                description=(
                    "Application id from list_applications. Omit to search every "
                    "application in the project."
                )
            ),
        ] = None,
        severity: Annotated[
            list[str] | None,
            Field(
                description=(
                    "Severities to include: 'unknown', 'trace', 'debug', 'info', "
                    "'warning', 'error', 'fatal'. Omit for all."
                )
            ),
        ] = None,
        search: Annotated[
            str | None,
            Field(
                description=(
                    "Full-text search over the message body. Tokens are combined "
                    "with AND and matched case-insensitively."
                )
            ),
        ] = None,
        trace_id: Annotated[
            str | None, Field(description="Only entries belonging to this trace id.")
        ] = None,
        limit: Annotated[
            int, Field(description="Maximum entries to return.", ge=1, le=1000)
        ] = 100,
        since: Annotated[
            str | None,
            Field(
                description=(
                    "Continue after an earlier call: pass the next_since value "
                    "it returned to get entries newer than the last one seen."
                )
            ),
        ] = None,
        from_time: FromParam = None,
        to_time: ToParam = None,
    ) -> dict[str, Any]:
        """Search log entries, newest first, for one application or a whole project.

        Requires ClickHouse in Coroot. Start narrow: a one-hour window with a
        severity filter. To continue past the entries returned, pass the
        response's next_since value back as `since`.
        """
        state, pid = await target(ctx, project_id)
        for level in severity or []:
            if level.strip().lower() not in LOG_SEVERITIES:
                raise ValueError(
                    f"unknown severity {level!r}: use one of "
                    f"{', '.join(LOG_SEVERITIES)}"
                )
        filters = _log_filters(severity, search, trace_id)
        if app_id:
            result = await state.coroot.applications.logs(
                pid,
                app_id,
                filters=filters,
                limit=limit,
                since=since,
                from_=from_time,
                to=to_time,
            )
        else:
            result = await state.coroot.overview.logs(
                pid,
                filters=filters,
                limit=limit,
                since=since,
                from_=from_time,
                to=to_time,
            )
        data = result.data if isinstance(result.data, dict) else {}
        entries = [e for e in (data.get("entries") or []) if isinstance(e, dict)]
        kept, omitted = limit_items(entries, limit)
        return respond(
            state,
            {
                "project_id": pid,
                "application_id": normalize_app_id(app_id, project_id=pid)
                if app_id
                else None,
                "message": data.get("message") or None,
                "error": data.get("error") or None,
                "returned": len(kept),
                "omitted": omitted or None,
                "next_since": data.get("max_ts") or None,
                "entries": [_entry_digest(e) for e in kept],
            },
        )

    @mcp.tool(title="Get log patterns", annotations=READ_ONLY)
    @guard
    async def get_log_patterns(
        ctx: ToolContext,
        app_id: AppIdParam,
        project_id: ProjectIdParam = None,
        from_time: FromParam = None,
        to_time: ToParam = None,
    ) -> dict[str, Any]:
        """Group an application's logs into repeated patterns with their volumes.

        Faster than reading raw logs when you want to know what an application is
        complaining about most. Works from metrics, so it does not need ClickHouse.
        """
        state, pid = await target(ctx, project_id)
        result = await state.coroot.applications.logs(
            pid, app_id, view="patterns", from_=from_time, to=to_time
        )
        data = result.data if isinstance(result.data, dict) else {}
        patterns = [
            {
                "severity": p.get("severity"),
                "count": p.get("sum"),
                "sample": p.get("sample"),
                "hash": p.get("hash"),
            }
            for p in (data.get("patterns") or [])
            if isinstance(p, dict)
        ]
        patterns.sort(key=lambda p: p.get("count") or 0, reverse=True)
        return respond(
            state,
            {
                "project_id": pid,
                "application_id": normalize_app_id(app_id, project_id=pid),
                "message": data.get("message") or None,
                "count": len(patterns),
                "patterns": patterns,
            },
        )

    @mcp.tool(title="Summarise trace endpoints", annotations=READ_ONLY)
    @guard
    async def summarize_trace_endpoints(
        ctx: ToolContext,
        project_id: ProjectIdParam = None,
        service: ServiceParam = None,
        span: SpanParam = None,
        sort_by: Annotated[
            Literal["errors", "latency", "requests"],
            Field(description="Which endpoints to rank first."),
        ] = "errors",
        limit: Annotated[
            int, Field(description="Maximum endpoints to return.", ge=1, le=500)
        ] = 20,
        from_time: FromParam = None,
        to_time: ToParam = None,
    ) -> dict[str, Any]:
        """Summarise distributed traces per endpoint: rate, errors and latency.

        The first stop for "what is slow or failing?", ranked worst-first.
        Latency quantiles are in SECONDS. Follow up with get_trace_errors for
        failure reasons or get_trace_latency for the slow tail. Requires
        ClickHouse in Coroot.
        """
        state, pid = await target(ctx, project_id)
        result = await state.coroot.overview.traces(
            pid,
            view="summary",
            filters=_trace_filters(service, span),
            from_=from_time,
            to=to_time,
        )
        data = result.data if isinstance(result.data, dict) else {}
        summary = data.get("summary") or {}
        stats = summary.get("stats") if isinstance(summary, dict) else None
        endpoints = [
            _endpoint_digest(stat) for stat in (stats or []) if isinstance(stat, dict)
        ]
        endpoints.sort(key=_endpoint_sort_key(sort_by), reverse=True)
        kept, omitted = limit_items(endpoints, limit)
        return respond(
            state,
            {
                "project_id": pid,
                "message": data.get("message") or None,
                "error": data.get("error") or None,
                "total_endpoints": len(endpoints),
                "omitted": omitted or None,
                "sorted_by": sort_by,
                "endpoints": kept,
                "overall": compact(summary.get("overall"))
                if isinstance(summary, dict)
                else None,
            },
        )

    @mcp.tool(title="List trace error reasons", annotations=READ_ONLY)
    @guard
    async def list_trace_error_reasons(
        ctx: ToolContext,
        project_id: ProjectIdParam = None,
        service: ServiceParam = None,
        span: SpanParam = None,
        from_time: FromParam = None,
        to_time: ToParam = None,
    ) -> dict[str, Any]:
        """List the top error reasons in traces, with a sample trace id for each.

        Feed a sample trace id to get_trace_by_id to see the whole failing
        request, or use list_traces to pick one yourself.
        """
        state, pid = await target(ctx, project_id)
        result = await state.coroot.overview.traces(
            pid,
            view="errors",
            filters=_trace_filters(service, span),
            from_=from_time,
            to=to_time,
        )
        data = result.data if isinstance(result.data, dict) else {}
        return respond(
            state,
            {
                "project_id": pid,
                "message": data.get("message") or None,
                "errors": compact(data.get("errors") or []),
            },
        )

    @mcp.tool(title="Explain slow traces", annotations=READ_ONLY)
    @guard
    async def explain_trace_latency(
        ctx: ToolContext,
        project_id: ProjectIdParam = None,
        service: ServiceParam = None,
        span: SpanParam = None,
        slower_than: Annotated[
            str,
            Field(
                description=(
                    "Lower bound of the slow band, e.g. '1s', '500ms' or '2.5s'. "
                    "Traces at or above it are compared against the rest. Must be "
                    "greater than zero."
                )
            ),
        ] = "1s",
        faster_than: Annotated[
            str | None,
            Field(
                description=(
                    "Optional upper bound of the slow band, e.g. '5s'. Omit for no "
                    "upper bound."
                )
            ),
        ] = None,
        from_time: FromParam = None,
        to_time: ToParam = None,
    ) -> dict[str, Any]:
        """Explain a high p99 by showing where slow requests spend their time.

        Returns the heaviest frames of a flame graph built from traces inside
        the band. Sizes from summarize_trace_endpoints are in SECONDS, so pass
        them with a unit ('1.85s'): a bare number is read as milliseconds.
        """
        state, pid = await target(ctx, project_id)
        # Coroot parses these bounds as float seconds, not as durations, and a
        # band it cannot parse selects nothing at all.
        dur_from = parse_duration_ms(slower_than) / 1000
        if dur_from <= 0:
            raise ValueError(
                f"slower_than must be greater than zero, got {slower_than!r}"
            )
        dur_to = parse_duration_ms(faster_than) / 1000 if faster_than else None
        if dur_to is not None and dur_to <= dur_from:
            raise ValueError(
                f"faster_than ({faster_than}) must be greater than slower_than "
                f"({slower_than})"
            )
        result = await state.coroot.overview.traces(
            pid,
            view="latency",
            filters=_trace_filters(service, span),
            dur_from=_seconds(dur_from),
            dur_to=_seconds(dur_to) if dur_to is not None else None,
            # Never ask for the differential view. Coroot builds it with
            # FlameGraphNode.Diff, which dereferences its argument without a nil
            # check, and either side is nil when the band or its complement
            # selects no traces -- which crashes the request handler.
            diff=False,
            from_=from_time,
            to=to_time,
        )
        data = result.data if isinstance(result.data, dict) else {}
        latency = data.get("latency") or {}
        graph = latency.get("flamegraph") if isinstance(latency, dict) else None
        return respond(
            state,
            {
                "project_id": pid,
                "message": data.get("message") or None,
                "band": {
                    "slower_than_seconds": dur_from,
                    "faster_than_seconds": dur_to,
                },
                "hotspots": flamegraph_summary(graph, top=25) if graph else None,
                "note": None
                if graph
                else (
                    "No traces fell in this band. Lower slower_than or widen "
                    "the time window."
                ),
            },
        )

    @mcp.tool(title="List slow or failed traces", annotations=READ_ONLY)
    @guard
    async def list_traces(
        ctx: ToolContext,
        project_id: ProjectIdParam = None,
        service: ServiceParam = None,
        span: SpanParam = None,
        slower_than: Annotated[
            str | None,
            Field(
                description=(
                    "Only traces at least this slow, e.g. '1s' or '500ms'. Sizes "
                    "from get_traces are in seconds, so pass them with a unit."
                )
            ),
        ] = None,
        errors_only: Annotated[
            bool, Field(description="Only traces that ended in an error.")
        ] = False,
        limit: Annotated[
            int, Field(description="Maximum traces to return.", ge=1, le=100)
        ] = 20,
        from_time: FromParam = None,
        to_time: ToParam = None,
    ) -> dict[str, Any]:
        """List individual traces, with the ids needed to open one.

        The step between summarize_trace_endpoints, which says an endpoint's
        p99 is bad, and get_trace_by_id, which shows one request in full: this
        finds the actual slow or failed requests. Requires ClickHouse in Coroot.
        """
        state, pid = await target(ctx, project_id)
        dur_from = (
            _seconds(parse_duration_ms(slower_than) / 1000) if slower_than else None
        )
        result = await state.coroot.overview.traces(
            pid,
            view="traces",
            filters=_trace_filters(service, span),
            dur_from="inf" if errors_only else dur_from,
            from_=from_time,
            to=to_time,
        )
        data = result.data if isinstance(result.data, dict) else {}
        traces = [t for t in (data.get("traces") or []) if isinstance(t, dict)]
        digests = [
            {
                "trace_id": t.get("trace_id") or t.get("id"),
                "service": t.get("service"),
                "name": t.get("name"),
                "timestamp": ms_to_iso(t.get("timestamp")),
                "duration_ms": t.get("duration"),
                "status": t.get("status"),
            }
            for t in traces
        ]
        kept, omitted = limit_items(digests, limit)
        return respond(
            state,
            {
                "project_id": pid,
                "message": data.get("message") or None,
                "matched": len(digests),
                "omitted": omitted or None,
                "traces": kept,
                "note": None
                if kept
                else (
                    "No traces matched. Lower slower_than, widen the time range, "
                    "or check get_traces for which endpoints have traffic."
                ),
            },
        )

    @mcp.tool(title="Get one trace by id", annotations=READ_ONLY)
    @guard
    async def get_trace_by_id(
        ctx: ToolContext,
        trace_id: Annotated[
            str,
            Field(
                description=(
                    "Trace id, from list_traces, list_trace_error_reasons or get_logs."
                )
            ),
        ],
        project_id: ProjectIdParam = None,
        app_id: Annotated[
            str | None,
            Field(
                description=(
                    "Application the trace belongs to. Narrows the search and is "
                    "faster when known."
                )
            ),
        ] = None,
        from_time: FromParam = None,
        to_time: ToParam = None,
    ) -> dict[str, Any]:
        """Fetch one distributed trace as a span tree with attributes and events.

        Coroot searches the given time window, so widen it if the trace is older
        than an hour.
        """
        state, pid = await target(ctx, project_id)
        if app_id:
            result = await state.coroot.applications.tracing(
                pid,
                app_id,
                trace=build_trace_param(trace_id=trace_id),
                from_=from_time,
                to=to_time,
            )
            data = result.data if isinstance(result.data, dict) else {}
            spans = data.get("spans") or []
        else:
            result = await state.coroot.overview.traces(
                pid, view="traces", trace_id=trace_id, from_=from_time, to=to_time
            )
            data = result.data if isinstance(result.data, dict) else {}
            trace = data.get("trace")
            spans = trace if isinstance(trace, list) else (data.get("traces") or [])
        digests = [
            {
                "service": s.get("service"),
                "name": s.get("name"),
                "id": s.get("id"),
                "parent_id": s.get("parent_id") or None,
                "timestamp": ms_to_iso(s.get("timestamp")),
                "duration_ms": s.get("duration"),
                "status": s.get("status"),
                "attributes": s.get("attributes"),
                "events": s.get("events"),
            }
            for s in spans
            if isinstance(s, dict)
        ]
        return respond(
            state,
            {
                "project_id": pid,
                "trace_id": trace_id,
                "message": data.get("message") or None,
                "span_count": len(digests),
                "spans": compact(digests),
            },
        )

    @mcp.tool(title="Get a CPU or memory profile", annotations=READ_ONLY)
    @guard
    async def get_profile(
        ctx: ToolContext,
        app_id: AppIdParam,
        project_id: ProjectIdParam = None,
        profile: Annotated[
            str,
            Field(
                description=(
                    "'cpu', 'memory' or 'lock' for the featured profile of that "
                    "kind, or an exact profile type such as "
                    "'go:profile_cpu:nanoseconds' (see available_profiles in a "
                    "previous response)."
                )
            ),
        ] = "cpu",
        instance: Annotated[
            str | None,
            Field(
                description=(
                    "Limit to one instance (pod) name instead of the whole application."
                )
            ),
        ] = None,
        from_time: FromParam = None,
        to_time: ToParam = None,
    ) -> dict[str, Any]:
        """Get an application's profile as its heaviest call-stack frames.

        The raw flame graph is far too large for a context window, so it is
        reduced to the hottest leaves. Requires profiling to be enabled and
        ClickHouse to be configured.
        """
        state, pid = await target(ctx, project_id)
        wanted = profile.strip()
        is_category = ":" not in wanted
        if is_category and wanted not in PROFILE_CATEGORIES:
            raise ValueError(
                f"profile must be one of {', '.join(PROFILE_CATEGORIES)}, or an "
                f"exact profile type containing ':' (got {profile!r})"
            )

        query: str | dict[str, Any] = wanted
        if is_category and instance:
            # Coroot only resolves a category to its featured profile type when
            # the request carries no type at all, so an instance filter needs the
            # concrete type. Ask for the category first to learn it.
            probe = await state.coroot.applications.profiling(
                pid, app_id, query=wanted, from_=from_time, to=to_time
            )
            probe_data = probe.data if isinstance(probe.data, dict) else {}
            resolved = (probe_data.get("profile") or {}).get("type")
            if not resolved:
                return respond(
                    state,
                    {
                        "project_id": pid,
                        "application_id": normalize_app_id(app_id, project_id=pid),
                        "status": probe_data.get("status"),
                        "message": probe_data.get("message")
                        or f"No {wanted} profiles found for this application",
                        "available_profiles": probe_data.get("profiles"),
                    },
                )
            query = {"type": resolved, "instance": instance}
        elif not is_category:
            query = {"type": wanted, "instance": instance or ""}

        result = await state.coroot.applications.profiling(
            pid, app_id, query=query, from_=from_time, to=to_time
        )
        data = result.data if isinstance(result.data, dict) else {}
        current = data.get("profile") or {}
        graph = current.get("flamegraph") if isinstance(current, dict) else None
        return respond(
            state,
            {
                "project_id": pid,
                "application_id": normalize_app_id(app_id, project_id=pid),
                "instance": instance,
                "status": data.get("status"),
                "message": data.get("message") or None,
                "profile_type": current.get("type")
                if isinstance(current, dict)
                else None,
                "available_profiles": data.get("profiles"),
                "instances": data.get("instances"),
                "hotspots": flamegraph_summary(graph, top=30) if graph else None,
            },
        )

    @mcp.tool(title="Run a PromQL query", annotations=READ_ONLY)
    @guard
    async def get_metrics(
        ctx: ToolContext,
        query: Annotated[
            str,
            Field(
                description=(
                    "PromQL expression, e.g. 'rate(container_cpu_usage_seconds"
                    "_total[5m])'. Discover metric names with list_metrics."
                )
            ),
        ],
        project_id: ProjectIdParam = None,
        from_time: FromParam = None,
        to_time: ToParam = None,
        limit: Annotated[
            int, Field(description="Maximum series to return.", ge=1, le=500)
        ] = 50,
    ) -> dict[str, Any]:
        """Run a PromQL range query against the project's metrics backend.

        Series are returned as statistics (last, min, max, average) rather than
        raw samples. Use it to check a number Coroot reports, or to look at a
        metric no built-in report covers.
        """
        state, pid = await target(ctx, project_id)
        data = await state.coroot.metrics.query(pid, query, from_=from_time, to=to_time)
        chart = compact_dict({"chart": data.get("chart")}).get("chart") or {}
        series = chart.get("series") or []
        kept, omitted = limit_items(series, limit)
        return respond(
            state,
            {
                "project_id": pid,
                "query": query,
                "window": chart.get("window"),
                "series_count": len(series),
                "omitted": omitted or None,
                "series": kept,
                "message": None
                if series
                else (
                    "The query matched no series in this window. Check the metric "
                    "name with list_metrics, or widen from_time."
                ),
            },
        )

    @mcp.tool(title="Discover metric names", annotations=READ_ONLY)
    @guard
    async def list_metrics(
        ctx: ToolContext,
        project_id: ProjectIdParam = None,
        match: Annotated[
            str | None,
            Field(
                description=(
                    "Regular expression the metric name must match, e.g. "
                    "'redis.*' or 'container_net_.*'. Omit for all names."
                )
            ),
        ] = None,
        limit: Annotated[
            int, Field(description="Maximum names to return.", ge=1, le=5000)
        ] = 500,
        from_time: FromParam = None,
        to_time: ToParam = None,
    ) -> dict[str, Any]:
        """List metric names available in the project, to build a get_metrics query."""
        state, pid = await target(ctx, project_id)
        selector = f'{{__name__=~"{match}"}}' if match else None
        data = await state.coroot.metrics.label_values(
            pid,
            "__name__",
            match=[selector] if selector else None,
            from_=from_time,
            to=to_time,
        )
        names = [n for n in (data.get("data") or []) if isinstance(n, str)]
        kept, omitted = limit_items(sorted(names), limit)
        return respond(
            state,
            {
                "project_id": pid,
                "match": match,
                "count": len(names),
                "omitted": omitted or None,
                "metrics": kept,
            },
        )
