"""Tests for configuration, dashboard and user tools."""

from __future__ import annotations

import json
from typing import Any

import httpx2 as httpx
import pytest
from mcp import Client
from mcp.types import TextContent

from mcp_coroot.client import CorootClient
from mcp_coroot.config import ConfigError, Settings
from mcp_coroot.server import build_server
from tests.conftest import ALL_TOOLSETS, FakeCoroot

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
        "GET",
        "/api/project/p1/integrations/pagerduty",
        # Coroot returns the real key to any account that may edit integrations.
        {"integration_key": "r8k2-live-secret", "incidents": True},
    )
    fake.on("DELETE", "/api/project/p1/integrations/pagerduty")
    fake.on("PUT", "/api/project/p1/integrations")
    async with make_client(fake, settings) as client:
        listed = await call(client, "list_integrations")
        assert listed["base_url"] == "https://coroot.example"

        single = await call(client, "get_integration", integration_type="pagerduty")
        # Coroot hands the real key to any account that may edit integrations;
        # it must not reach the model.
        assert single["integration_key"] == "<redacted by mcp-coroot>"
        assert "r8k2-live-secret" not in json.dumps(single)
        assert single["incidents"] is True

        await call(client, "delete_integration", integration_type="pagerduty")
        assert fake.last.method == "DELETE"

        message = await call_error(
            client, "get_integration", integration_type="carrier-pigeon"
        )
    # Rejected by the schema enum before the tool body runs.
    assert "integration_type" in message
    assert "slack" in message


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
    assert "db_type" in message
    assert "postgres" in message


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
    assert "kind" in message
    assert "tracing" in message


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

        # Omitting both prices resets to Coroot's built-in rates.
        reset = await call(client, "set_cloud_pricing")
        assert "Reset" in reset["message"]
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
            client, "get_trace_by_id", trace_id="abc123", app_id="ns:Deployment:api"
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
        errors = await call(client, "list_trace_error_reasons", service="checkout")
        assert errors["errors"][0]["sample_trace_id"] == "t1"

        # Without app_id the trace is fetched through the project-wide view.
        trace = await call(client, "get_trace_by_id", trace_id="t1")
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
        assert (await call(client, "list_applications"))["total_in_project"] == 0
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
        traces = await call(client, "summarize_trace_endpoints")
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
        result = await call(client, "explain_trace_latency", slower_than="500ms")
        query = json.loads(dict(fake.last.url.params)["query"])
        assert query["dur_from"] == "0.5"
        assert "dur_to" not in query
        # An unset upper bound is dropped rather than reported as null.
        assert result["band"] == {"slower_than_seconds": 0.5}

        await call(client, "explain_trace_latency", slower_than="1s", faster_than="5s")
        query = json.loads(dict(fake.last.url.params)["query"])
        assert (query["dur_from"], query["dur_to"]) == ("1", "5")


async def test_trace_latency_rejects_an_empty_band(
    fake: FakeCoroot, settings: Settings
) -> None:
    project(fake)
    async with make_client(fake, settings) as client:
        zero = await call_error(client, "explain_trace_latency", slower_than="0s")
        inverted = await call_error(
            client, "explain_trace_latency", slower_than="5s", faster_than="1s"
        )
    assert "greater than zero" in zero
    assert "must be greater than slower_than" in inverted


async def test_application_report_keeps_chart_group_numbers(
    fake: FakeCoroot, settings: Settings
) -> None:
    # Audit reports carry their series inside chart groups; get_application must
    # not reduce those to a bare title.
    project(fake).on(
        "GET",
        "/api/project/p1/app/p1%3Ans%3ADeployment%3Aapi",
        enveloped(
            {
                "app_map": {
                    "application": {"id": "p1:ns:Deployment:api", "status": "warning"}
                },
                "reports": [
                    {
                        "name": "CPU",
                        "status": "warning",
                        "checks": [],
                        "widgets": [
                            {
                                "chart_group": {
                                    "title": "CPU usage by instance, cores",
                                    "charts": [
                                        {
                                            "title": "api-1",
                                            "series": [
                                                {"name": "usage", "data": [0.5, 1.5]}
                                            ],
                                        }
                                    ],
                                }
                            }
                        ],
                    }
                ],
            }
        ),
    )
    async with make_client(fake, settings) as client:
        result = await call(
            client, "get_application", app_id="ns:Deployment:api", report="CPU"
        )
    group = result["reports"][0]["widgets"][0]["chart_group"]
    assert group["title"] == "CPU usage by instance, cores"
    assert group["charts"][0]["series"][0]["max"] == 1.5


