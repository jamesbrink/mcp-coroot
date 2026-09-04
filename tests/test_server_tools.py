"""End-to-end tool tests driven through an in-memory MCP client."""

from __future__ import annotations

import json
from typing import Any

import httpx2 as httpx
import pytest
from mcp import Client
from mcp.types import TextContent

from mcp_coroot.client import CorootClient
from mcp_coroot.config import Settings
from mcp_coroot.server import build_server
from tests.conftest import FakeCoroot

CONTEXT: dict[str, Any] = {
    "status": {"status": "ok"},
    "search": {"applications": [], "nodes": []},
    "incidents": {"application": 1},
    "alerts": {"critical": 2},
}


def enveloped(data: Any) -> dict[str, Any]:
    return {"context": CONTEXT, "data": data}


def make_client(fake: FakeCoroot, settings: Settings) -> Client:
    server = build_server(
        settings,
        client_factory=lambda s: CorootClient(s, transport=httpx.MockTransport(fake)),
    )
    return Client(server)


@pytest.fixture
def one_project(fake: FakeCoroot) -> FakeCoroot:
    fake.on(
        "GET",
        "/api/user",
        {"email": "admin", "projects": [{"id": "p1", "name": "prod"}]},
    )
    return fake


async def call(_client: Client, _tool: str, **args: Any) -> dict[str, Any]:
    """Call a tool and return its structured content, failing on tool errors."""
    result = await _client.call_tool(_tool, args)
    assert result.is_error is False, text_of(result)
    assert isinstance(result.structured_content, dict)
    return result.structured_content


async def call_error(_client: Client, _tool: str, **args: Any) -> str:
    """Call a tool expected to fail and return the message shown to the model."""
    result = await _client.call_tool(_tool, args)
    assert result.is_error is True
    return text_of(result)


def text_of(result: Any) -> str:
    block = result.content[0]
    return block.text if isinstance(block, TextContent) else str(block)


# -- discovery ---------------------------------------------------------------


async def test_tools_are_discoverable_and_annotated(
    one_project: FakeCoroot, settings: Settings
) -> None:
    async with make_client(one_project, settings) as client:
        tools = (await client.list_tools()).tools
        names = {t.name for t in tools}
        assert {"list_projects", "get_application", "get_logs", "list_alerts"} <= names
        assert len(tools) > 60
        by_name = {t.name: t for t in tools}
        assert by_name["list_projects"].annotations.read_only_hint is True
        assert by_name["delete_project"].annotations.destructive_hint is True
        # Descriptions are what the model plans with; every tool must have one.
        assert all(t.description for t in tools)


async def test_read_only_mode_hides_mutating_tools(one_project: FakeCoroot) -> None:
    settings = Settings(base_url="http://coroot.test", read_only=True)
    async with make_client(one_project, settings) as client:
        names = {t.name for t in (await client.list_tools()).tools}
    assert "list_applications" in names
    for hidden in (
        "delete_project",
        "create_user",
        "resolve_alerts",
        "set_cloud_pricing",
    ):
        assert hidden not in names


# -- projects ----------------------------------------------------------------


async def test_health_check_and_whoami(
    one_project: FakeCoroot, settings: Settings
) -> None:
    async with make_client(one_project, settings) as client:
        health = await call(client, "health_check")
        assert health["healthy"] is True
        assert health["auth_mode"] == "password"
        who = await call(client, "whoami")
        assert who["email"] == "admin"


async def test_list_projects(one_project: FakeCoroot, settings: Settings) -> None:
    async with make_client(one_project, settings) as client:
        result = await call(client, "list_projects")
        assert result["count"] == 1
        assert result["projects"][0]["id"] == "p1"


async def test_project_is_resolved_when_only_one_exists(
    one_project: FakeCoroot, settings: Settings
) -> None:
    async with make_client(one_project, settings) as client:
        one_project.on("GET", "/api/project/p1/status", enveloped({"status": "ok"}))
        result = await call(client, "get_project_status")
        assert result["project_id"] == "p1"
        assert result["open_incidents"] == {"application": 1}


