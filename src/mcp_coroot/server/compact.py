"""Shape Coroot payloads so they fit an LLM context window.

Coroot's UI endpoints return everything needed to draw a page: chart series with
hundreds of samples, widget trees, flame graphs. A single traces or profiling
response can exceed a hundred thousand tokens. These helpers keep the signal
(names, statuses, quantiles, last/min/max values) and drop the pixels, then
enforce a hard character budget as a final safety net.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from typing import Any

#: Keys whose values are chart payloads; replaced by a statistical summary.
CHART_KEYS = frozenset({"chart", "heatmap"})

#: Keys holding a ``{"title", "charts": [...]}`` group of charts.
CHART_GROUP_KEYS = frozenset({"chart_group"})

#: Keys that are pure presentation and are dropped outright.
NOISE_KEYS = frozenset(
    {
        "color",
        "color_shift",
        "column",
        "featured",
        "hide_legend",
        "sorted",
        "stacked",
        "drill_down_link",
        "link",
        "doc_link",
        "width",
        "icon",
        "condition_format_template",
    }
)

MAX_STRING = 2_000

#: Keys never truncated by :func:`fit`. They are small, and they carry either the
#: answer or the means to ask a better question.
PROTECTED_KEYS = frozenset(
    {
        "failing_checks",
        "report_names",
        "available_profiles",
        "truncated",
        "note",
        "message",
        "error",
        "totals",
        "by_status",
        "by_severity",
    }
)

#: Marks an already-summarised chart so a second pass leaves it alone.
CHART_NOTE = "chart data summarised; use get_metrics for raw samples"


def _numbers(values: Iterable[Any]) -> list[float]:
    return [float(v) for v in values if isinstance(v, int | float)]


def series_summary(data: Sequence[Any] | None) -> dict[str, Any] | None:
    """Summarise one time series as count/last/min/max/avg."""
    if not data:
        return None
    numbers = _numbers(data)
    if not numbers:
        # Every sample is null: the target reported no data for the window,
        # which is usually the thing the user is looking for.
        return {"points": len(data), "values": "all null (no data in window)"}
    last = next((v for v in reversed(numbers)), None)
    return {
        "points": len(data),
        "last": round(last, 6) if last is not None else None,
        "min": round(min(numbers), 6),
        "max": round(max(numbers), 6),
        "avg": round(sum(numbers) / len(numbers), 6),
    }


#: Keys a real Coroot Chart carries. A dict under a chart key with none of them
#: is something else (a dashboard panel's display config, say) and is left alone.
_CHART_FIELDS = frozenset({"ctx", "series", "title", "threshold", "annotations"})


def chart_summary(chart: Any) -> Any:
    """Replace a Coroot chart with per-series statistics.

    Idempotent: summarising an already-summarised chart returns it unchanged, so
    nested payloads can be compacted more than once safely.

    A bare list of numbers is a ``timeseries.TimeSeries``, which Coroot also
    serialises under ``chart`` (table-cell sparklines, overview parameters), and
    is summarised the same way.
    """
    if isinstance(chart, list):
        return series_summary(chart)
    if not isinstance(chart, dict):
        return chart
    if chart.get("note") == CHART_NOTE:
        return chart
    if not _CHART_FIELDS & set(chart):
        # Not a chart: a dashboard panel's {"display", "stacked"}, for instance.
        return compact(chart)
    summary: dict[str, Any] = {}
    if title := chart.get("title"):
        summary["title"] = title
    ctx = chart.get("ctx")
    if isinstance(ctx, dict):
        summary["window"] = {
            k: ctx.get(k) for k in ("from", "to", "step") if ctx.get(k) is not None
        }
    series = chart.get("series")
    if isinstance(series, list):
        summary["series"] = [
            {
                "name": item.get("name"),
                **(series_summary(item.get("data")) or {}),
            }
            for item in series
            if isinstance(item, dict)
        ]
    if (threshold := chart.get("threshold")) is not None:
        summary["threshold"] = threshold
    if not summary:
        return None
    summary["note"] = CHART_NOTE
    return summary


def chart_group_summary(group: Any) -> Any:
    """Summarise a Coroot chart group, keeping every chart inside it.

    A ``ChartGroup`` is ``{"title": str, "charts": [Chart]}``. Treating it like a
    single chart would drop every series it holds, which is most of the data in
    an audit report.
    """
    if not isinstance(group, dict):
        return group
    charts = group.get("charts")
    if not isinstance(charts, list):
        return chart_summary(group)
    summary: dict[str, Any] = {}
    if title := group.get("title"):
        summary["title"] = title
    summarised = [chart_summary(chart) for chart in charts]
    summary["charts"] = [chart for chart in summarised if chart is not None]
    return summary or None


def flamegraph_summary(node: Any, *, top: int = 15) -> Any:
    """Reduce a flame graph to its heaviest leaves.

    Idempotent, like :func:`chart_summary`.
    """
    if not isinstance(node, dict):
        return node
    if "hottest" in node and "leaves" in node:
        return node
    leaves: list[tuple[float, str]] = []

    def walk(current: dict[str, Any], depth: int) -> None:
        if depth > 32:
            return
        children = current.get("children")
        name = str(current.get("name", ""))
        value = current.get("total") or current.get("value") or 0
        if isinstance(children, list) and children:
            for child in children:
                if isinstance(child, dict):
                    walk(child, depth + 1)
        elif isinstance(value, int | float) and name:
            leaves.append((float(value), name))

    walk(node, 0)
    leaves.sort(reverse=True)
    total = node.get("total") or node.get("value")
    return {
        "total": total,
        "hottest": [{"name": name, "value": value} for value, name in leaves[:top]],
        "leaves": len(leaves),
        "note": f"flame graph reduced to its {top} heaviest leaves",
    }


def compact(value: Any, *, depth: int = 0, max_depth: int = 12) -> Any:
    """Recursively summarise charts and drop presentation-only keys."""
    if depth >= max_depth:
        return "<truncated: nesting too deep>"
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if key in NOISE_KEYS or item is None:
                continue
            if key == "flamegraph":
                summarised = flamegraph_summary(item)
            elif key in CHART_GROUP_KEYS:
                summarised = (
                    [chart_group_summary(g) for g in item]
                    if isinstance(item, list)
                    else chart_group_summary(item)
                )
            elif key in CHART_KEYS:
                summarised = chart_summary(item)
            else:
                summarised = compact(item, depth=depth + 1, max_depth=max_depth)
            if summarised is not None:
                result[key] = summarised
        return result or None
    if isinstance(value, list):
        # Keep a placeholder for items that compact to nothing, so a count taken
        # before compaction still matches the list that comes back.
        items: list[Any] = []
        for item in value:
            compacted = compact(item, depth=depth + 1, max_depth=max_depth)
            if compacted is None and isinstance(item, dict):
                compacted = {}
            elif compacted is None and isinstance(item, list):
                compacted = []
            if compacted is not None:
                items.append(compacted)
        return items
    if isinstance(value, str) and len(value) > MAX_STRING:
        return value[:MAX_STRING] + f"... <{len(value) - MAX_STRING} chars truncated>"
    return value


def compact_dict(value: Any) -> dict[str, Any]:
    """Compact a mapping, returning ``{}`` where :func:`compact` would return None.

    ``compact`` drops keys whose value is None, so a mapping that compacts to
    nothing becomes None. Callers that go on to index the result need a dict.
    """
    result = compact(value)
    return result if isinstance(result, dict) else {}


def encoded_size(payload: Any) -> int:
    """Size of ``payload`` once serialised as JSON."""
    return len(json.dumps(payload, default=str))


def _shrink(value: Any, list_limit: int, string_limit: int) -> Any:
    if isinstance(value, dict):
        return {
            k: (v if k in PROTECTED_KEYS else _shrink(v, list_limit, string_limit))
            for k, v in value.items()
        }
    if isinstance(value, list):
        kept = [_shrink(v, list_limit, string_limit) for v in value[:list_limit]]
        dropped = len(value) - len(kept)
        if dropped > 0:
            kept.append(f"<{dropped} more items omitted>")
        return kept
    if isinstance(value, str) and len(value) > string_limit:
        return value[:string_limit] + "..."
    return value


def fit(payload: dict[str, Any], max_chars: int) -> dict[str, Any]:
    """Shrink ``payload`` until its JSON encoding fits ``max_chars``.

    Lists are truncated before strings, and the result records what happened in
    ``truncated`` so the model knows to narrow its query instead of assuming it
    saw everything.
    """
    if encoded_size(payload) <= max_chars:
        return payload
    for list_limit, string_limit in (
        (200, 2_000),
        (100, 1_000),
        (50, 500),
        (20, 300),
        (10, 200),
        (5, 120),
        (2, 80),
    ):
        shrunk: dict[str, Any] = dict(_shrink(payload, list_limit, string_limit))
        shrunk["truncated"] = (
            f"Response exceeded {max_chars} characters. Lists were cut to "
            f"{list_limit} items. Narrow the time range or use a smaller limit."
        )
        if encoded_size(shrunk) <= max_chars:
            return shrunk
    # Nothing left to truncate: the payload is wide rather than deep. Report the
    # shape instead of the data, and keep even that inside the budget.
    note = (
        f"Response could not be reduced below {max_chars} characters. "
        "Query a narrower time range, a single application, or a smaller limit."
    )
    keys = sorted(payload)
    shown: list[str] = []
    for key in keys:
        # Measure the encoded result rather than estimating it: a non-ASCII key
        # is six characters per character once json.dumps escapes it.
        candidate = [*shown, key]
        probe = {
            "truncated": note,
            "keys": candidate,
            "keys_omitted": len(keys) - len(candidate),
        }
        if encoded_size(probe) > max_chars:
            break
        shown = candidate
    return {
        "truncated": note,
        "keys": shown,
        "keys_omitted": len(keys) - len(shown),
    }


def status_counts(items: Iterable[Any], key: str = "status") -> dict[str, int]:
    """Count how many items sit at each Coroot status."""
    counts: dict[str, int] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        value = item.get(key)
        if isinstance(value, dict):
            value = value.get("status")
        if isinstance(value, str):
            counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])))


def limit_items(items: Sequence[Any], limit: int) -> tuple[list[Any], int]:
    """Return ``(kept, omitted)`` for a sequence."""
    if limit <= 0 or len(items) <= limit:
        return list(items), 0
    return list(items[:limit]), len(items) - limit