async def test_profile_category_with_instance_resolves_the_type(
    fake: FakeCoroot, settings: Settings
) -> None:
    # Coroot resolves 'cpu' to a featured profile type only when the request
    # carries no type, so an instance filter needs the concrete type first.
    calls: list[str] = []

    def profiling(request: httpx.Request) -> httpx.Response:
        query = request.url.params.get("query", "")
        calls.append(query)
        return httpx.Response(
            200,
            json=enveloped(
                {
                    "status": "ok",
                    "profile": {
                        "type": "go:profile_cpu:nanoseconds",
                        "flamegraph": {
                            "name": "root",
                            "total": 100,
                            "children": [{"name": "compress", "total": 90}],
                        },
                    },
                    "profiles": [{"type": "go:profile_cpu:nanoseconds", "name": "CPU"}],
                }
            ),
        )

    project(fake).handle(
        "GET", "/api/project/p1/app/p1%3Ans%3ADeployment%3Aapi/profiling", profiling
    )
    import json

    async with make_client(fake, settings) as client:
        result = await call(
            client,
            "get_profile",
            app_id="ns:Deployment:api",
            profile="cpu",
            instance="api-7d9f",
        )
    assert calls[0] == "cpu"
    assert json.loads(calls[1]) == {
        "type": "go:profile_cpu:nanoseconds",
        "instance": "api-7d9f",
    }
    assert result["hotspots"]["hottest"][0]["name"] == "compress"
    assert result["instance"] == "api-7d9f"


async def test_profile_rejects_an_unknown_category(
    fake: FakeCoroot, settings: Settings
) -> None:
    project(fake)
    async with make_client(fake, settings) as client:
        message = await call_error(
            client, "get_profile", app_id="ns:Deployment:api", profile="gpu"
        )
    assert "profile must be one of" in message


async def test_profile_reports_when_a_category_has_no_data(
    fake: FakeCoroot, settings: Settings
) -> None:
    project(fake).on(
        "GET",
        "/api/project/p1/app/p1%3Ans%3ADeployment%3Aapi/profiling",
        enveloped(
            {"status": "warning", "message": "No profiles found", "profiles": []}
        ),
    )
    async with make_client(fake, settings) as client:
        result = await call(
            client,
            "get_profile",
            app_id="ns:Deployment:api",
            profile="memory",
            instance="api-1",
        )
    assert "No profiles found" in result["message"]


async def test_alert_filters_scan_beyond_the_requested_limit(
    fake: FakeCoroot, settings: Settings
) -> None:
    # Coroot cannot return resolved alerts on their own: asking for them yields a
    # page of firing ones first. Filtering only the caller's page would report
    # zero resolved alerts while forty exist.
    firing = [
        {"id": f"f{i}", "rule_name": "CPU", "severity": "critical", "resolved_at": None}
        for i in range(3)
    ]
    resolved = [
        {
            "id": f"r{i}",
            "rule_name": "Memory",
            "severity": "warning",
            "resolved_at": 1704067200000,
        }
        for i in range(40)
    ]

    def alerts(request: httpx.Request) -> httpx.Response:
        limit = int(request.url.params.get("limit", "50"))
        page = (firing + resolved)[:limit]
        return httpx.Response(
            200,
            json=enveloped({"alerts": page, "total": 43, "firing": 3, "resolved": 40}),
        )

    project(fake).handle("GET", "/api/project/p1/alerts", alerts)
    async with make_client(fake, settings) as client:
        result = await call(client, "list_alerts", state_filter="resolved", limit=3)
    assert result["returned"] == 3
    assert result["matched"] == 40
    assert all(not a["firing"] for a in result["alerts"])
    # No search was applied here, so Coroot's counts really are project-wide.
    assert result["totals"] == {
        "scope": "project",
        "firing": 3,
        "resolved": 40,
        "total": 43,
    }
    # The wider scan is what makes the filter meaningful.
    assert int(dict(fake.last.url.params)["limit"]) > 3


