"""Tests for configuration, dashboard and user tools."""

from __future__ import annotations

from typing import Any

import httpx2 as httpx
from mcp import Client
from mcp.types import TextContent

from mcp_coroot.client import CorootClient
from mcp_coroot.config import Settings
from mcp_coroot.server import build_server
from tests.conftest import FakeCoroot

CONTEXT: dict[str, Any] = {"status": {"status": "ok"}, "search": {}}


def enveloped(data: Any) -> dict[str, Any]:
    return {"context": CONTEXT, "data": data}


def make_client(fake: FakeCoroot, settings: Settings) -> Client:
    server = build_server(
        settings,
        client_factory=lambda s: CorootClient(s, transport=httpx.MockTransport(fake)),
    )
    return Client(server)


async def call(_client: Client, _tool: str, **args: Any) -> dict[str, Any]:
    result = await _client.call_tool(_tool, args)
    block = result.content[0]
    detail = block.text if isinstance(block, TextContent) else ""
    assert result.is_error is False, detail
    assert isinstance(result.structured_content, dict)
    return result.structured_content


async def call_error(_client: Client, _tool: str, **args: Any) -> str:
    result = await _client.call_tool(_tool, args)
    assert result.is_error is True
    block = result.content[0]
    return block.text if isinstance(block, TextContent) else str(block)


def project(fake: FakeCoroot) -> FakeCoroot:
    fake.on("GET", "/api/user", {"projects": [{"id": "p1", "name": "prod"}]})
    return fake


# -- inspections and categories ---------------------------------------------


async def test_list_inspections(fake: FakeCoroot, settings: Settings) -> None:
    project(fake).on(
        "GET",
        "/api/project/p1/inspections",
        enveloped(
            {
                "checks": [
                    {
                        "id": "CPUContainer",
                        "title": "Container CPU",
                        "category": "CPU",
                        "unit": "percent",
                        "global_threshold": 80,
                        "project_threshold": 90,
                    }
                ]
            }
        ),
    )
    async with make_client(fake, settings) as client:
        result = await call(client, "list_inspections")
    assert result["count"] == 1
    assert result["checks"][0]["project_threshold"] == 90


async def test_update_inspection_config_scopes(
    fake: FakeCoroot, settings: Settings
) -> None:
    project(fake)
    fake.on("POST", "/api/project/p1/app/%3A%3A/inspection/CPUContainer/config")
    async with make_client(fake, settings) as client:
        await call(
            client,
            "update_inspection_config",
            check_id="CPUContainer",
            config={"configs": [None, {"threshold": 90}, None]},
        )
        assert fake.last_path.endswith("/app/%3A%3A/inspection/CPUContainer/config")

        fake.on(
            "POST",
            "/api/project/p1/app/p1%3Ans%3ADeployment%3Aapi/inspection/CPUContainer/config",
        )
        await call(
            client,
            "update_inspection_config",
            check_id="CPUContainer",
            app_id="ns:Deployment:api",
            config={"configs": [None, None, {"threshold": 95}]},
        )
    assert "p1%3Ans%3ADeployment%3Aapi" in fake.last_path
    assert fake.body(fake.last)["configs"][2]["threshold"] == 95


