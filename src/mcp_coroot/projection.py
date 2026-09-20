"""Opt-in bounded projections for large Coroot read payloads.

Pure functions: no I/O, no extra HTTP request. Applied on the already-fetched
overview / application payload when the caller passes ``summary=True``.
``summary=False`` (default) is byte-identical passthrough.

Contract (public tool surface — ``summary`` on
``get_application`` / ``get_applications_overview``):

- The ``context.search`` global directory is DROPPED, never replicated:
  ``directory_returned`` is always 0 and ``directory_dropped`` carries the
  total. The directory is intentionally unbounded upstream (283 entries here,
  grows with the fleet), so no ``max_*`` cap governs it.
- Dependency/client ids are a semantic identity list, intentionally
  UNBOUNDED: every id is kept, named in ``unbounded``, with no hard
  total-bytes claim on the envelope.
- Malformed items (non-dict rows/nodes/reports) are skipped and counted as
  ``*_malformed`` — never conflated with cap truncation, so
  ``returned + truncated + malformed == total`` holds everywhere.
"""

from typing import Any

_OVERVIEW_IDENTITY_FIELDS = (
    "id",
    "cluster",
    "category",
    "status",
)

_OVERVIEW_SIGNALS = (
    "errors",
    "latency",
    "cpu",
    "memory",
    "disk_io_load",
    "disk_usage",
    "network",
    "dns",
    "logs",
    "restarts",
)

_MAX_NODE_INDICATORS = 20


def _signal_value(signal: Any) -> Any:
    if isinstance(signal, dict):
        if "value" in signal:
            return {"status": signal.get("status"), "value": signal.get("value")}
        if signal.get("status") == "unknown":
            return signal
        return {"status": signal.get("status"), "reason": "malformed-signal"}
    return signal


def _summarize_overview_app(app: dict[str, Any]) -> dict[str, Any]:
    """Keep identity + dependency/provenance signals, drop chart payload."""
    out: dict[str, Any] = {k: app.get(k) for k in _OVERVIEW_IDENTITY_FIELDS if k in app}
    for sig in ("upstreams", "instances", *_OVERVIEW_SIGNALS):
        if sig in app:
            out[sig] = _signal_value(app[sig])
    return out


def _check_caps(**caps: int) -> None:
    for name, value in caps.items():
        minimum = 0 if name == "max_table_rows" else 1
        if value < minimum:
            raise ValueError(f"{name} must be >= {minimum}, got {value}")


def check_overview_caps(max_apps: int) -> None:
    """Validate overview caps before any HTTP call (invalid cap raises)."""
    _check_caps(max_apps=max_apps)


def check_application_caps(max_table_rows: int, max_nodes: int) -> None:
    """Validate application caps before any HTTP call (invalid caps raise)."""
    _check_caps(max_table_rows=max_table_rows, max_nodes=max_nodes)


def _directory_total(overview_or_app: dict[str, Any]) -> int:
    context = overview_or_app.get("context", {})
    if not isinstance(context, dict):
        return 0
    search = context.get("search", {})
    if not isinstance(search, dict):
        return 0
    search_apps = search.get("applications", [])
    if not isinstance(search_apps, list):
        return 0
    return len(search_apps)


def summarize_overview(overview: dict[str, Any], max_apps: int = 50) -> dict[str, Any]:
    """Project an applications-overview payload into a bounded summary."""
    _check_caps(max_apps=max_apps)
    context = overview.get("context", {}) if isinstance(overview, dict) else {}
    if not isinstance(context, dict):
        context = {}
    data = overview.get("data", {}) if isinstance(overview, dict) else {}
    if not isinstance(data, dict):
        data = {}
    apps = data.get("applications", [])
    if not isinstance(apps, list):
        apps = []
    malformed = sum(1 for a in apps if not isinstance(a, dict))
    dicts = [a for a in apps if isinstance(a, dict)]
    kept = [_summarize_overview_app(a) for a in dicts[:max_apps]]
    apps_total = len(apps)
    directory_total = _directory_total(overview if isinstance(overview, dict) else {})
    apps_truncated = max(0, len(dicts) - len(kept))
    return {
        "projected": True,
        "limits": {"max_apps": max_apps},
        "counts": {
            "applications_returned": len(kept),
            "applications_truncated": apps_truncated,
            "applications_malformed": malformed,
            "applications_total": apps_total,
            "directory_returned": 0,
            "directory_truncated": 0,
            "directory_dropped": directory_total,
            "directory_total": directory_total,
        },
        "context_status": context.get("status", {}),
        "categories": data.get("categories", []),
        "applications": kept,
        "dropped": {
            "directory_ids": directory_total,
            "chart_payloads": len(kept),
        },
        "detail": {
            "how": (
                "call get_applications_overview(project_id) with summary=False "
                "for the full payload, or get_application(project_id, app_id) "
                "for one app"
            ),
        },
    }