async def test_ambiguous_project_asks_for_one(
    fake: FakeCoroot, settings: Settings
) -> None:
    fake.on(
        "GET",
        "/api/user",
        {
            "email": "admin",
            "projects": [{"id": "p1", "name": "prod"}, {"id": "p2", "name": "dev"}],
        },
    )
    async with make_client(fake, settings) as client:
        message = await call_error(client, "list_applications")
    assert "project_id is required" in message
    assert "prod (p1)" in message


async def test_default_project_from_settings(fake: FakeCoroot) -> None:
    settings = Settings(
        base_url="http://coroot.test",
        username="admin",
        password="secret",
        default_project="p9",
    )
    fake.on("GET", "/api/project/p9/status", enveloped({"status": "warning"}))
    async with make_client(fake, settings) as client:
        result = await call(client, "get_project_status")
    assert result["project_id"] == "p9"


async def test_project_write_tools(one_project: FakeCoroot, settings: Settings) -> None:
    async with make_client(one_project, settings) as client:
        one_project.on("POST", "/api/project/", text="p2\n")
        created = await call(client, "create_project", name="staging")
        assert created["project_id"] == "p2"

        one_project.on("DELETE", "/api/project/p2")
        deleted = await call(client, "delete_project", project_id="p2")
        assert deleted["ok"] is True

    # -- applications ------------------------------------------------------------


async def test_list_applications_summarises_health(
    one_project: FakeCoroot, settings: Settings
) -> None:
    async with make_client(one_project, settings) as client:
        one_project.on(
            "GET",
            "/api/project/p1/overview/applications",
            enveloped(
                {
                    "applications": [
                        {
                            "id": "p1:default:Deployment:api",
                            "status": "critical",
                            "category": "application",
                            "type": {"name": "golang"},
                            "cpu": {"status": "critical", "value": "95%"},
                            "memory": {"status": "ok", "value": "40%"},
                        },
                        {
                            "id": "p1:default:Deployment:web",
                            "status": "ok",
                            "category": "application",
                        },
                    ],
                    "categories": ["application"],
                }
            ),
        )
        result = await call(client, "list_applications")
        assert result["total"] == 2
        assert result["by_status"] == {"critical": 1, "ok": 1}
        first = result["applications"][0]
        assert first["type"] == "golang"
        assert first["issues"] == ["cpu: critical"]

        filtered = await call(client, "list_applications", status="ok")
        assert [a["id"] for a in filtered["applications"]] == [
            "p1:default:Deployment:web"
        ]


async def test_get_application_extracts_failing_checks(
    one_project: FakeCoroot, settings: Settings
) -> None:
    async with make_client(one_project, settings) as client:
        one_project.on(
            "GET",
            "/api/project/p1/app/p1%3Adefault%3ADeployment%3Aapi",
            enveloped(
                {
                    "app_map": {
                        "application": {
                            "id": "p1:default:Deployment:api",
                            "status": "warning",
                        },
                        "dependencies": [
                            {"id": "p1:default:StatefulSet:db", "status": "ok"}
                        ],
                    },
                    "reports": [
                        {
                            "name": "SLO",
                            "status": "warning",
                            "checks": [
                                {"title": "Availability", "status": "ok"},
                                {
                                    "title": "Latency",
                                    "status": "warning",
                                    "message": "p99 high",
                                },
                            ],
                            "widgets": [
                                {"chart": {"series": [{"name": "p99", "data": [1, 5]}]}}
                            ],
                        },
                        {"name": "CPU", "status": "ok", "checks": []},
                    ],
                }
            ),
        )
        result = await call(client, "get_application", app_id="default:Deployment:api")
        assert result["status"] == "warning"
        assert result["failing_checks"] == [
            {
                "report": "SLO",
                "check": "Latency",
                "status": "warning",
                "message": "p99 high",
            }
        ]
        assert result["report_names"] == ["SLO", "CPU"]
        # Chart data must be summarised, never returned raw.
        chart = result["reports"][0]["widgets"][0]["chart"]
        assert chart["series"][0]["max"] == 5.0

        single = await call(
            client, "get_application", app_id="default:Deployment:api", report="cpu"
        )
        assert [r["name"] for r in single["reports"]] == ["CPU"]

        missing = await call(
            client, "get_application", app_id="default:Deployment:api", report="Redis"
        )
        assert missing["available_reports"] == ["SLO", "CPU"]