async def test_application_category_crud(fake: FakeCoroot, settings: Settings) -> None:
    routing = {
        "incidents": {"enabled": True, "slack": {"enabled": True, "channel": "ops"}}
    }

    def get_categories(request: httpx.Request) -> httpx.Response:
        name = request.url.params.get("name")
        if name is None:
            return httpx.Response(
                200,
                json=[{"name": "application", "builtin": True, "custom_patterns": ""}],
            )
        if name == "":
            return httpx.Response(200, json={"action": "", "id": "", "name": ""})
        return httpx.Response(
            200,
            json={
                "action": "",
                "id": name,
                "name": name,
                "custom_patterns": "default/pay-*",
                "notification_settings": routing,
            },
        )

    project(fake).handle(
        "GET", "/api/project/p1/application_categories", get_categories
    )
    fake.on("POST", "/api/project/p1/application_categories")
    async with make_client(fake, settings) as client:
        listed = await call(client, "list_application_categories")
        assert listed["count"] == 1

        await call(
            client,
            "save_application_category",
            name="databases",
            custom_patterns=["default/postgres-*", "default/redis-*"],
        )
        body = fake.body(fake.last)
        assert body["custom_patterns"] == "default/postgres-* default/redis-*"
        assert body["id"] == ""

        # Updating only the patterns must not erase the category's notification
        # routing: Coroot replaces the whole category on save.
        await call(
            client,
            "save_application_category",
            name="payments",
            current_name="payments",
            custom_patterns=["prod/pay-*"],
        )
        body = fake.body(fake.last)
        assert body["custom_patterns"] == "prod/pay-*"
        assert body["notification_settings"] == routing

        # ...and updating only the routing must not erase the patterns.
        await call(
            client,
            "save_application_category",
            name="payments",
            current_name="payments",
            notification_settings={"incidents": {"enabled": False}},
        )
        body = fake.body(fake.last)
        assert body["custom_patterns"] == "default/pay-*"
        assert body["notification_settings"] == {"incidents": {"enabled": False}}

        await call(client, "delete_application_category", name="datastores")
    assert fake.body(fake.last)["action"] == "delete"


async def test_custom_application_crud(fake: FakeCoroot, settings: Settings) -> None:
    project(fake).on(
        "GET",
        "/api/project/p1/custom_applications",
        {"custom_applications": [{"name": "workers", "instance_patterns": "worker-*"}]},
    )
    fake.on("POST", "/api/project/p1/custom_applications")
    async with make_client(fake, settings) as client:
        listed = await call(client, "list_custom_applications")
        assert listed["custom_applications"][0]["name"] == "workers"

        await call(
            client,
            "save_custom_application",
            name="workers",
            instance_patterns=["worker-*", "batch-*"],
        )
        assert fake.body(fake.last)["instance_patterns"] == "worker-* batch-*"

        await call(client, "delete_custom_application", name="workers")
    assert fake.body(fake.last)["instance_patterns"] == ""


# -- integrations ------------------------------------------------------------


async def test_integration_read_and_delete(
    fake: FakeCoroot, settings: Settings
) -> None:
    project(fake).on(
        "GET",
        "/api/project/p1/integrations",
        {"base_url": "https://coroot.example", "integrations": [{"type": "slack"}]},
    )
    fake.on(
        "GET", "/api/project/p1/integrations/pagerduty", {"integration_key": "<hidden>"}
    )
    fake.on("DELETE", "/api/project/p1/integrations/pagerduty")
    fake.on("PUT", "/api/project/p1/integrations")
    async with make_client(fake, settings) as client:
        listed = await call(client, "list_integrations")
        assert listed["base_url"] == "https://coroot.example"

        single = await call(client, "get_integration", integration_type="pagerduty")
        assert single["integration_key"] == "<hidden>"

        await call(client, "delete_integration", integration_type="pagerduty")
        assert fake.last.method == "DELETE"

        await call(
            client, "set_notification_base_url", base_url="https://coroot2.example"
        )
        assert fake.body(fake.last) == {"base_url": "https://coroot2.example"}

        message = await call_error(
            client, "get_integration", integration_type="carrier-pigeon"
        )
    assert "integration_type must be one of" in message


async def test_db_instrumentation_read(fake: FakeCoroot, settings: Settings) -> None:
    project(fake).on(
        "GET",
        "/api/project/p1/app/p1%3Ans%3AStatefulSet%3Apg/instrumentation/postgres",
        {"type": "postgres", "port": "5432", "enabled": True},
    )
    async with make_client(fake, settings) as client:
        result = await call(
            client,
            "get_db_instrumentation",
            app_id="ns:StatefulSet:pg",
            db_type="postgres",
        )
        assert result["port"] == "5432"
        assert result["application_id"] == "p1:ns:StatefulSet:pg"

        message = await call_error(
            client,
            "get_db_instrumentation",
            app_id="ns:StatefulSet:pg",
            db_type="oracle",
        )
    assert "db_type must be one of" in message