def _summarize_node(node: Any, max_indicators: int = _MAX_NODE_INDICATORS) -> Any:
    if not isinstance(node, dict):
        return {"malformed": True}
    out: dict[str, Any] = {
        k: node.get(k)
        for k in (
            "id",
            "cluster",
            "category",
            "custom",
            "status",
            "icon",
            "link_status",
            "link_status_reason",
            "link_direction",
            "labels",
        )
        if k in node
    }
    indicators = node.get("indicators", [])
    if isinstance(indicators, list):
        out["indicators"] = indicators[:max_indicators]
        out["indicators_truncated"] = max(0, len(indicators) - len(out["indicators"]))
    out["link_stats_count"] = len(node.get("link_stats", []) or [])
    return out


def _summarize_widget(widget: Any, max_table_rows: int) -> dict[str, Any]:
    if not isinstance(widget, dict):
        return {"kind": "malformed"}
    if "table" in widget:
        table = widget.get("table", {})
        header = table.get("header", []) if isinstance(table, dict) else []
        rows = table.get("rows", []) if isinstance(table, dict) else []
        total = len(rows) if isinstance(rows, list) else 0
        kept_rows = []
        malformed = 0
        if isinstance(rows, list):
            for row in rows[:max_table_rows]:
                if not isinstance(row, dict):
                    malformed += 1
                    continue
                cells = row.get("cells", [])
                kept_rows.append(
                    {
                        "id": row.get("id"),
                        "cells": [
                            cell.get("value") if isinstance(cell, dict) else cell
                            for cell in cells
                            if isinstance(cells, list)
                        ],
                    }
                )
            malformed = sum(
                1 for row in rows[:max_table_rows] if not isinstance(row, dict)
            )
        truncated = max(0, total - len(kept_rows) - malformed)
        return {
            "kind": "table",
            "header": header,
            "rows": kept_rows,
            "rows_returned": len(kept_rows),
            "rows_truncated": truncated,
            "rows_malformed": malformed,
            "rows_total": total,
        }
    if "chart" in widget or "chart_group" in widget or "heatmap" in widget:
        key = (
            "chart_group"
            if "chart_group" in widget
            else ("heatmap" if "heatmap" in widget else "chart")
        )
        group = widget.get(key, {})
        charts = group.get("charts", [group]) if isinstance(group, dict) else []
        series_count = 0
        points_dropped = 0
        if isinstance(charts, list):
            for chart in charts:
                series = chart.get("series", []) if isinstance(chart, dict) else []
                if not isinstance(series, list):
                    continue
                for serie in series:
                    series_count += 1
                    values = serie.get("data", []) if isinstance(serie, dict) else []
                    if isinstance(values, list):
                        points_dropped += len(values)
        title = group.get("title") if isinstance(group, dict) else None
        return {
            "kind": "chart",
            "source": key,
            "title": title,
            "series_count": series_count,
            "points_dropped": points_dropped,
        }
    if "logs" in widget:
        logs = widget.get("logs", {})
        check = logs.get("check", {}) if isinstance(logs, dict) else {}
        summary = {
            k: check.get(k)
            for k in ("id", "title", "status", "message")
            if isinstance(check, dict) and k in check
        }
        app_id = logs.get("application_id") if isinstance(logs, dict) else None
        return {"kind": "logs", "application_id": app_id, "check": summary}
    if "profiling" in widget or "tracing" in widget:
        key = "profiling" if "profiling" in widget else "tracing"
        inner = widget.get(key, {})
        app_id = inner.get("application_id") if isinstance(inner, dict) else None
        return {
            "kind": key,
            "application_id": app_id,
            "detail": (
                f"use get_application_{key}(project_id, app_id) for the full payload"
            ),
        }
    return {"kind": "other", "keys": sorted(widget.keys())}