async def test_alert_app_filter_uses_server_side_search(
    fake: FakeCoroot, settings: Settings
) -> None:
    project(fake).on(
        "GET",
        "/api/project/p1/alerts",
        enveloped(
            {
                "alerts": [
                    {
                        "id": "a1",
                        "application_id": "p1:ns:Deployment:api",
                        "severity": "warning",
                        "resolved_at": None,
                    },
                    {
                        "id": "a2",
                        "application_id": "p1:ns:Deployment:web",
                        "severity": "warning",
                        "resolved_at": None,
                    },
                ],
                "total": 2,
                "firing": 2,
                "resolved": 0,
            }
        ),
    )
    async with make_client(fake, settings) as client:
        result = await call(client, "list_alerts", app_id="p1:ns:Deployment:api")
    # Coroot's search matches application_id, so the filter reaches the database.
    assert dict(fake.last.url.params)["search"] == "p1:ns:Deployment:api"
    # The exact match still runs here, because search is a substring match.
    assert [a["id"] for a in result["alerts"]] == ["a1"]


async def test_incident_filters_scan_beyond_the_requested_limit(
    fake: FakeCoroot, settings: Settings
) -> None:
    open_incidents = [
        {"key": f"o{i}", "application_id": "p1:ns:Deployment:api", "resolved_at": None}
        for i in range(2)
    ]
    closed = [
        {
            "key": f"c{i}",
            "application_id": "p1:ns:Deployment:web",
            "resolved_at": 1704067200000,
        }
        for i in range(30)
    ]

    def incidents(request: httpx.Request) -> httpx.Response:
        limit = int(request.url.params.get("limit", "100"))
        return httpx.Response(200, json=enveloped((open_incidents + closed)[:limit]))

    project(fake).handle("GET", "/api/project/p1/incidents", incidents)
    async with make_client(fake, settings) as client:
        result = await call(client, "list_incidents", state_filter="resolved", limit=5)
        assert result["matched"] == 30
        assert result["returned"] == 5

        by_app = await call(
            client, "list_incidents", app_id="p1:ns:Deployment:api", limit=5
        )
    assert by_app["matched"] == 2


async def test_api_keys_tolerate_a_null_key_list(
    fake: FakeCoroot, settings: Settings
) -> None:
    # Coroot has no omitempty on the key list, so a project without keys (every
    # multicluster and config-file project) serialises it as null.
    keys: list[dict[str, str]] = []

    def get_keys(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"editable": True, "keys": keys if keys else None}
        )

    def post_keys(request: httpx.Request) -> httpx.Response:
        keys.append({"key": "k1", "description": fake.body(request)["description"]})
        return httpx.Response(200)

    project(fake).handle("GET", "/api/project/p1/api_keys", get_keys)
    fake.handle("POST", "/api/project/p1/api_keys", post_keys)
    async with make_client(fake, settings) as client:
        listed = await call(client, "list_api_keys")
        assert listed["keys"] == []

        created = await call(client, "create_api_key", description="first")
    assert created["key"] == "k1"


async def test_health_check_does_not_need_credentials(fake: FakeCoroot) -> None:
    # /health needs no auth, and the tool that distinguishes a connectivity
    # problem from a credentials one must not fail at login.
    bad = Settings(base_url="http://coroot.test", username="admin", password="wrong")
    async with make_client(fake, bad) as client:
        result = await call(client, "health_check")
    assert result["healthy"] is True
    assert [r.url.path for r in fake.requests] == ["/health"]


async def test_unexpected_errors_are_reported_not_swallowed(
    fake: FakeCoroot, settings: Settings
) -> None:
    # A bug in this server should still tell the model what happened.
    project(fake).on("GET", "/api/project/p1/overview/nodes", enveloped({"nodes": 42}))
    async with make_client(fake, settings) as client:
        message = await call_error(client, "list_nodes")
    assert "list_nodes failed unexpectedly" in message
    assert "bug in mcp-coroot" in message