async def test_nodes_and_deployments(
    one_project: FakeCoroot, settings: Settings
) -> None:
    async with make_client(one_project, settings) as client:
        one_project.on(
            "GET",
            "/api/project/p1/overview/nodes",
            enveloped(
                {
                    "nodes": [
                        {
                            "name": "node-1",
                            "status": {"status": "ok"},
                            "cpu_percent": 42,
                            "memory_percent": 71,
                            "instance_type": "m5.large",
                        }
                    ]
                }
            ),
        )
        nodes = await call(client, "list_nodes")
        assert nodes["nodes"][0]["cpu_percent"] == 42
        assert nodes["by_status"] == {"ok": 1}

        one_project.on(
            "GET",
            "/api/project/p1/overview/deployments",
            enveloped(
                {
                    "deployments": [
                        {
                            "application": {"id": "p1:default:Deployment:api"},
                            "version": "v2",
                            "status": "warning",
                            "summary": [{"status": "warning", "message": "latency up"}],
                        }
                    ]
                }
            ),
        )
        deployments = await call(client, "list_deployments")
        assert deployments["deployments"][0]["version"] == "v2"


async def test_risks_filter_dismissed(
    one_project: FakeCoroot, settings: Settings
) -> None:
    async with make_client(one_project, settings) as client:
        one_project.on(
            "GET",
            "/api/project/p1/overview/risks",
            enveloped(
                {
                    "risks": [
                        {
                            "application_id": "p1:default:Deployment:api",
                            "key": {
                                "category": "Availability",
                                "type": "single-instance-app",
                            },
                            "severity": "warning",
                        },
                        {
                            "application_id": "p1:default:Deployment:web",
                            "key": {
                                "category": "Security",
                                "type": "db-internet-exposure",
                            },
                            "dismissal": {"by": "sre", "reason": "internal only"},
                        },
                    ]
                }
            ),
        )
        active = await call(client, "list_risks")
        assert active["count"] == 1
        everything = await call(client, "list_risks", include_dismissed=True)
        assert everything["count"] == 2

    # -- telemetry ---------------------------------------------------------------


async def test_get_logs_across_project(
    one_project: FakeCoroot, settings: Settings
) -> None:
    async with make_client(one_project, settings) as client:
        one_project.on(
            "GET",
            "/api/project/p1/overview/logs",
            enveloped(
                {
                    "logs": {
                        "entries": [
                            {
                                "timestamp": 1704067200000,
                                "severity": "error",
                                "message": "connection refused",
                                "application": "p1:default:Deployment:api",
                            }
                        ],
                        "max_ts": "1704067200000000000",
                    }
                }
            ),
        )
        result = await call(client, "get_logs", severity=["error"], search="refused")
        assert result["entries"][0]["timestamp"] == "2024-01-01T00:00:00Z"
        assert result["next_since"] == "1704067200000000000"
        query = json.loads(dict(one_project.last.url.params)["query"])
        assert {"name": "Severity", "op": "=", "value": "error"} in query["filters"]
        assert {"name": "Message", "op": "contains", "value": "refused"} in query[
            "filters"
        ]


async def test_get_logs_rejects_unknown_severity(
    one_project: FakeCoroot, settings: Settings
) -> None:
    async with make_client(one_project, settings) as client:
        message = await call_error(client, "get_logs", severity=["catastrophe"])
        assert "unknown severity" in message


