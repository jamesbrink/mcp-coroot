"""Tests for response compaction."""

from __future__ import annotations

from typing import Any

from mcp_coroot.server.compact import (
    chart_summary,
    compact,
    encoded_size,
    fit,
    flamegraph_summary,
    limit_items,
    series_summary,
    status_counts,
)


def test_series_summary() -> None:
    assert series_summary([1, 2, None, 3]) == {
        "points": 4,
        "last": 3.0,
        "min": 1.0,
        "max": 3.0,
        "avg": 2.0,
    }
    assert series_summary([]) is None
    assert series_summary(None) is None
    assert series_summary([None, None]) == {"points": 2, "values": None}


def test_chart_summary_keeps_signal() -> None:
    chart = {
        "title": "CPU",
        "ctx": {"from": 1, "to": 2, "step": 30, "raw_step": 15},
        "series": [{"name": "api", "data": [0.1, 0.9], "color": "red"}],
        "threshold": 0.8,
        "featured": True,
    }
    summary = chart_summary(chart)
    assert summary["title"] == "CPU"
    assert summary["window"] == {"from": 1, "to": 2, "step": 30}
    assert summary["series"][0]["max"] == 0.9
    assert summary["threshold"] == 0.8
    assert chart_summary("not-a-chart") == "not-a-chart"
    assert chart_summary({}) is None


def test_flamegraph_summary() -> None:
    graph = {
        "name": "root",
        "total": 100,
        "children": [
            {"name": "a", "total": 70, "children": [{"name": "a1", "total": 70}]},
            {"name": "b", "total": 30},
        ],
    }
    summary = flamegraph_summary(graph, top=1)
    assert summary["total"] == 100
    assert summary["hottest"] == [{"name": "a1", "value": 70.0}]
    assert summary["leaves"] == 2


def test_compact_drops_noise_and_summarises_charts() -> None:
    payload = {
        "name": "SLO",
        "status": "warning",
        "icon": "postgres",
        "widgets": [
            {"chart": {"series": [{"name": "p99", "data": [1, 2, 3]}]}, "width": "100%"}
        ],
        "empty": None,
    }
    result = compact(payload)
    assert result["name"] == "SLO"
    assert "icon" not in result
    assert "empty" not in result
    widget = result["widgets"][0]
    assert "width" not in widget
    assert widget["chart"]["series"][0]["avg"] == 2.0


def test_compact_truncates_long_strings_and_deep_nesting() -> None:
    long_text = "x" * 5000
    assert "truncated" in compact({"m": long_text})["m"]
    deep: dict[str, Any] = {"v": 1}
    for _ in range(20):
        deep = {"child": deep}
    assert "too deep" in str(compact(deep))


def test_fit_returns_small_payloads_untouched() -> None:
    payload = {"items": [1, 2, 3]}
    assert fit(payload, 10_000) is payload


def test_fit_truncates_lists_and_notes_it() -> None:
    payload = {"items": [{"name": f"app-{i}", "detail": "y" * 200} for i in range(500)]}
    result = fit(payload, 5_000)
    assert encoded_size(result) <= 5_000
    assert "truncated" in result
    assert "more items omitted" in str(result["items"][-1])


def test_fit_shrinks_long_strings() -> None:
    result = fit({"blob": "z" * 50_000}, 2_000)
    assert encoded_size(result) <= 2_000
    assert result["blob"].endswith("...")
    assert "truncated" in result


def test_fit_gives_up_when_shape_cannot_shrink() -> None:
    # Wide dictionaries have nothing to truncate: keys are never dropped.
    payload = {f"key-{i}": i for i in range(5_000)}
    result = fit(payload, 2_000)
    assert "could not be reduced" in result["truncated"]
    assert result["keys"][0] == "key-0"


def test_status_counts_and_limit_items() -> None:
    apps = [
        {"status": "ok"},
        {"status": "warning"},
        {"status": "warning"},
        {"status": {"status": "critical"}},
        "junk",
    ]
    assert status_counts(apps) == {"warning": 2, "critical": 1, "ok": 1}
    kept, omitted = limit_items([1, 2, 3, 4], 2)
    assert (kept, omitted) == ([1, 2], 2)
    assert limit_items([1, 2], 5) == ([1, 2], 0)
    assert limit_items([1, 2], 0) == ([1, 2], 0)