async def test_link_telemetry_service(fake: FakeCoroot, settings: Settings) -> None:
    project(fake)
    fake.on("POST", "/api/project/p1/app/p1%3Ans%3ADeployment%3Aapi/tracing")
    async with make_client(fake, settings) as client:
        await call(
            client,
            "link_telemetry_service",
            app_id="ns:Deployment:api",
            kind="tracing",
            service="checkout",
        )
        assert fake.body(fake.last) == {"service": "checkout"}

        message = await call_error(
            client,
            "link_telemetry_service",
            app_id="ns:Deployment:api",
            kind="metrics",
            service="x",
        )
    assert "kind must be one of" in message


# -- pricing and server settings --------------------------------------------


async def test_cloud_pricing(fake: FakeCoroot, settings: Settings) -> None:
    project(fake).on(
        "GET",
        "/api/project/p1/custom_cloud_pricing",
        {"default": True, "per_cpu_core": 0.03},
    )
    fake.on("POST", "/api/project/p1/custom_cloud_pricing")
    fake.on("DELETE", "/api/project/p1/custom_cloud_pricing")
    async with make_client(fake, settings) as client:
        current = await call(client, "get_cloud_pricing")
        assert current["default"] is True

        await call(client, "set_cloud_pricing", per_cpu_core=0.05, per_memory_gb=0.006)
        body = fake.body(fake.last)
        assert body["per_cpu_core"] == 0.05
        assert body["default"] is False

        await call(client, "reset_cloud_pricing")
    assert fake.last.method == "DELETE"


async def test_set_cloud_pricing_rejects_non_positive(
    fake: FakeCoroot, settings: Settings
) -> None:
    project(fake)
    async with make_client(fake, settings) as client:
        message = await call_error(
            client, "set_cloud_pricing", per_cpu_core=0, per_memory_gb=0.006
        )
    assert "greater than 0" in message


async def test_get_server_settings(fake: FakeCoroot, settings: Settings) -> None:
    project(fake).on("GET", "/api/sso", {"roles": ["Admin"], "default_role": "Viewer"})
    fake.on("GET", "/api/ai", {"provider": ""})
    fake.on("GET", "/api/cloud", {"status": "unconfigured"})
    async with make_client(fake, settings) as client:
        result = await call(client, "get_server_settings")
    assert result["sso"]["default_role"] == "Viewer"
    assert result["cloud"]["status"] == "unconfigured"
    assert result["base_url"] == "http://coroot.test"


# -- dashboards --------------------------------------------------------------


async def test_dashboard_crud(fake: FakeCoroot, settings: Settings) -> None:
    project(fake).on(
        "GET", "/api/project/p1/dashboards", enveloped([{"id": "d1", "name": "Redis"}])
    )
    fake.on("POST", "/api/project/p1/dashboards", text="d2\n", status=201)
    fake.on("POST", "/api/project/p1/dashboards/d2")
    fake.on(
        "GET",
        "/api/project/p1/dashboards/d2",
        enveloped({"id": "d2", "name": "New", "config": {"groups": []}}),
    )
    async with make_client(fake, settings) as client:
        listed = await call(client, "list_dashboards")
        assert listed["count"] == 1

        created = await call(client, "create_dashboard", name="New")
        assert created["dashboard_id"] == "d2"

        fetched = await call(client, "get_dashboard", dashboard_id="d2")
        assert fetched["config"] == {"groups": []}

        await call(client, "update_dashboard", dashboard_id="d2", name="Renamed")
        assert fake.body(fake.last)["action"] == "update"

        await call(client, "delete_dashboard", dashboard_id="d2")
    assert fake.body(fake.last)["action"] == "delete"


async def test_get_panel_data_builds_a_panel(
    fake: FakeCoroot, settings: Settings
) -> None:
    project(fake).on(
        "GET",
        "/api/project/p1/panel/data",
        {
            "chart": {
                "ctx": {"from": 1, "to": 2, "step": 30},
                "series": [{"name": "a", "data": [1, 2]}],
            }
        },
    )
    async with make_client(fake, settings) as client:
        result = await call(
            client,
            "get_panel_data",
            queries=["up", "rate(x[5m])"],
            legend="{{instance}}",
        )
    assert result["queries"] == ["up", "rate(x[5m])"]
    assert result["chart"]["series"][0]["avg"] == 1.5
    import json

    panel = json.loads(dict(fake.last.url.params)["query"])
    queries = panel["source"]["metrics"]["queries"]
    assert [q["query"] for q in queries] == ["up", "rate(x[5m])"]
    assert queries[0]["legend"] == "{{instance}}"