async def test_log_patterns_sorted_by_volume(
    one_project: FakeCoroot, settings: Settings
) -> None:
    async with make_client(one_project, settings) as client:
        one_project.on(
            "GET",
            "/api/project/p1/app/p1%3Adefault%3ADeployment%3Aapi/logs",
            enveloped(
                {
                    "patterns": [
                        {
                            "severity": "info",
                            "sum": 5,
                            "sample": "started",
                            "hash": "h1",
                        },
                        {
                            "severity": "error",
                            "sum": 90,
                            "sample": "timeout",
                            "hash": "h2",
                        },
                    ]
                }
            ),
        )
        result = await call(client, "get_log_patterns", app_id="default:Deployment:api")
        assert [p["count"] for p in result["patterns"]] == [90, 5]


async def test_traces_and_errors(one_project: FakeCoroot, settings: Settings) -> None:
    async with make_client(one_project, settings) as client:
        one_project.on(
            "GET",
            "/api/project/p1/overview/traces",
            enveloped(
                {
                    "traces": {
                        "summary": {
                            "stats": [
                                {
                                    "service_name": "checkout",
                                    "span_name": "GET /cart",
                                    "total": 100,
                                    "failed": 5,
                                }
                            ]
                        }
                    }
                }
            ),
        )
        result = await call(client, "get_traces", service="checkout")
        assert result["endpoints"][0]["span_name"] == "GET /cart"
        query = json.loads(dict(one_project.last.url.params)["query"])
        assert query["view"] == "summary"
        assert query["filters"][0]["value"] == "checkout"


async def test_trace_latency_reduces_flamegraph(
    one_project: FakeCoroot, settings: Settings
) -> None:
    async with make_client(one_project, settings) as client:
        one_project.on(
            "GET",
            "/api/project/p1/overview/traces",
            enveloped(
                {
                    "traces": {
                        "latency": {
                            "flamegraph": {
                                "name": "root",
                                "total": 100,
                                "children": [
                                    {"name": "db.query", "total": 80},
                                    {"name": "render", "total": 20},
                                ],
                            }
                        }
                    }
                }
            ),
        )
        result = await call(client, "get_trace_latency", slower_than="2s")
        assert result["band"]["slower_than_seconds"] == 2.0
        assert result["hotspots"]["hottest"][0]["name"] == "db.query"


async def test_profile_reduces_to_hotspots(
    one_project: FakeCoroot, settings: Settings
) -> None:
    async with make_client(one_project, settings) as client:
        one_project.on(
            "GET",
            "/api/project/p1/app/p1%3Adefault%3ADeployment%3Aapi/profiling",
            enveloped(
                {
                    "status": "ok",
                    "profile": {
                        "type": "go:profile_cpu:nanoseconds",
                        "flamegraph": {
                            "name": "root",
                            "total": 1000,
                            "children": [{"name": "json.Marshal", "total": 900}],
                        },
                    },
                }
            ),
        )
        result = await call(client, "get_profile", app_id="default:Deployment:api")
        assert result["hotspots"]["hottest"][0]["name"] == "json.Marshal"
        assert dict(one_project.last.url.params)["query"] == "cpu"


async def test_metrics_query_and_discovery(
    one_project: FakeCoroot, settings: Settings
) -> None:
    async with make_client(one_project, settings) as client:
        one_project.on(
            "GET",
            "/api/project/p1/panel/data",
            {
                "chart": {
                    "ctx": {"from": 1, "to": 2, "step": 30},
                    "series": [{"name": "api", "data": [1.0, 3.0, 2.0]}],
                }
            },
        )
        result = await call(client, "get_metrics", query="up")
        assert result["series"][0]["avg"] == 2.0
        assert result["series_count"] == 1

        one_project.on(
            "GET",
            "/api/project/p1/prom/api/v1/label/__name__/values",
            {"status": "success", "data": ["up", "node_cpu_seconds_total"]},
        )
        names = await call(client, "list_metrics", match="up.*")
        assert names["metrics"] == ["node_cpu_seconds_total", "up"]

    # -- incidents and alerts ----------------------------------------------------