async def test_database_credentials_are_redacted(
    fake: FakeCoroot, settings: Settings
) -> None:
    project(fake).on(
        "GET",
        "/api/project/p1/app/p1%3Ans%3AStatefulSet%3Apg/instrumentation/postgres",
        {
            "type": "postgres",
            "port": "5432",
            "enabled": True,
            "credentials": {"username": "coroot", "password": "pg-live-password"},
            "params": {"sslmode": "disable"},
        },
    )
    async with make_client(fake, settings) as client:
        result = await call(
            client,
            "get_db_instrumentation",
            app_id="ns:StatefulSet:pg",
            db_type="postgres",
        )
    assert "pg-live-password" not in json.dumps(result)
    assert result["credentials"]["password"] == "<redacted by mcp-coroot>"
    # Non-secret operational detail must survive redaction.
    assert result["port"] == "5432"
    assert result["enabled"] is True
    assert result["params"] == {"sslmode": "disable"}


async def test_secrets_can_be_revealed_deliberately(fake: FakeCoroot) -> None:
    reveal = Settings(
        base_url="http://coroot.test",
        username="admin",
        password="secret",
        reveal_secrets=True,
        toolsets=ALL_TOOLSETS,
    )
    fake.on("GET", "/api/user", {"projects": [{"id": "p1", "name": "prod"}]})
    fake.on(
        "GET",
        "/api/project/p1/integrations/slack",
        {"token": "xoxb-live", "default_channel": "ops"},
    )
    async with make_client(fake, reveal) as client:
        result = await call(client, "get_integration", integration_type="slack")
    assert result["token"] == "xoxb-live"


async def test_placeholders_are_refused_on_write(
    fake: FakeCoroot, settings: Settings
) -> None:
    project(fake)
    async with make_client(fake, settings) as client:
        redacted = await call_error(
            client,
            "configure_integration",
            integration_type="slack",
            config={"token": "<redacted by mcp-coroot>", "default_channel": "ops"},
        )
        hidden = await call_error(
            client,
            "configure_integration",
            integration_type="teams",
            config={"channels": [{"name": "d", "webhook_url": "<hidden>"}]},
        )
        creds = await call_error(
            client,
            "configure_db_instrumentation",
            app_id="ns:StatefulSet:pg",
            db_type="postgres",
            username="coroot",
            password="<redacted by mcp-coroot>",
        )
    assert "token" in redacted and "placeholder" in redacted
    assert "channels[0].webhook_url" in hidden
    assert "password" in creds
    # Nothing may have been written.
    assert [r.method for r in fake.requests if r.method in {"PUT", "POST"}] == ["POST"]


async def test_trace_latency_never_requests_the_diff(
    fake: FakeCoroot, settings: Settings
) -> None:
    # Coroot's FlameGraphNode.Diff dereferences its argument without a nil
    # check, and either side is nil when the band or its complement is empty.
    project(fake).on(
        "GET",
        "/api/project/p1/overview/traces",
        enveloped(
            {"traces": {"latency": {"flamegraph": {"name": "root", "total": 1}}}}
        ),
    )
    async with make_client(fake, settings) as client:
        await call(client, "explain_trace_latency", slower_than="1s")
    assert json.loads(dict(fake.last.url.params)["query"])["diff"] is False


async def test_manually_resolved_and_suppressed_alerts_are_not_firing(
    fake: FakeCoroot, settings: Settings
) -> None:
    # Coroot treats an alert as resolved if it resolved itself, a person
    # resolved it, or it was suppressed.
    project(fake).on(
        "GET",
        "/api/project/p1/alerts",
        enveloped(
            {
                "alerts": [
                    {"id": "a1", "severity": "critical", "resolved_at": None},
                    {
                        "id": "a2",
                        "severity": "warning",
                        "resolved_at": 0,
                        "manually_resolved_at": 1704067200000,
                        "resolved_by": "sre",
                    },
                    {
                        "id": "a3",
                        "severity": "warning",
                        "resolved_at": 0,
                        "suppressed": True,
                    },
                ],
                "total": 3,
                "firing": 1,
                "resolved": 2,
            }
        ),
    )
    async with make_client(fake, settings) as client:
        firing = await call(client, "list_alerts", state_filter="firing")
        resolved = await call(client, "list_alerts", state_filter="resolved")
    assert [a["id"] for a in firing["alerts"]] == ["a1"]
    assert sorted(a["id"] for a in resolved["alerts"]) == ["a2", "a3"]
    assert resolved["alerts"][0]["resolved_by"] == "sre"
    # by_severity must describe what was returned, not the whole scan.
    assert firing["by_severity"] == {"critical": 1}