def summarize_application(
    application: dict[str, Any],
    max_table_rows: int = 5,
    max_nodes: int = 100,
) -> dict[str, Any]:
    """Project an application-detail payload into a bounded summary."""
    _check_caps(max_table_rows=max_table_rows, max_nodes=max_nodes)
    context = application.get("context", {}) if isinstance(application, dict) else {}
    if not isinstance(context, dict):
        context = {}
    status = context.get("status", {})
    data = application.get("data", {}) if isinstance(application, dict) else {}
    if not isinstance(data, dict):
        data = {}
    app_map = data.get("app_map", {})
    if not isinstance(app_map, dict):
        app_map = {}
    ordered: list[tuple[str, Any]] = []
    for key in ("application", "instances", "clients", "dependencies"):
        value = app_map.get(key, [])
        if isinstance(value, dict):
            items: list[Any] = [value]
        elif isinstance(value, list):
            items = value
        else:
            items = []
        for item in items:
            ordered.append((key, item))
    malformed_nodes = sum(1 for _, item in ordered if not isinstance(item, dict))
    dict_items = [(kind, item) for kind, item in ordered if isinstance(item, dict)]
    sliced = dict_items[:max_nodes]
    kept = [_summarize_node(node) for _, node in sliced]
    kinds = [kind for kind, _ in sliced]
    # Identity list: every client/dependency id is kept regardless of the
    # node cap, so dependency_ids is complete even when nodes truncate.
    dependency_ids = [
        node.get("id")
        for kind, node in dict_items
        if kind in ("clients", "dependencies") and isinstance(node.get("id"), str)
    ]
    reports = data.get("reports", [])
    if not isinstance(reports, list):
        reports = []
    malformed_reports = sum(1 for report in reports if not isinstance(report, dict))
    report_rows = []
    points_dropped = 0
    rows_dropped = 0
    for report in reports:
        if not isinstance(report, dict):
            continue
        widgets = report.get("widgets", []) or []
        checks = report.get("checks", []) or []
        summarized = [
            _summarize_widget(widget, max_table_rows)
            for widget in widgets
            if isinstance(widget, dict)
        ]
        for widget_summary in summarized:
            points_dropped += widget_summary.get("points_dropped", 0)
            rows_dropped += widget_summary.get("rows_truncated", 0)
        report_rows.append(
            {
                "name": report.get("name"),
                "status": report.get("status"),
                "checks": [
                    {
                        k: check.get(k)
                        for k in ("id", "title", "status", "message")
                        if k in check
                    }
                    for check in checks
                    if isinstance(check, dict)
                ],
                "widgets": summarized,
            }
        )
    total_nodes = len(ordered)
    nodes_truncated = max(0, len(dict_items) - len(kept))
    directory_total = _directory_total(
        application if isinstance(application, dict) else {}
    )
    categories = data.get("categories", app_map.get("categories", []))
    return {
        "projected": True,
        "limits": {"max_table_rows": max_table_rows, "max_nodes": max_nodes},
        "counts": {
            "nodes_returned": len(kept),
            "nodes_truncated": nodes_truncated,
            "nodes_malformed": malformed_nodes,
            "nodes_total": total_nodes,
            "dependencies_total": len(
                [1 for kind, _ in ordered if kind == "dependencies"]
            ),
            "clients_total": len([1 for kind, _ in ordered if kind == "clients"]),
            "directory_returned": 0,
            "directory_truncated": 0,
            "directory_dropped": directory_total,
            "directory_total": directory_total,
            "reports_returned": len(report_rows),
            "reports_malformed": malformed_reports,
            "reports_total": len(reports),
        },
        "context_status": status,
        "categories": categories,
        "node_kinds": kinds,
        "nodes": kept,
        "dependency_ids": dependency_ids,
        "unbounded": ["dependency_ids"],
        "reports": report_rows,
        "dropped": {
            "directory_ids": directory_total,
            "chart_points": points_dropped,
            "table_rows": rows_dropped,
        },
        "detail": {
            "how": (
                "call get_application(project_id, app_id) with summary=False "
                "for the full payload; chart series and dropped table rows "
                "live only there"
            ),
        },
    }