async def test_incidents_and_alerts(
    one_project: FakeCoroot, settings: Settings
) -> None:
    async with make_client(one_project, settings) as client:
        one_project.on(
            "GET",
            "/api/project/p1/incidents",
            enveloped(
                [
                    {
                        "key": "inc1",
                        "application_id": "p1:default:Deployment:api",
                        "severity": "critical",
                        "opened_at": 1704067200000,
                        "resolved_at": None,
                        "short_description": "High latency",
                    },
                    {
                        "key": "inc2",
                        "application_id": "p1:default:Deployment:web",
                        "severity": "warning",
                        "opened_at": 1704060000000,
                        "resolved_at": 1704063600000,
                    },
                ]
            ),
        )
        everything = await call(client, "list_incidents")
        assert everything["matched"] == 2
        assert everything["open_in_scan"] == 1
        open_only = await call(client, "list_incidents", state_filter="open")
        assert [i["key"] for i in open_only["incidents"]] == ["inc1"]
        assert open_only["incidents"][0]["opened_at"] == "2024-01-01T00:00:00Z"

        one_project.on(
            "GET",
            "/api/project/p1/alerts",
            enveloped(
                {
                    "alerts": [
                        {
                            "id": "a1",
                            "rule_name": "CPU",
                            "severity": "critical",
                            "summary": "cpu high",
                            "opened_at": 1704067200000,
                            "resolved_at": None,
                        }
                    ],
                    "total": 1,
                    "firing": 1,
                    "resolved": 0,
                }
            ),
        )
        alerts = await call(client, "list_alerts")
        assert alerts["alerts"][0]["firing"] is True
        assert alerts["by_severity"] == {"critical": 1}
        assert alerts["project_totals"] == {"firing": 1, "resolved": 0, "total": 1}

        one_project.on("POST", "/api/project/p1/alerts/resolve", status=204)
        resolved = await call(client, "resolve_alerts", alert_ids=["a1"])
        assert resolved["ok"] is True
        assert one_project.body(one_project.last) == {"ids": ["a1"]}


async def test_state_filter_validation(
    one_project: FakeCoroot, settings: Settings
) -> None:
    async with make_client(one_project, settings) as client:
        message = await call_error(client, "list_alerts", state_filter="exploding")
        assert "state_filter must be one of" in message


async def test_alerting_rule_lifecycle(
    one_project: FakeCoroot, settings: Settings
) -> None:
    async with make_client(one_project, settings) as client:
        one_project.on(
            "GET",
            "/api/project/p1/alerting-rules",
            enveloped(
                {
                    "rules": [
                        {
                            "id": "r1",
                            "name": "CPU",
                            "severity": "warning",
                            "enabled": True,
                            "builtin": True,
                            "source": {"type": "check"},
                            "selector": {"type": "all"},
                        }
                    ],
                    "alert_counts": {"r1": 3},
                }
            ),
        )
        rules = await call(client, "list_alerting_rules")
        assert rules["rules"][0]["alerts"] == 3

        rule = {"name": "disk", "severity": "critical", "enabled": True}
        one_project.on("POST", "/api/project/p1/alerting-rules", {"id": "r2", **rule})
        created = await call(client, "create_alerting_rule", rule=rule)
        assert created["rule_id"] == "r2"

        one_project.on("DELETE", "/api/project/p1/alerting-rules/r2", status=204)
        assert (await call(client, "delete_alerting_rule", rule_id="r2"))["ok"] is True

    # -- configuration and dashboards -------------------------------------------


async def test_inspection_config_scope(
    one_project: FakeCoroot, settings: Settings
) -> None:
    async with make_client(one_project, settings) as client:
        one_project.on(
            "GET",
            "/api/project/p1/app/%3A%3A/inspection/CPUContainer/config",
            {"form": {"configs": [{"threshold": 80}, None]}},
        )
        result = await call(client, "get_inspection_config", check_id="CPUContainer")
        assert result["scope"] == "project"
        assert result["form"]["configs"][0]["threshold"] == 80

        message = await call_error(
            client, "get_inspection_config", check_id="NotACheck"
        )
        assert "check_id must be one of" in message