async def test_alert_app_filter_normalises_the_id(
    fake: FakeCoroot, settings: Settings
) -> None:
    project(fake).on(
        "GET",
        "/api/project/p1/alerts",
        enveloped(
            {
                "alerts": [
                    {
                        "id": "a1",
                        "application_id": "p1:ns:Deployment:api",
                        "severity": "warning",
                        "resolved_at": None,
                    }
                ],
                "total": 1,
                "firing": 1,
                "resolved": 0,
            }
        ),
    )
    async with make_client(fake, settings) as client:
        # A three-part id must still match the four-part id Coroot returns.
        result = await call(client, "list_alerts", app_id="ns:Deployment:api")
    assert [a["id"] for a in result["alerts"]] == ["a1"]
    assert dict(fake.last.url.params)["search"] == "p1:ns:Deployment:api"
    assert result["totals"]["scope"] == "search"


def test_base_url_must_not_carry_credentials() -> None:
    # Userinfo in the URL would survive redacted() and reach logs, --check
    # output and tool responses.
    with pytest.raises(ConfigError, match="must not embed credentials"):
        Settings(base_url="https://admin:hunter2@coroot.example.com")


async def test_dashboard_config_round_trips_unchanged(
    fake: FakeCoroot, settings: Settings
) -> None:
    # update_dashboard_panels tells the model to read a dashboard and send the
    # modified version back, so get_dashboard must not strip panel settings.
    config = {
        "groups": [
            {
                "name": "Latency",
                "collapsed": False,
                "panels": [
                    {
                        "name": "p99",
                        "source": {
                            "metrics": {
                                "queries": [
                                    {"query": "up", "legend": "{{i}}", "color": "red"}
                                ]
                            }
                        },
                        "widget": {"chart": {"display": "line", "stacked": True}},
                        "box": {"x": 0, "y": 0, "w": 12, "h": 6},
                    }
                ],
            }
        ]
    }
    project(fake).on(
        "GET",
        "/api/project/p1/dashboards/d1",
        enveloped({"id": "d1", "name": "Redis", "config": config}),
    )
    async with make_client(fake, settings) as client:
        result = await call(client, "get_dashboard", dashboard_id="d1")
    assert result["config"] == config


async def test_get_application_defaults_to_the_diagnosis(
    fake: FakeCoroot, settings: Settings
) -> None:
    # A full audit report set runs to tens of thousands of tokens, most of it
    # chart summaries for checks that are passing.
    reports = [
        {
            "name": f"Report{i}",
            "status": "ok",
            "checks": [{"title": f"check-{i}", "status": "ok"}],
            "widgets": [
                {"chart": {"series": [{"name": "s", "data": list(range(200))}]}}
            ],
        }
        for i in range(10)
    ]
    reports[0]["status"] = "critical"
    reports[0]["checks"] = [
        {"title": "Latency", "status": "critical", "message": "p99 is 4s"}
    ]
    project(fake).on(
        "GET",
        "/api/project/p1/app/p1%3Ans%3ADeployment%3Aapi",
        enveloped(
            {"app_map": {"application": {"status": "critical"}}, "reports": reports}
        ),
    )
    async with make_client(fake, settings) as client:
        summary = await call(client, "get_application", app_id="ns:Deployment:api")
        assert summary["failing_checks"] == [
            {
                "report": "Report0",
                "check": "Latency",
                "status": "critical",
                "message": "p99 is 4s",
            }
        ]
        assert len(summary["report_names"]) == 10
        assert "reports" not in summary
        assert "report=<name>" in summary["note"]

        detail = await call(
            client, "get_application", app_id="ns:Deployment:api", report="Report0"
        )
    assert [r["name"] for r in detail["reports"]] == ["Report0"]