# -- users -------------------------------------------------------------------


async def test_user_tools(fake: FakeCoroot, settings: Settings) -> None:
    project(fake).on(
        "GET",
        "/api/users",
        {
            "users": [{"id": 1, "email": "admin", "role": "Admin"}],
            "roles": ["Admin", "Viewer"],
        },
    )
    fake.on("POST", "/api/users")
    fake.on(
        "GET",
        "/api/roles",
        {"roles": [{"name": "Admin", "permissions": []}], "scopes": [{"name": "*"}]},
    )
    fake.on("POST", "/api/user")
    async with make_client(fake, settings) as client:
        users = await call(client, "list_users")
        assert users["roles"] == ["Admin", "Viewer"]

        roles = await call(client, "list_roles")
        assert roles["roles"][0]["name"] == "Admin"

        await call(
            client, "create_user", email="a@b.c", name="A", role="Viewer", password="pw"
        )
        assert fake.body(fake.last)["action"] == "create"

        await call(
            client, "update_user", user_id=2, email="a@b.c", name="A2", role="Editor"
        )
        assert fake.body(fake.last)["name"] == "A2"

        await call(client, "delete_user", user_id=2)
        assert fake.body(fake.last) == {"action": "delete", "id": 2}

        result = await call(
            client, "change_password", old_password="old", new_password="new"
        )
    assert "COROOT_PASSWORD" in result["message"]


# -- remaining read tools ----------------------------------------------------


async def test_alerting_rule_read_tools(fake: FakeCoroot, settings: Settings) -> None:
    project(fake).on(
        "GET",
        "/api/project/p1/alerting-rules/r1",
        {"id": "r1", "name": "CPU", "source": {"type": "check"}},
    )
    fake.on(
        "GET",
        "/api/project/p1/alerting-rules/export",
        {"yaml": "- id: r1\n  name: CPU\n"},
    )
    fake.on("PUT", "/api/project/p1/alerting-rules/r1", {"id": "r1", "enabled": False})
    async with make_client(fake, settings) as client:
        rule = await call(client, "get_alerting_rule", rule_id="r1")
        assert rule["name"] == "CPU"

        exported = await call(client, "export_alerting_rules")
        assert exported["yaml"].startswith("- id: r1")

        await call(
            client,
            "update_alerting_rule",
            rule_id="r1",
            rule={"name": "CPU", "enabled": False},
        )
    assert fake.last.method == "PUT"


async def test_alert_detail_and_state_changes(
    fake: FakeCoroot, settings: Settings
) -> None:
    project(fake).on(
        "GET",
        "/api/project/p1/alerts/a1",
        enveloped(
            {
                "id": "a1",
                "rule_name": "Memory",
                "severity": "warning",
                "summary": "memory high",
                "opened_at": 1704067200000,
                "details": [{"name": "usage", "value": "91%"}],
            }
        ),
    )
    for action in ("suppress", "reopen"):
        fake.on("POST", f"/api/project/p1/alerts/{action}", status=204)
    async with make_client(fake, settings) as client:
        alert = await call(client, "get_alert", alert_id="a1")
        assert alert["rule"] == "Memory"
        assert alert["details"][0]["value"] == "91%"

        await call(client, "suppress_alerts", alert_ids=["a1"])
        await call(client, "reopen_alerts", alert_ids=["a1"])
    assert fake.body(fake.last) == {"ids": ["a1"]}