async def test_integration_configure_and_test(
    one_project: FakeCoroot, settings: Settings
) -> None:
    async with make_client(one_project, settings) as client:
        one_project.on("PUT", "/api/project/p1/integrations/slack")
        saved = await call(
            client,
            "configure_integration",
            integration_type="slack",
            config={"token": "xoxb", "default_channel": "ops"},
        )
        assert saved["type"] == "slack"
        assert one_project.last.method == "PUT"

        one_project.on("POST", "/api/project/p1/integrations/slack")
        tested = await call(
            client,
            "configure_integration",
            integration_type="slack",
            config={"token": "xoxb", "default_channel": "ops"},
            test_only=True,
        )
        assert "test succeeded" in tested["message"]
        assert one_project.last.method == "POST"


async def test_db_instrumentation_defaults_port(
    one_project: FakeCoroot, settings: Settings
) -> None:
    async with make_client(one_project, settings) as client:
        one_project.on(
            "POST",
            "/api/project/p1/app/p1%3Adefault%3AStatefulSet%3Adb/instrumentation/postgres",
        )
        await call(
            client,
            "configure_db_instrumentation",
            app_id="default:StatefulSet:db",
            db_type="postgres",
            username="coroot",
            password="secret",
        )
        body = one_project.body(one_project.last)
        assert body["port"] == "5432"
        assert body["credentials"] == {"username": "coroot", "password": "secret"}


async def test_dashboard_panels_roundtrip(
    one_project: FakeCoroot, settings: Settings
) -> None:
    async with make_client(one_project, settings) as client:
        one_project.on(
            "GET",
            "/api/project/p1/dashboards/d1",
            enveloped({"id": "d1", "name": "Redis", "config": {"groups": []}}),
        )
        one_project.on("POST", "/api/project/p1/dashboards/d1")
        config = {"groups": [{"name": "Latency", "panels": []}]}
        result = await call(
            client, "update_dashboard_panels", dashboard_id="d1", config=config
        )
        assert result["groups"] == 1
        body = one_project.body(one_project.last)
        assert body["name"] == "Redis"
        assert body["config"] == config

    # -- error handling ----------------------------------------------------------


async def test_coroot_errors_become_tool_errors(
    one_project: FakeCoroot, settings: Settings
) -> None:
    async with make_client(one_project, settings) as client:
        one_project.on(
            "GET",
            "/api/project/p1/app/p1%3Adefault%3ADeployment%3Aghost",
            status=404,
            text="Application not found",
        )
        message = await call_error(
            client, "get_application", app_id="default:Deployment:ghost"
        )
        assert "Application not found" in message
        assert "list_applications" in message  # actionable next step


async def test_permission_errors_explain_themselves(
    one_project: FakeCoroot, settings: Settings
) -> None:
    async with make_client(one_project, settings) as client:
        one_project.on(
            "GET", "/api/users", status=403, text="You are not allowed to edit users."
        )
        message = await call_error(client, "list_users")
        assert "not allowed to edit users" in message
        assert "role" in message


async def test_invalid_application_id_is_reported(
    one_project: FakeCoroot, settings: Settings
) -> None:
    async with make_client(one_project, settings) as client:
        message = await call_error(client, "get_application", app_id="just-a-name")
        assert "invalid application id" in message


async def test_large_responses_are_truncated(fake: FakeCoroot) -> None:
    settings = Settings(
        base_url="http://coroot.test",
        username="admin",
        password="secret",
        default_project="p1",
        max_output_chars=3_000,
    )
    fake.on("GET", "/api/user", {"projects": [{"id": "p1", "name": "prod"}]})
    fake.on(
        "GET",
        "/api/project/p1/overview/applications",
        enveloped(
            {
                "applications": [
                    {
                        "id": f"p1:default:Deployment:app-{i}",
                        "status": "ok",
                        "category": "application",
                    }
                    for i in range(400)
                ]
            }
        ),
    )
    async with make_client(fake, settings) as client:
        result = await call(client, "list_applications")
    assert result["total"] == 400
    assert "truncated" in result
    assert len(json.dumps(result)) <= 3_000
