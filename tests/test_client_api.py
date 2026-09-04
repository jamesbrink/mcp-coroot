"""Tests for the per-domain Coroot API modules."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import unquote

import httpx2 as httpx
import pytest
import pytest_asyncio

from mcp_coroot.client import CorootClient
from mcp_coroot.client.applications import build_trace_param
from mcp_coroot.client.dashboards import build_panel, metrics_query
from mcp_coroot.client.errors import CorootNotFoundError, CorootValidationError
from mcp_coroot.config import Settings
from tests.conftest import FakeCoroot

ENVELOPE_CONTEXT: dict[str, Any] = {
    "status": {"status": "ok"},
    "search": {
        "applications": [{"id": "p1:default:Deployment:api"}],
        "nodes": [{"name": "n1"}],
    },
    "incidents": {"application": 1},
    "alerts": {"critical": 2},
}


def enveloped(data: Any) -> dict[str, Any]:
    return {"context": ENVELOPE_CONTEXT, "data": data}


@pytest_asyncio.fixture
async def coroot(fake: FakeCoroot, settings: Settings) -> Any:
    client = CorootClient(settings, transport=httpx.MockTransport(fake))
    try:
        yield client
    finally:
        await client.aclose()


def query_of(fake: FakeCoroot) -> dict[str, str]:
    return dict(fake.last.url.params)


# -- accounts ---------------------------------------------------------------


async def test_current_user_and_projects(
    coroot: CorootClient, fake: FakeCoroot
) -> None:
    fake.on(
        "GET",
        "/api/user",
        {
            "email": "admin",
            "name": "Admin",
            "role": "Admin",
            "projects": [{"id": "p1", "name": "prod"}, {"id": "p2", "name": "staging"}],
        },
    )
    user = await coroot.auth.current_user()
    assert user["role"] == "Admin"
    projects = await coroot.projects.list()
    assert [p["id"] for p in projects] == ["p1", "p2"]


async def test_change_password(coroot: CorootClient, fake: FakeCoroot) -> None:
    fake.on("POST", "/api/user")
    await coroot.auth.change_password("old", "new")
    assert fake.body(fake.last) == {"old_password": "old", "new_password": "new"}


async def test_user_crud(coroot: CorootClient, fake: FakeCoroot) -> None:
    fake.on("GET", "/api/users", {"users": [{"id": 1}], "roles": ["Admin"]})
    fake.on("POST", "/api/users")
    listing = await coroot.users.list()
    assert listing["roles"] == ["Admin"]
    await coroot.users.create(email="a@b.c", name="A", role="Viewer", password="pw")
    assert fake.body(fake.last)["action"] == "create"
    await coroot.users.update(2, email="a@b.c", name="A", role="Editor")
    body = fake.body(fake.last)
    assert body == {
        "action": "update",
        "id": 2,
        "email": "a@b.c",
        "name": "A",
        "role": "Editor",
        "password": "",
    }
    await coroot.users.delete(2)
    assert fake.body(fake.last) == {"action": "delete", "id": 2}


async def test_system_endpoints(coroot: CorootClient, fake: FakeCoroot) -> None:
    assert await coroot.system.health() is True
    fake.on("GET", "/api/sso", {"roles": ["Admin"], "default_role": "Viewer"})
    assert (await coroot.system.sso())["default_role"] == "Viewer"
    fake.on("GET", "/api/ai", {"provider": ""})
    assert await coroot.system.ai() == {"provider": ""}
    fake.on("GET", "/api/cloud", {"status": "configured"})
    assert (await coroot.system.cloud_status())["status"] == "configured"
    assert query_of(fake) == {"query": "status"}
    fake.on("POST", "/api/cloud")
    await coroot.system.update_cloud(api_key="k", incidents_auto_investigation=True)
    assert fake.body(fake.last)["incidents_auto_investigation"] is True


# -- projects ---------------------------------------------------------------


async def test_project_lifecycle(coroot: CorootClient, fake: FakeCoroot) -> None:
    fake.on("POST", "/api/project/", text="newid123\n")
    assert await coroot.projects.create("prod") == "newid123"
    assert fake.body(fake.last) == {"name": "prod", "member_projects": []}

    fake.on("GET", "/api/project/newid123", {"name": "prod", "refresh_interval": 30000})
    project = await coroot.projects.get("newid123")
    assert project["name"] == "prod"

    fake.on("POST", "/api/project/newid123", text="newid123\n")
    await coroot.projects.update("newid123", name="prod2", member_projects=["a"])
    assert fake.body(fake.last)["member_projects"] == ["a"]

    fake.on("DELETE", "/api/project/newid123")
    await coroot.projects.delete("newid123")


async def test_unknown_project_empty_body_is_not_found(
    coroot: CorootClient, fake: FakeCoroot
) -> None:
    fake.on("GET", "/api/project/ghost", text="")
    with pytest.raises(CorootNotFoundError):
        await coroot.projects.get("ghost")


async def test_project_status(coroot: CorootClient, fake: FakeCoroot) -> None:
    fake.on(
        "GET", "/api/project/p1/status", enveloped({"status": "ok", "prometheus": {}})
    )
    result = await coroot.projects.status("p1")
    assert result.data["status"] == "ok"
    assert result.known_nodes == ["n1"]


async def test_api_keys(coroot: CorootClient, fake: FakeCoroot) -> None:
    state = {"keys": [{"key": "old", "description": "default"}]}

    def get_keys(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"editable": True, "keys": state["keys"]})

    def post_keys(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if body["action"] == "generate":
            state["keys"] = [
                *state["keys"],
                {"key": "fresh", "description": body["description"]},
            ]
        elif body["action"] == "delete":
            state["keys"] = [k for k in state["keys"] if k["key"] != body["key"]]
        return httpx.Response(200)

    fake.handle("GET", "/api/project/p1/api_keys", get_keys)
    fake.handle("POST", "/api/project/p1/api_keys", post_keys)

    created = await coroot.projects.generate_api_key("p1", "ci")
    assert created == {"key": "fresh", "description": "ci"}
    await coroot.projects.delete_api_key("p1", "fresh")
    assert [k["key"] for k in (await coroot.projects.api_keys("p1"))["keys"]] == ["old"]
    await coroot.projects.edit_api_key("p1", "old", "renamed")
    assert fake.body(fake.last)["description"] == "renamed"


# -- overview ---------------------------------------------------------------


async def test_overview_extracts_requested_view(
    coroot: CorootClient, fake: FakeCoroot
) -> None:
    fake.on(
        "GET",
        "/api/project/p1/overview/applications",
        enveloped(
            {
                "applications": [
                    {"id": "p1:default:Deployment:api", "status": "warning"}
                ],
                "nodes": None,
                "categories": ["application", "database"],
            }
        ),
    )
    result = await coroot.overview.applications("p1", from_="6h")
    assert result.data == [{"id": "p1:default:Deployment:api", "status": "warning"}]
    assert result.context["categories"] == ["application", "database"]
    assert query_of(fake)["from"] == "now-6h"


async def test_overview_traces_query(coroot: CorootClient, fake: FakeCoroot) -> None:
    fake.on(
        "GET", "/api/project/p1/overview/traces", enveloped({"traces": {"summary": {}}})
    )
    await coroot.overview.traces(
        "p1",
        view="errors",
        filters=[{"field": "ServiceName", "op": "=", "value": "checkout"}],
        dur_from="1s",
    )
    query = json.loads(query_of(fake)["query"])
    assert query["view"] == "errors"
    assert query["filters"][0]["value"] == "checkout"
    assert query["dur_from"] == "1s"


async def test_overview_logs_query(coroot: CorootClient, fake: FakeCoroot) -> None:
    fake.on(
        "GET", "/api/project/p1/overview/logs", enveloped({"logs": {"entries": []}})
    )
    await coroot.overview.logs(
        "p1", filters=[{"name": "Severity", "op": "=", "value": "error"}], limit=25
    )
    query = json.loads(query_of(fake)["query"])
    assert query["limit"] == 25
    assert query["agent"] is True and query["otel"] is True


# -- applications -----------------------------------------------------------


async def test_application_id_is_completed_and_encoded(
    coroot: CorootClient, fake: FakeCoroot
) -> None:
    path = "/api/project/p1/app/p1%3Adefault%3ADeployment%3Aapi"
    fake.on("GET", path, enveloped({"app_map": {}, "reports": []}))
    result = await coroot.applications.get("p1", "default:Deployment:api", from_="1h")
    assert result.data["reports"] == []
    assert fake.last_path == path


async def test_application_logs_and_traces(
    coroot: CorootClient, fake: FakeCoroot
) -> None:
    base = "/api/project/p1/app/p1%3Adefault%3ADeployment%3Aapi"
    fake.on("GET", f"{base}/logs", enveloped({"entries": []}))
    await coroot.applications.logs(
        "p1",
        "p1:default:Deployment:api",
        filters=[{"name": "Severity", "op": "=", "value": "error"}],
        limit=10,
    )
    query = json.loads(query_of(fake)["query"])
    assert query["view"] == "messages" and query["limit"] == 10

    fake.on("GET", f"{base}/tracing", enveloped({"spans": []}))
    trace = build_trace_param(
        source="otel", ts_from="now-10m", ts_to="now", dur_from=0.5
    )
    await coroot.applications.tracing("p1", "p1:default:Deployment:api", trace=trace)
    assert query_of(fake)["trace"] == "otel::now-10m-now:0.5-"

    fake.on("GET", f"{base}/profiling", enveloped({"profile": {}}))
    await coroot.applications.profiling("p1", "p1:default:Deployment:api", query="cpu")
    assert query_of(fake)["query"] == "cpu"


async def test_application_settings_writes(
    coroot: CorootClient, fake: FakeCoroot
) -> None:
    base = "/api/project/p1/app/p1%3Adefault%3ADeployment%3Aapi"
    for suffix in ("profiling", "tracing", "logs"):
        fake.on("POST", f"{base}/{suffix}")
    await coroot.applications.set_profiling_service(
        "p1", "p1:default:Deployment:api", "svc"
    )
    assert fake.body(fake.last) == {"service": "svc"}
    await coroot.applications.set_tracing_service(
        "p1", "p1:default:Deployment:api", "svc"
    )
    await coroot.applications.set_logs_service("p1", "p1:default:Deployment:api", "svc")

    fake.on("POST", f"{base}/instrumentation/postgres")
    await coroot.applications.set_instrumentation(
        "p1",
        "p1:default:Deployment:api",
        {"type": "postgres", "port": "5432", "enabled": True},
    )
    assert fake.body(fake.last)["type"] == "postgres"
    with pytest.raises(CorootValidationError):
        await coroot.applications.set_instrumentation(
            "p1", "p1:default:Deployment:api", {}
        )

    fake.on("POST", f"{base}/risks")
    await coroot.applications.set_risk_override(
        "p1",
        "p1:default:Deployment:api",
        action="dismiss",
        category="Availability",
        risk_type="single-instance-app",
        reason="accepted",
    )
    body = fake.body(fake.last)
    assert body["key"] == {"category": "Availability", "type": "single-instance-app"}


async def test_inspection_config_project_scope(
    coroot: CorootClient, fake: FakeCoroot
) -> None:
    path = "/api/project/p1/app/%3A%3A/inspection/CPUContainer/config"
    fake.on("GET", path, {"form": {"configs": [{"threshold": 80}, None]}})
    form = await coroot.applications.get_inspection_config("p1", "::", "CPUContainer")
    assert form["form"]["configs"][0]["threshold"] == 80
    fake.on("POST", path)
    await coroot.applications.set_inspection_config(
        "p1", "::", "CPUContainer", {"configs": [None, {"threshold": 90}]}
    )
    assert fake.body(fake.last)["configs"][1]["threshold"] == 90


async def test_node_report(coroot: CorootClient, fake: FakeCoroot) -> None:
    fake.on(
        "GET", "/api/project/p1/node/node-1", enveloped({"name": "Node", "checks": []})
    )
    result = await coroot.nodes.get("p1", "node-1")
    assert result.data["name"] == "Node"


# -- incidents and alerts ---------------------------------------------------


async def test_incidents(coroot: CorootClient, fake: FakeCoroot) -> None:
    fake.on(
        "GET",
        "/api/project/p1/incidents",
        enveloped([{"key": "abc", "severity": "critical"}]),
    )
    result = await coroot.incidents.list("p1", limit=10, from_="2d")
    assert result.data[0]["key"] == "abc"
    assert query_of(fake) == {"from": "now-2d", "limit": "10"}

    fake.on(
        "GET", "/api/project/p1/incident/abc", enveloped({"key": "abc", "widgets": []})
    )
    single = await coroot.incidents.get("p1", "abc")
    assert single.data["key"] == "abc"


async def test_alerts(coroot: CorootClient, fake: FakeCoroot) -> None:
    fake.on(
        "GET",
        "/api/project/p1/alerts",
        enveloped({"alerts": [{"id": "a1"}], "total": 1, "firing": 1, "resolved": 0}),
    )
    result = await coroot.alerts.list("p1", include_resolved=True, limit=5)
    assert result.data["firing"] == 1
    query = query_of(fake)
    assert query["include_resolved"] == "true" and query["limit"] == "5"

    fake.on("GET", "/api/project/p1/alerts/a1", enveloped({"id": "a1", "widgets": []}))
    single = await coroot.alerts.get("p1", "a1")
    assert single.data["id"] == "a1"
    assert query_of(fake)["alert"] == "a1"

    for action in ("resolve", "suppress", "reopen"):
        fake.on("POST", f"/api/project/p1/alerts/{action}", status=204)
    await coroot.alerts.resolve("p1", ["a1"])
    assert fake.body(fake.last) == {"ids": ["a1"]}
    await coroot.alerts.suppress("p1", ["a1"])
    await coroot.alerts.reopen("p1", ["a1"])


async def test_alerting_rules(coroot: CorootClient, fake: FakeCoroot) -> None:
    fake.on(
        "GET",
        "/api/project/p1/alerting-rules",
        enveloped({"rules": [{"id": "r1"}], "checks": [], "alert_counts": {}}),
    )
    listing = await coroot.alerting_rules.list("p1")
    assert listing.data["rules"][0]["id"] == "r1"

    rule = {"name": "cpu", "severity": "warning", "enabled": True}
    fake.on("POST", "/api/project/p1/alerting-rules", {"id": "r2", **rule})
    created = await coroot.alerting_rules.create("p1", rule)
    assert created["id"] == "r2"

    fake.on("GET", "/api/project/p1/alerting-rules/r2", {"id": "r2", **rule})
    assert (await coroot.alerting_rules.get("p1", "r2"))["name"] == "cpu"

    fake.on("PUT", "/api/project/p1/alerting-rules/r2", {"id": "r2", "enabled": False})
    updated = await coroot.alerting_rules.update("p1", "r2", {**rule, "enabled": False})
    assert updated["enabled"] is False

    fake.on("DELETE", "/api/project/p1/alerting-rules/r2", status=204)
    await coroot.alerting_rules.delete("p1", "r2")

    fake.on("GET", "/api/project/p1/alerting-rules/export", {"yaml": "- id: r1\n"})
    assert (await coroot.alerting_rules.export("p1")).startswith("- id: r1")


# -- dashboards and panels --------------------------------------------------


async def test_dashboards(coroot: CorootClient, fake: FakeCoroot) -> None:
    fake.on(
        "GET", "/api/project/p1/dashboards", enveloped([{"id": "d1", "name": "Redis"}])
    )
    listing = await coroot.dashboards.list("p1")
    assert listing.data[0]["id"] == "d1"

    fake.on("POST", "/api/project/p1/dashboards", text="d2\n", status=201)
    assert await coroot.dashboards.create("p1", name="New") == "d2"
    assert fake.body(fake.last)["action"] == "create"

    fake.on(
        "GET",
        "/api/project/p1/dashboards/d2",
        enveloped({"id": "d2", "name": "New", "config": {"groups": []}}),
    )
    single = await coroot.dashboards.get("p1", "d2")
    assert single.data["config"] == {"groups": []}

    fake.on("POST", "/api/project/p1/dashboards/d2")
    await coroot.dashboards.update("p1", "d2", name="Renamed")
    assert fake.body(fake.last)["action"] == "update"

    panel = build_panel([metrics_query("up", legend="{{instance}}")], name="Up")
    await coroot.dashboards.save_config(
        "p1",
        "d2",
        name="Renamed",
        config={"groups": [{"name": "g", "panels": [panel]}]},
    )
    saved = fake.body(fake.last)
    assert saved["action"] == ""
    assert (
        saved["config"]["groups"][0]["panels"][0]["source"]["metrics"]["queries"][0][
            "query"
        ]
        == "up"
    )

    await coroot.dashboards.delete("p1", "d2")
    assert fake.body(fake.last) == {"action": "delete", "id": "d2", "name": "New"}


async def test_panel_data(coroot: CorootClient, fake: FakeCoroot) -> None:
    fake.on("GET", "/api/project/p1/panel/data", {"chart": {"series": []}})
    panel = build_panel([metrics_query("up")])
    data = await coroot.dashboards.panel_data("p1", panel, from_="30m")
    assert data["chart"] == {"series": []}
    assert (
        json.loads(query_of(fake)["query"])["source"]["metrics"]["queries"][0]["query"]
        == "up"
    )


# -- configuration ----------------------------------------------------------


async def test_inspections_and_categories(
    coroot: CorootClient, fake: FakeCoroot
) -> None:
    fake.on(
        "GET",
        "/api/project/p1/inspections",
        enveloped({"checks": [{"id": "CPUContainer", "title": "CPU"}]}),
    )
    checks = await coroot.inspections.list("p1")
    assert checks.data["checks"][0]["id"] == "CPUContainer"

    fake.on(
        "GET",
        "/api/project/p1/application_categories",
        [{"name": "application", "builtin": True}],
    )
    assert (await coroot.categories.list("p1"))[0]["name"] == "application"

    fake.on("POST", "/api/project/p1/application_categories")
    await coroot.categories.save(
        "p1", {"action": "", "id": "", "name": "db", "custom_patterns": "ns/*"}
    )
    assert fake.body(fake.last)["name"] == "db"
    await coroot.categories.delete("p1", "db")
    assert fake.body(fake.last)["action"] == "delete"
    await coroot.categories.test_notification(
        "p1", "db", {"incident": {"slack": {"channel": "ops"}}}
    )
    assert fake.body(fake.last)["action"] == "test"


async def test_custom_applications(coroot: CorootClient, fake: FakeCoroot) -> None:
    fake.on(
        "GET",
        "/api/project/p1/custom_applications",
        {"custom_applications": [{"name": "batch", "instance_patterns": "job-*"}]},
    )
    assert (await coroot.custom_applications.list("p1"))[0]["name"] == "batch"

    fake.on("POST", "/api/project/p1/custom_applications")
    await coroot.custom_applications.save(
        "p1", name="batch", instance_patterns=["job-*", "cron-*"]
    )
    assert fake.body(fake.last) == {
        "name": "batch",
        "new_name": "batch",
        "instance_patterns": "job-* cron-*",
    }
    await coroot.custom_applications.save(
        "p1", name="batch2", instance_patterns=["job-*"], current_name="batch"
    )
    assert fake.body(fake.last)["name"] == "batch"
    await coroot.custom_applications.delete("p1", "batch")
    assert fake.body(fake.last)["instance_patterns"] == ""
    with pytest.raises(CorootValidationError):
        await coroot.custom_applications.save("p1", name="x", instance_patterns=[])


async def test_cloud_pricing_and_integrations(
    coroot: CorootClient, fake: FakeCoroot
) -> None:
    fake.on("GET", "/api/project/p1/custom_cloud_pricing", {"default": True})
    assert (await coroot.cloud_pricing.get("p1"))["default"] is True
    fake.on("POST", "/api/project/p1/custom_cloud_pricing")
    await coroot.cloud_pricing.set("p1", per_cpu_core=0.04, per_memory_gb=0.005)
    assert fake.body(fake.last)["per_cpu_core"] == 0.04
    fake.on("DELETE", "/api/project/p1/custom_cloud_pricing")
    await coroot.cloud_pricing.reset("p1")

    fake.on(
        "GET",
        "/api/project/p1/integrations",
        {
            "base_url": "https://c.example",
            "integrations": [{"type": "slack", "configured": True}],
        },
    )
    assert (await coroot.integrations.list("p1"))["base_url"] == "https://c.example"
    fake.on("PUT", "/api/project/p1/integrations")
    await coroot.integrations.set_base_url("p1", "https://c2.example")
    assert fake.body(fake.last) == {"base_url": "https://c2.example"}

    fake.on("GET", "/api/project/p1/integrations/slack", {"token": "<hidden>"})
    assert (await coroot.integrations.get("p1", "slack"))["token"] == "<hidden>"
    fake.on("PUT", "/api/project/p1/integrations/slack")
    await coroot.integrations.save(
        "p1", "slack", {"token": "t", "default_channel": "ops"}
    )
    assert fake.last.method == "PUT"
    fake.on("POST", "/api/project/p1/integrations/slack")
    await coroot.integrations.test(
        "p1", "slack", {"token": "t", "default_channel": "ops"}
    )
    assert fake.last.method == "POST"
    fake.on("DELETE", "/api/project/p1/integrations/slack")
    await coroot.integrations.delete("p1", "slack")


# -- metrics ----------------------------------------------------------------


async def test_metrics_series_and_labels(
    coroot: CorootClient, fake: FakeCoroot
) -> None:
    fake.on(
        "GET",
        "/api/project/p1/prom/api/v1/series",
        {"status": "success", "data": [{"__name__": "up"}]},
    )
    series = await coroot.metrics.series("p1", ["up"], from_="1h")
    assert series["data"][0]["__name__"] == "up"
    assert fake.last.url.params.get_list("match[]") == ["up"]

    fake.on(
        "GET",
        "/api/project/p1/prom/api/v1/label/__name__/values",
        {"status": "success", "data": ["up", "node_cpu"]},
    )
    values = await coroot.metrics.label_values(
        "p1", "__name__", match=["{__name__=~'up.*'}"]
    )
    assert values["data"] == ["up", "node_cpu"]

    fake.on(
        "GET", "/api/project/p1/prom/api/v1/metadata", {"status": "success", "data": {}}
    )
    await coroot.metrics.metadata("p1", metric="up", datasource="member1")
    assert fake.last.headers["X-Datasource"] == "member1"


async def test_metrics_query_uses_panel_data(
    coroot: CorootClient, fake: FakeCoroot
) -> None:
    fake.on(
        "GET", "/api/project/p1/panel/data", {"chart": {"series": [{"name": "up"}]}}
    )
    result = await coroot.metrics.query("p1", "up", from_="15m")
    assert result["chart"]["series"][0]["name"] == "up"
    panel = json.loads(query_of(fake)["query"])
    assert panel["source"]["metrics"]["queries"][0]["query"] == "up"


async def test_query_range_uses_api_key(fake: FakeCoroot) -> None:
    fake.on("GET", "/api/v1/query_range", {"status": "success", "data": {"result": []}})
    settings = Settings(base_url="http://coroot.test", api_key="key1")
    client = CorootClient(settings, transport=httpx.MockTransport(fake))
    try:
        result = await client.metrics.query_range("up", from_="1h", step="60s")
    finally:
        await client.aclose()
    assert result["status"] == "success"
    assert fake.last.headers["X-API-Key"] == "key1"
    assert unquote(str(fake.last.url.params["query"])) == "up"


async def test_client_context_manager(fake: FakeCoroot, settings: Settings) -> None:
    fake.on("GET", "/api/user", {"email": "admin"})
    async with CorootClient(settings, transport=httpx.MockTransport(fake)) as client:
        assert (await client.auth.current_user())["email"] == "admin"
