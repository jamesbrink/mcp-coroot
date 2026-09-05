"""Tests for response compaction."""

from __future__ import annotations

from typing import Any

from mcp_coroot.server.compact import (
    chart_group_summary,
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
    # An all-null series means the target reported nothing, which is signal.
    assert series_summary([None, None]) == {
        "points": 2,
        "values": "all null (no data in window)",
    }


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
    # Wide dictionaries have nothing to truncate: keys are never dropped. The
    # budget must still hold, so the fallback reports only as many keys as fit.
    payload = {f"key-{i}": i for i in range(5_000)}
    result = fit(payload, 2_000)
    assert "could not be reduced" in result["truncated"]
    assert encoded_size(result) <= 2_000
    assert result["keys"][0] == "key-0"
    assert result["keys_omitted"] > 0
    assert len(result["keys"]) + result["keys_omitted"] == 5_000


def test_fit_holds_the_budget_for_every_shape() -> None:
    budget = 1_500
    # Non-ASCII keys encode to six characters each, so estimating is not enough.
    shapes: list[dict[str, Any]] = [
        {"items": [{"name": "x" * 100} for _ in range(500)]},
        {"blob": "z" * 100_000},
        {f"k{i}": {"nested": ["v"] * 50} for i in range(300)},
        {"mixed": [{"a": "b" * 500}] * 50, "other": "c" * 5_000},
        {f"\u30ad\u30fc{i}" * 5: i for i in range(400)},
    ]
    for shape in shapes:
        assert encoded_size(fit(shape, budget)) <= budget


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


def test_chart_group_keeps_every_chart() -> None:
    # Coroot's audit reports are built mostly from chart groups, which are
    # {"title", "charts": [Chart]} rather than charts themselves.
    group = {
        "title": "CPU usage by instance, cores",
        "charts": [
            {"title": "api-1", "series": [{"name": "usage", "data": [0.5, 1.5]}]},
            {"title": "api-2", "series": [{"name": "usage", "data": [2.0, 4.0]}]},
        ],
    }
    result = compact({"chart_group": group})
    charts = result["chart_group"]["charts"]
    assert result["chart_group"]["title"] == "CPU usage by instance, cores"
    assert len(charts) == 2
    assert charts[0]["series"][0]["max"] == 1.5
    assert charts[1]["series"][0]["avg"] == 3.0


def test_chart_group_summary_handles_odd_shapes() -> None:
    assert chart_group_summary("not-a-group") == "not-a-group"
    # A group without a charts list falls back to chart handling.
    assert chart_group_summary({"title": "t", "series": []})["title"] == "t"


def test_latency_is_not_treated_as_a_chart() -> None:
    # Coroot's 'latency' is a profile or a status parameter, never a Chart.
    latency = {"type": "::nanoseconds", "flamegraph": {"name": "root", "total": 5}}
    result = compact({"latency": latency})
    assert result["latency"]["type"] == "::nanoseconds"
    assert result["latency"]["flamegraph"]["total"] == 5


def test_list_items_that_compact_to_nothing_are_kept() -> None:
    # Counts are computed before compaction, so the list length must not change.
    items = [{"name": "a"}, {"icon": "dropped-key"}, {"name": "b"}]
    result = compact({"items": items})
    assert len(result["items"]) == 3
    assert result["items"][1] == {}


def test_a_dict_under_chart_that_is_not_a_chart_is_left_alone() -> None:
    # A dashboard panel's widget is {"chart": {"display", "stacked"}}, which is
    # not a Coroot Chart and must not be summarised into nothing.
    result = compact({"widget": {"chart": {"display": "line", "kind": "area"}}})
    assert result["widget"]["chart"] == {"display": "line", "kind": "area"}


def test_bare_series_under_a_chart_key_is_summarised() -> None:
    # timeseries.TimeSeries serialises as a plain array of floats, and Coroot
    # puts one under "chart" in table cells and overview parameters.
    result = compact({"chart": [1.0, 5.0, 3.0]})
    assert result["chart"] == {
        "points": 3,
        "last": 3.0,
        "min": 1.0,
        "max": 5.0,
        "avg": 3.0,
    }


def test_fit_protects_the_fields_that_carry_the_answer() -> None:
    payload = {
        "failing_checks": [
            {"check": f"check-{i}", "status": "critical"} for i in range(30)
        ],
        "report_names": [f"Report{i}" for i in range(11)],
        "reports": [{"name": f"R{i}", "blob": "x" * 400} for i in range(40)],
    }
    result = fit(payload, 6_000)
    assert encoded_size(result) <= 6_000
    # The diagnosis and the means to ask a narrower question both survive.
    assert len(result["failing_checks"]) == 30
    assert len(result["report_names"]) == 11
    assert "more items omitted" in str(result["reports"][-1])