async def test_api_key_tools(fake: FakeCoroot, settings: Settings) -> None:
    keys: list[dict[str, str]] = [{"key": "k1", "description": "default"}]

    def get_keys(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"editable": True, "keys": keys})

    def post_keys(request: httpx.Request) -> httpx.Response:
        body = fake.body(request)
        if body["action"] == "generate":
            keys.append({"key": "k2", "description": body["description"]})
        else:
            keys[:] = [k for k in keys if k["key"] != body.get("key")]
        return httpx.Response(200)

    project(fake).handle("GET", "/api/project/p1/api_keys", get_keys)
    fake.handle("POST", "/api/project/p1/api_keys", post_keys)
    async with make_client(fake, settings) as client:
        listed = await call(client, "list_api_keys")
        assert listed["keys"][0]["key"] == "k1"

        created = await call(client, "create_api_key", description="ci")
        assert created["key"] == "k2"

        await call(client, "delete_api_key", key="k2")
    assert [k["key"] for k in keys] == ["k1"]


async def test_get_project_and_update(fake: FakeCoroot, settings: Settings) -> None:
    project(fake).on(
        "GET",
        "/api/project/p1",
        {"name": "prod", "refresh_interval": 30000, "api_keys": []},
    )
    fake.on("POST", "/api/project/p1", text="p1\n")
    async with make_client(fake, settings) as client:
        result = await call(client, "get_project")
        assert result["name"] == "prod"
        assert result["id"] == "p1"

        await call(client, "update_project", name="production")
    # The tool refreshes its project cache afterwards, so find the write itself.
    posted = fake.calls("POST", "/api/project/p1")[-1]
    assert fake.body(posted)["name"] == "production"


async def test_service_map_and_rca(fake: FakeCoroot, settings: Settings) -> None:
    project(fake).on(
        "GET",
        "/api/project/p1/overview/map",
        enveloped(
            {
                "map": [
                    {
                        "id": "p1:ns:Deployment:api",
                        "status": "warning",
                        "upstreams": [
                            {"id": "p1:ns:StatefulSet:db", "status": "critical"}
                        ],
                    }
                ]
            }
        ),
    )
    fake.on(
        "GET",
        "/api/project/p1/app/p1%3Ans%3ADeployment%3Aapi/rca",
        {
            "status": "OK",
            "short_summary": "database saturated",
            "root_cause": "connection pool exhausted",
            "immediate_fixes": "raise max_connections",
        },
    )
    async with make_client(fake, settings) as client:
        service_map = await call(client, "get_service_map")
        assert service_map["applications"][0]["upstreams"][0]["status"] == "critical"

        rca = await call(client, "get_application_rca", app_id="ns:Deployment:api")
    assert rca["status"] == "OK"
    assert rca["summary"] == "database saturated"


async def test_costs_and_risk_dismissal(fake: FakeCoroot, settings: Settings) -> None:
    project(fake).on(
        "GET",
        "/api/project/p1/overview/costs",
        enveloped(
            {
                "costs": {
                    "custom_pricing": False,
                    "nodes": [{"name": "n1", "price": 0.1}],
                    "applications": [
                        {"id": "p1:ns:Deployment:api", "usage_costs": 0.02}
                    ],
                }
            }
        ),
    )
    fake.on("POST", "/api/project/p1/app/p1%3Ans%3ADeployment%3Aapi/risks")
    async with make_client(fake, settings) as client:
        costs = await call(client, "get_costs")
        assert costs["nodes"][0]["name"] == "n1"

        await call(
            client,
            "set_risk_status",
            app_id="ns:Deployment:api",
            risk_category="Availability",
            risk_type="single-instance-app",
            action="dismiss",
            reason="accepted",
        )
        body = fake.body(fake.last)
        assert body["action"] == "dismiss"

        await call(
            client,
            "set_risk_status",
            app_id="ns:Deployment:api",
            risk_category="Availability",
            risk_type="single-instance-app",
            action="activate",
        )
    assert fake.body(fake.last)["action"] == "mark_as_active"