async def test_get_traces_ranks_and_limits(
    fake: FakeCoroot, settings: Settings
) -> None:
    stats = [
        {
            "service_name": "svc",
            "span_name": f"GET /{i}",
            "total": 100,
            "failed": i,
            "duration_quantiles": [{"quantile": 0.99, "value": float(i)}],
        }
        for i in range(30)
    ]
    project(fake).on(
        "GET",
        "/api/project/p1/overview/traces",
        enveloped({"traces": {"summary": {"stats": stats}}}),
    )
    async with make_client(fake, settings) as client:
        by_errors = await call(client, "summarize_trace_endpoints", limit=3)
        assert by_errors["total_endpoints"] == 30
        assert by_errors["omitted"] == 27
        assert [e["span"] for e in by_errors["endpoints"]] == [
            "GET /29",
            "GET /28",
            "GET /27",
        ]
        assert by_errors["endpoints"][0]["latency_seconds"] == {"p99": 29.0}

        by_latency = await call(
            client, "summarize_trace_endpoints", sort_by="latency", limit=1
        )
    assert by_latency["endpoints"][0]["span"] == "GET /29"


async def test_list_traces_bridges_summary_and_single_trace(
    fake: FakeCoroot, settings: Settings
) -> None:
    project(fake).on(
        "GET",
        "/api/project/p1/overview/traces",
        enveloped(
            {
                "traces": {
                    "traces": [
                        {
                            "trace_id": "t1",
                            "service": "checkout",
                            "name": "POST /pay",
                            "timestamp": 1704067200000,
                            "duration": 4210.5,
                            "status": {"error": True, "message": "upstream timeout"},
                        }
                    ]
                }
            }
        ),
    )
    async with make_client(fake, settings) as client:
        result = await call(
            client, "list_traces", service="checkout", slower_than="1.5s", limit=5
        )
    trace = result["traces"][0]
    assert trace["trace_id"] == "t1"
    assert trace["duration_ms"] == 4210.5
    assert trace["timestamp"] == "2024-01-01T00:00:00Z"
    query = json.loads(dict(fake.last.url.params)["query"])
    assert query["view"] == "traces"
    assert query["dur_from"] == "1.5"


async def test_list_traces_can_ask_for_errors_only(
    fake: FakeCoroot, settings: Settings
) -> None:
    project(fake).on(
        "GET",
        "/api/project/p1/overview/traces",
        enveloped({"traces": {"traces": []}}),
    )
    async with make_client(fake, settings) as client:
        result = await call(client, "list_traces", errors_only=True)
    # Coroot selects error traces with the 'inf' marker in the dur_from slot.
    assert json.loads(dict(fake.last.url.params)["query"])["dur_from"] == "inf"
    assert "No traces matched" in result["note"]


async def test_toolsets_select_what_is_registered(fake: FakeCoroot) -> None:
    async def names(**kw: Any) -> set[str]:
        s = Settings(base_url="http://coroot.test", username="a", password="b", **kw)
        async with make_client(fake, s) as client:
            return {t.name for t in (await client.list_tools()).tools}

    everything = frozenset({"diagnose", "alerts", "dashboards", "config", "admin"})
    default = await names()
    full = await names(toolsets=everything)

    # Finding a project works in every configuration.
    assert {"list_projects", "get_project_status", "health_check"} <= default
    # The diagnostic core is what the default is for.
    assert {
        "list_applications",
        "get_application",
        "get_logs",
        "summarize_trace_endpoints",
        "list_traces",
        "get_metrics",
        "list_alerts",
        "list_incidents",
    } <= default
    # Administration is not carried unless asked for.
    assert not {"create_user", "delete_project", "create_api_key"} & default
    assert {"create_user", "delete_project", "create_api_key"} <= full
    assert "list_dashboards" not in default
    assert "list_dashboards" in (await names(toolsets=frozenset({"dashboards"})))
    assert "resolve_alerts" not in default
    assert "resolve_alerts" in (await names(toolsets=frozenset({"alerts"})))
    assert len(default) < len(full)


def test_toolsets_are_parsed_and_validated() -> None:
    assert Settings.from_env({}).toolsets == frozenset({"diagnose"})
    assert Settings.from_env({"COROOT_TOOLSETS": "all"}).toolsets == frozenset(
        {"diagnose", "alerts", "dashboards", "config", "admin"}
    )
    assert Settings.from_env(
        {"COROOT_TOOLSETS": " Diagnose , admin "}
    ).toolsets == frozenset({"diagnose", "admin"})
    with pytest.raises(ConfigError, match="unknown group"):
        Settings.from_env({"COROOT_TOOLSETS": "diagnose,telepathy"})
