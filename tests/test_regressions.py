"""Tests for behaviour that mutation testing showed nothing else caught.

Each of these corresponds to a deliberate bug that the rest of the suite let
through: a wrong unit on a query parameter, a dropped filter, a login race, a
write body nobody inspected.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx2 as httpx
import pytest

from mcp_coroot.client import CorootClient
from mcp_coroot.client.base import Transport
from mcp_coroot.client.errors import (
    CorootAuthenticationError,
    CorootConnectionError,
    CorootServerError,
)
from mcp_coroot.config import SESSION_COOKIE_NAME, Settings
from tests.conftest import FakeCoroot


def query(fake: FakeCoroot) -> dict[str, str]:
    return dict(fake.last.url.params)


# -- request parameters ------------------------------------------------------


async def test_series_sends_epoch_seconds_over_a_one_hour_default(
    fake: FakeCoroot, settings: Settings
) -> None:
    # Prometheus takes seconds; sending milliseconds silently matches nothing.
    fake.on("GET", "/api/project/p1/prom/api/v1/series", {"status": "success"})
    async with CorootClient(settings, transport=httpx.MockTransport(fake)) as coroot:
        await coroot.metrics.series("p1", ["up"])
    params = query(fake)
    start, end = int(params["start"]), int(params["end"])
    assert 1_600_000_000 < start < 4_000_000_000, "start must be epoch seconds"
    assert 3_500 <= end - start <= 3_700, "the default window is one hour"


async def test_series_honours_an_explicit_window(
    fake: FakeCoroot, settings: Settings
) -> None:
    fake.on("GET", "/api/project/p1/prom/api/v1/series", {"status": "success"})
    async with CorootClient(settings, transport=httpx.MockTransport(fake)) as coroot:
        await coroot.metrics.series("p1", ["up"], from_="6h")
    params = query(fake)
    assert 21_000 <= int(params["end"]) - int(params["start"]) <= 22_000


async def test_label_values_forwards_the_match_selector(
    fake: FakeCoroot, settings: Settings
) -> None:
    # The selector is list_metrics' only filter.
    fake.on(
        "GET",
        "/api/project/p1/prom/api/v1/label/__name__/values",
        {"status": "success", "data": ["up"]},
    )
    async with CorootClient(settings, transport=httpx.MockTransport(fake)) as coroot:
        await coroot.metrics.label_values(
            "p1", "__name__", match=['{__name__=~"redis.*"}'], from_="1h", to="now"
        )
    assert fake.last.url.params.get_list("match[]") == ['{__name__=~"redis.*"}']
    assert "start" in query(fake) and "end" in query(fake)


async def test_query_range_sends_the_configured_key_and_window(
    fake: FakeCoroot,
) -> None:
    fake.on("GET", "/api/v1/query_range", {"status": "success"})
    settings = Settings(base_url="http://coroot.test", api_key=fake.api_key)
    async with CorootClient(settings, transport=httpx.MockTransport(fake)) as coroot:
        await coroot.metrics.query_range("up", from_="30m", step="15s")
    assert fake.last.headers["X-API-Key"] == fake.api_key
    params = query(fake)
    assert params["step"] == "15s"
    assert 1_750 <= float(params["end"]) - float(params["start"]) <= 1_850


async def test_log_severities_are_normalised(
    fake: FakeCoroot, settings: Settings
) -> None:
    # Coroot matches severity values case-sensitively.
    from mcp_coroot.server.tools.telemetry import _log_filters

    filters = _log_filters(["ERROR", " Warning "], None, None)
    assert filters == [
        {"name": "Severity", "op": "=", "value": "error"},
        {"name": "Severity", "op": "=", "value": "warning"},
    ]


async def test_list_alerts_asks_for_resolved_only_when_needed(
    fake: FakeCoroot, settings: Settings
) -> None:
    calls: list[str] = []

    def alerts(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.params.get("include_resolved", ""))
        return httpx.Response(
            200,
            json={
                "context": {"status": {}, "search": {}},
                "data": {"alerts": [], "total": 0, "firing": 0, "resolved": 0},
            },
        )

    fake.on("GET", "/api/user", {"projects": [{"id": "p1", "name": "prod"}]})
    fake.handle("GET", "/api/project/p1/alerts", alerts)
    async with CorootClient(settings, transport=httpx.MockTransport(fake)) as coroot:
        await coroot.alerts.list("p1", include_resolved=False)
        await coroot.alerts.list("p1", include_resolved=True)
    assert calls == ["false", "true"]


# -- write bodies ------------------------------------------------------------


async def test_telemetry_service_links_hit_their_own_endpoint(
    fake: FakeCoroot, settings: Settings
) -> None:
    base = "/api/project/p1/app/p1%3Ans%3ADeployment%3Aapi"
    for kind, setter in (
        ("profiling", "set_profiling_service"),
        ("tracing", "set_tracing_service"),
        ("logs", "set_logs_service"),
    ):
        one = FakeCoroot()
        one.on("POST", f"{base}/{kind}")
        async with CorootClient(settings, transport=httpx.MockTransport(one)) as coroot:
            await getattr(coroot.applications, setter)("p1", "ns:Deployment:api", "svc")
        assert one.last_path == f"{base}/{kind}"
        assert one.body(one.last) == {"service": "svc"}


async def test_create_user_sends_the_requested_role(
    fake: FakeCoroot, settings: Settings
) -> None:
    fake.on("POST", "/api/users")
    async with CorootClient(settings, transport=httpx.MockTransport(fake)) as coroot:
        await coroot.users.create(
            email="viewer@example.com", name="Viewer", role="Viewer", password="pw"
        )
    assert fake.body(fake.last) == {
        "action": "create",
        "email": "viewer@example.com",
        "name": "Viewer",
        "role": "Viewer",
        "password": "pw",
    }


async def test_alerting_rule_update_sends_the_whole_rule(
    fake: FakeCoroot, settings: Settings
) -> None:
    rule = {"name": "cpu", "severity": "critical", "enabled": False, "for": "5m"}
    fake.on("PUT", "/api/project/p1/alerting-rules/r1", {"id": "r1", **rule})
    async with CorootClient(settings, transport=httpx.MockTransport(fake)) as coroot:
        await coroot.alerting_rules.update("p1", "r1", rule)
    assert fake.body(fake.last) == rule


async def test_alert_state_changes_hit_their_own_endpoint(
    fake: FakeCoroot, settings: Settings
) -> None:
    for action, method in (
        ("resolve", "resolve"),
        ("suppress", "suppress"),
        ("reopen", "reopen"),
    ):
        one = FakeCoroot()
        one.on("POST", f"/api/project/p1/alerts/{action}", status=204)
        async with CorootClient(settings, transport=httpx.MockTransport(one)) as coroot:
            await getattr(coroot.alerts, method)("p1", ["a1"])
        assert one.last_path == f"/api/project/p1/alerts/{action}"
        assert one.body(one.last) == {"ids": ["a1"]}


# -- authentication ----------------------------------------------------------


async def test_concurrent_requests_log_in_once(
    fake: FakeCoroot, settings: Settings
) -> None:
    # The handler must actually suspend, or the event loop runs each request to
    # completion in turn and the race the lock exists for never happens.
    fake.on("GET", "/api/user", {"email": "admin"})

    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0)
        return fake(request)

    transport = Transport(settings, transport=httpx.MockTransport(slow))
    try:
        await asyncio.gather(*(transport.get("/api/user") for _ in range(8)))
    finally:
        await transport.aclose()
    assert len(fake.calls("POST", "/api/login")) == 1


async def test_login_without_a_cookie_is_an_error(fake: FakeCoroot) -> None:
    # A proxy that strips Set-Cookie must not look like a successful login.
    fake.on("POST", "/api/login")
    settings = Settings(base_url="http://coroot.test", username="admin", password="x")
    transport = Transport(settings, transport=httpx.MockTransport(fake))
    try:
        with pytest.raises(CorootAuthenticationError, match="session cookie"):
            await transport.login()
    finally:
        await transport.aclose()


async def test_login_server_error_is_not_reported_as_bad_credentials(
    fake: FakeCoroot,
) -> None:
    fake.on("POST", "/api/login", status=500, text="database is down")
    settings = Settings(base_url="http://coroot.test", username="admin", password="x")
    transport = Transport(settings, transport=httpx.MockTransport(fake))
    try:
        with pytest.raises(CorootServerError, match="database is down"):
            await transport.login()
    finally:
        await transport.aclose()


async def test_a_session_rejected_after_relogin_does_not_loop(
    fake: FakeCoroot, settings: Settings
) -> None:
    # The cookie is refused even after a fresh login: this must raise rather
    # than retry forever.
    fake.on("GET", "/api/user", {"email": "admin"})
    fake.session_cookie = "never-accepted"

    def login(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"set-cookie": f"{SESSION_COOKIE_NAME}=stale; Path=/"},
        )

    fake.handle("POST", "/api/login", login)
    transport = Transport(settings, transport=httpx.MockTransport(fake))
    try:
        with pytest.raises(CorootAuthenticationError):
            await transport.get("/api/user")
    finally:
        await transport.aclose()
    assert len(fake.calls("POST", "/api/login")) == 2


async def test_network_failure_after_a_successful_login(
    fake: FakeCoroot, settings: Settings
) -> None:
    calls = {"n": 0}

    def flaky(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if request.url.path == "/api/login":
            return fake(request)
        raise httpx.ConnectError("connection reset", request=request)

    transport = Transport(settings, transport=httpx.MockTransport(flaky))
    try:
        with pytest.raises(CorootConnectionError, match="Could not reach"):
            await transport.get("/api/user")
    finally:
        await transport.aclose()


# -- identifiers -------------------------------------------------------------


async def test_ids_needing_encoding_survive_the_round_trip(
    fake: FakeCoroot, settings: Settings
) -> None:
    # Coroot query-unescapes {app}, so a literal '+' must arrive as %2B.
    app_id = "p1:ns:Deployment:api+canary"
    encoded = "p1%3Ans%3ADeployment%3Aapi%2Bcanary"
    fake.on(
        "GET",
        f"/api/project/p1/app/{encoded}",
        {"context": {"status": {}, "search": {}}, "data": {"reports": []}},
    )
    async with CorootClient(settings, transport=httpx.MockTransport(fake)) as coroot:
        await coroot.applications.get("p1", app_id)
    assert fake.last_path == f"/api/project/p1/app/{encoded}"


async def test_non_ascii_ids_are_encoded(fake: FakeCoroot, settings: Settings) -> None:
    fake.on(
        "GET",
        "/api/project/p1/node/n%C3%B8de-1",
        {"context": {"status": {}, "search": {}}, "data": {"name": "Node"}},
    )
    async with CorootClient(settings, transport=httpx.MockTransport(fake)) as coroot:
        await coroot.nodes.get("p1", "nøde-1")
    assert fake.last_path == "/api/project/p1/node/n%C3%B8de-1"


async def test_project_ids_are_encoded(fake: FakeCoroot, settings: Settings) -> None:
    fake.on("GET", "/api/project/a%2Fb/status", {"context": {}, "data": {}})
    async with CorootClient(settings, transport=httpx.MockTransport(fake)) as coroot:
        await coroot.projects.status("a/b")
    assert fake.last_path == "/api/project/a%2Fb/status"


# -- caching and ordering ----------------------------------------------------


async def test_status_counts_are_ordered_by_volume() -> None:
    from mcp_coroot.server.compact import status_counts

    counts = status_counts(
        [{"status": "ok"}, {"status": "warning"}, {"status": "warning"}]
    )
    assert list(counts) == ["warning", "ok"]


async def test_unknown_project_zero_envelope_is_handled(
    fake: FakeCoroot, settings: Settings
) -> None:
    # Coroot answers world-loading routes for an unknown project with a zero
    # envelope: null search lists, null incident and alert maps.
    zero: dict[str, Any] = {
        "context": {
            "status": {"status": "unknown"},
            "search": {"applications": None, "nodes": None},
            "incidents": None,
            "alerts": None,
        },
        "data": None,
    }
    fake.on("GET", "/api/project/ghost/status", zero)
    fake.on("GET", "/api/project/ghost/overview/applications", zero)
    async with CorootClient(settings, transport=httpx.MockTransport(fake)) as coroot:
        status = await coroot.projects.status("ghost")
        assert status.known_applications == []
        assert status.known_nodes == []
        apps = await coroot.overview.applications("ghost")
    assert apps.data is None


def test_long_strings_are_cut_at_two_thousand_characters() -> None:
    from mcp_coroot.server.compact import compact

    result = compact({"m": "x" * 2_500})
    assert result["m"].startswith("x" * 2_000)
    assert "500 chars truncated" in result["m"]


def test_fit_returns_a_payload_that_is_exactly_at_budget() -> None:
    from mcp_coroot.server.compact import encoded_size, fit

    payload = {"a": "x" * 100}
    size = encoded_size(payload)
    assert fit(payload, size) is payload


def test_presentation_keys_are_dropped() -> None:
    # Spelled out rather than imported: importing the set under test would let a
    # mutation that shrinks it pass.
    from mcp_coroot.server.compact import compact

    payload: dict[str, Any] = {
        "keep": 1,
        "color": "red",
        "color_shift": 1,
        "column": 2,
        "featured": True,
        "hide_legend": True,
        "sorted": True,
        "stacked": True,
        "drill_down_link": "/x",
        "link": "/y",
        "doc_link": "/z",
        "width": "100%",
        "icon": "postgres",
        "condition_format_template": "{}",
    }
    assert compact(payload) == {"keep": 1}


async def test_health_probe_reports_an_unreachable_coroot(fake: FakeCoroot) -> None:
    fake.on("GET", "/health", status=503, text="unavailable")
    settings = Settings(base_url="http://coroot.test", username="a", password="b")
    async with CorootClient(settings, transport=httpx.MockTransport(fake)) as coroot:
        assert await coroot.system.health() is False


async def test_project_list_is_cached_between_calls(
    fake: FakeCoroot, settings: Settings
) -> None:
    from mcp_coroot.server.state import AppState

    fake.on("GET", "/api/user", {"projects": [{"id": "p1", "name": "prod"}]})
    async with CorootClient(settings, transport=httpx.MockTransport(fake)) as coroot:
        state = AppState(settings=settings, coroot=coroot)
        await state.project_choices()
        await state.project_choices()
        assert len(fake.calls("GET", "/api/user")) == 1
        await state.project_choices(refresh=True)
    assert len(fake.calls("GET", "/api/user")) == 2


async def test_unknown_dashboard_is_an_error_not_an_empty_success(
    fake: FakeCoroot, settings: Settings
) -> None:
    from mcp_coroot.client.errors import CorootNotFoundError

    fake.on(
        "GET",
        "/api/project/p1/dashboards/ghost",
        {"context": {"status": {}, "search": {}}, "data": None},
    )
    async with CorootClient(settings, transport=httpx.MockTransport(fake)) as coroot:
        with pytest.raises(CorootNotFoundError, match="Dashboard not found"):
            await coroot.dashboards.get("p1", "ghost")


def test_build_panel_uses_the_display_it_is_given() -> None:
    from mcp_coroot.client.dashboards import build_panel, metrics_query

    line = build_panel([metrics_query("up")])
    assert line["widget"]["chart"] == {"display": "line", "stacked": False}
    bars = build_panel([metrics_query("up")], display="bar", stacked=True)
    assert bars["widget"]["chart"] == {"display": "bar", "stacked": True}


def test_enum_validation_tolerates_surrounding_whitespace() -> None:
    from mcp_coroot.server.errors import one_of

    assert one_of("  CPUContainer  ", ("CPUContainer",), name="check_id") == (
        "CPUContainer"
    )


async def test_incident_resolved_at_zero_counts_as_resolved(
    fake: FakeCoroot, settings: Settings
) -> None:
    # Coroot encodes "never resolved" as 0, not null.
    from mcp_coroot.server.tools.incidents import _incident_digest

    assert _incident_digest({"resolved_at": 0})["open"] is True
    assert _incident_digest({"resolved_at": None})["open"] is True
    assert _incident_digest({"resolved_at": 1704067200000})["open"] is False


def test_alert_digest_reports_suppression_and_who_resolved_it() -> None:
    from mcp_coroot.server.tools.incidents import _alert_digest

    suppressed = _alert_digest({"id": "a1", "resolved_at": 0, "suppressed": True})
    assert suppressed["suppressed"] is True
    assert suppressed["firing"] is False
    by_hand = _alert_digest(
        {"id": "a2", "resolved_at": 0, "manually_resolved_at": 1, "resolved_by": "sre"}
    )
    assert by_hand["resolved_by"] == "sre"
    assert by_hand["firing"] is False


def test_log_entry_keeps_its_trace_id() -> None:
    from mcp_coroot.server.tools.telemetry import _entry_digest

    entry = _entry_digest(
        {"timestamp": 1704067200000, "severity": "error", "trace_id": "abc123"}
    )
    assert entry["trace_id"] == "abc123"
    assert _entry_digest({"trace_id": ""})["trace_id"] is None


async def test_health_probe_reports_a_non_ok_answer(fake: FakeCoroot) -> None:
    # A redirect does not raise, so this is the path a "return True regardless"
    # bug would slip through.
    fake.on("GET", "/health", status=302, headers={"location": "/login"})
    settings = Settings(base_url="http://coroot.test", username="a", password="b")
    async with CorootClient(settings, transport=httpx.MockTransport(fake)) as coroot:
        assert await coroot.system.health() is False


async def test_incident_app_filter_normalises_the_id(
    fake: FakeCoroot, settings: Settings
) -> None:
    from mcp_coroot.server.tools import incidents as incidents_tools

    assert incidents_tools is not None  # imported for the module under test
    fake.on("GET", "/api/user", {"projects": [{"id": "p1", "name": "prod"}]})
    fake.on(
        "GET",
        "/api/project/p1/incidents",
        {
            "context": {"status": {}, "search": {}},
            "data": [
                {
                    "key": "inc1",
                    "application_id": "p1:ns:Deployment:api",
                    "resolved_at": None,
                }
            ],
        },
    )
    from mcp import Client

    from mcp_coroot.server import build_server
    from tests.conftest import ALL_TOOLSETS

    full = Settings(
        base_url="http://coroot.test",
        username="admin",
        password="secret",
        toolsets=ALL_TOOLSETS,
    )
    server = build_server(
        full,
        client_factory=lambda s: CorootClient(s, transport=httpx.MockTransport(fake)),
    )
    async with Client(server) as client:
        # A three-part id must still match the four-part id Coroot returns.
        result = await client.call_tool(
            "get_incidents", {"app_id": "ns:Deployment:api"}
        )
    assert result.is_error is False
    assert isinstance(result.structured_content, dict)
    assert [i["key"] for i in result.structured_content["incidents"]] == ["inc1"]