async def test_get_trace_via_application(fake: FakeCoroot, settings: Settings) -> None:
    project(fake).on(
        "GET",
        "/api/project/p1/app/p1%3Ans%3ADeployment%3Aapi/tracing",
        enveloped(
            {
                "spans": [
                    {
                        "service": "api",
                        "name": "GET /cart",
                        "id": "s1",
                        "timestamp": 1704067200000,
                        "duration": 12.5,
                        "status": {"error": False},
                    }
                ]
            }
        ),
    )
    async with make_client(fake, settings) as client:
        result = await call(
            client, "get_trace", trace_id="abc123", app_id="ns:Deployment:api"
        )
    assert result["span_count"] == 1
    assert result["spans"][0]["timestamp"] == "2024-01-01T00:00:00Z"
    assert dict(fake.last.url.params)["trace"] == ":abc123::"


async def test_node_lookup_and_log_severity_pass_through(
    fake: FakeCoroot, settings: Settings
) -> None:
    project(fake).on(
        "GET",
        "/api/project/p1/node/node-1",
        enveloped(
            {
                "name": "Node",
                "status": "ok",
                "checks": [{"title": "CPU", "status": "ok"}],
            }
        ),
    )
    async with make_client(fake, settings) as client:
        result = await call(client, "get_node", node="node-1")
    assert result["checks"][0]["title"] == "CPU"


async def test_incident_detail_includes_rca(
    fake: FakeCoroot, settings: Settings
) -> None:
    project(fake).on(
        "GET",
        "/api/project/p1/incident/inc1",
        enveloped(
            {
                "key": "inc1",
                "application_id": "p1:ns:Deployment:api",
                "severity": "critical",
                "opened_at": 1704067200000,
                "resolved_at": None,
                "short_description": "Latency SLO violated",
                "availability_slo": {
                    "objective": 99.9,
                    "compliance": 99.1,
                    "violated": True,
                },
                "actual_from": 1704063600000,
                "actual_to": 1704070800000,
                "rca": {
                    "status": "OK",
                    "short_summary": "database contention",
                    "root_cause": "lock waits on orders table",
                    "immediate_fixes": "add an index",
                },
                "details": {"availability_impact": {"percentage": 4.2}},
            }
        ),
    )
    async with make_client(fake, settings) as client:
        result = await call(client, "get_incident", incident_key="inc1")
    assert result["open"] is True
    assert result["opened_at"] == "2024-01-01T00:00:00Z"
    assert result["availability_slo"]["violated"] is True
    assert result["rca"]["root_cause"] == "lock waits on orders table"
    assert result["details"]["availability_impact"]["percentage"] == 4.2


async def test_trace_errors_and_project_wide_trace(
    fake: FakeCoroot, settings: Settings
) -> None:
    project(fake).on(
        "GET",
        "/api/project/p1/overview/traces",
        enveloped(
            {
                "traces": {
                    "errors": [
                        {
                            "service_name": "checkout",
                            "span_name": "POST /pay",
                            "count": 12,
                            "sample_trace_id": "t1",
                            "sample_error": "upstream timeout",
                        }
                    ],
                    "trace": [
                        {
                            "service": "checkout",
                            "name": "POST /pay",
                            "id": "s1",
                            "timestamp": 1704067200000,
                            "duration": 501.2,
                        }
                    ],
                }
            }
        ),
    )
    async with make_client(fake, settings) as client:
        errors = await call(client, "get_trace_errors", service="checkout")
        assert errors["errors"][0]["sample_trace_id"] == "t1"

        # Without app_id the trace is fetched through the project-wide view.
        trace = await call(client, "get_trace", trace_id="t1")
    assert trace["span_count"] == 1
    assert trace["spans"][0]["service"] == "checkout"


async def test_project_scoped_logs_use_the_application_endpoint(
    fake: FakeCoroot, settings: Settings
) -> None:
    project(fake).on(
        "GET",
        "/api/project/p1/app/p1%3Ans%3ADeployment%3Aapi/logs",
        enveloped(
            {
                "entries": [
                    {"timestamp": 1704067200000, "severity": "error", "message": "x"}
                ]
            }
        ),
    )
    async with make_client(fake, settings) as client:
        result = await call(
            client, "get_logs", app_id="ns:Deployment:api", trace_id="t1", limit=5
        )
    assert result["application_id"] == "p1:ns:Deployment:api"
    import json

    query = json.loads(dict(fake.last.url.params)["query"])
    assert {"name": "TraceId", "op": "=", "value": "t1"} in query["filters"]
    assert query["limit"] == 5


async def test_empty_query_results_do_not_crash(
    fake: FakeCoroot, settings: Settings
) -> None:
    # Coroot answers a PromQL query that matches nothing with a null chart.
    project(fake).on("GET", "/api/project/p1/panel/data", {"chart": None})
    async with make_client(fake, settings) as client:
        metrics = await call(client, "get_metrics", query="nonexistent_metric")
        assert metrics["series_count"] == 0
        assert "list_metrics" in metrics["message"]

        panel = await call(client, "get_panel_data", queries=["nonexistent_metric"])
    # Empty values are dropped to save tokens; the message carries the meaning.
    assert panel.get("chart") is None
    assert "no series" in panel["message"]


async def test_empty_overviews_do_not_crash(
    fake: FakeCoroot, settings: Settings
) -> None:
    # An unknown project, or one with no data yet, yields a null data field.
    project(fake)
    for view in ("applications", "nodes", "deployments", "risks", "map", "costs"):
        fake.on(
            "GET",
            f"/api/project/p1/overview/{view}",
            {"context": CONTEXT, "data": None},
        )
    async with make_client(fake, settings) as client:
        assert (await call(client, "list_applications"))["total"] == 0
        assert (await call(client, "list_nodes"))["count"] == 0
        assert (await call(client, "list_deployments"))["total"] == 0
        assert (await call(client, "list_risks"))["count"] == 0
        assert (await call(client, "get_service_map"))["count"] == 0
        costs = await call(client, "get_costs")
    assert costs["nodes"] == []


async def test_empty_telemetry_responses_do_not_crash(
    fake: FakeCoroot, settings: Settings
) -> None:
    project(fake)
    fake.on(
        "GET", "/api/project/p1/overview/traces", {"context": CONTEXT, "data": None}
    )
    fake.on("GET", "/api/project/p1/overview/logs", {"context": CONTEXT, "data": None})
    fake.on(
        "GET",
        "/api/project/p1/app/p1%3Ans%3ADeployment%3Aapi/profiling",
        enveloped(
            {"status": "warning", "message": "Clickhouse integration is not configured"}
        ),
    )
    async with make_client(fake, settings) as client:
        traces = await call(client, "get_traces")
        assert traces["endpoints"] == []

        logs = await call(client, "get_logs")
        assert logs["returned"] == 0

        profile = await call(client, "get_profile", app_id="ns:Deployment:api")
    assert profile.get("hotspots") is None
    assert "Clickhouse" in profile["message"]


async def test_trace_latency_sends_float_seconds(
    fake: FakeCoroot, settings: Settings
) -> None:
    # Coroot parses dur_from/dur_to as float seconds (utils.ParseHeatmapDuration).
    # A Go-style duration such as "1s" fails its ParseFloat and selects nothing,
    # which makes the server diff against a nil flame graph.
    project(fake).on(
        "GET",
        "/api/project/p1/overview/traces",
        enveloped(
            {"traces": {"latency": {"flamegraph": {"name": "root", "total": 10}}}}
        ),
    )
    import json

    async with make_client(fake, settings) as client:
        result = await call(client, "get_trace_latency", slower_than="500ms")
        query = json.loads(dict(fake.last.url.params)["query"])
        assert query["dur_from"] == "0.5"
        assert "dur_to" not in query
        # An unset upper bound is dropped rather than reported as null.
        assert result["band"] == {"slower_than_seconds": 0.5}

        await call(client, "get_trace_latency", slower_than="1s", faster_than="5s")
        query = json.loads(dict(fake.last.url.params)["query"])
        assert (query["dur_from"], query["dur_to"]) == ("1", "5")


async def test_trace_latency_rejects_an_empty_band(
    fake: FakeCoroot, settings: Settings
) -> None:
    project(fake)
    async with make_client(fake, settings) as client:
        zero = await call_error(client, "get_trace_latency", slower_than="0s")
        inverted = await call_error(
            client, "get_trace_latency", slower_than="5s", faster_than="1s"
        )
    assert "greater than zero" in zero
    assert "must be greater than slower_than" in inverted
