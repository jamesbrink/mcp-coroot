"""Tests for MCP resources and prompts."""

from __future__ import annotations

import json
from typing import Any

import httpx2 as httpx
from mcp import Client
from mcp.types import TextContent, TextResourceContents

from mcp_coroot.client import CorootClient
from mcp_coroot.config import Settings
from mcp_coroot.server import build_server
from tests.conftest import FakeCoroot


def make_client(fake: FakeCoroot, settings: Settings) -> Client:
    server = build_server(
        settings,
        client_factory=lambda s: CorootClient(s, transport=httpx.MockTransport(fake)),
    )
    return Client(server)


def resource_text(result: Any) -> str:
    contents = result.contents[0]
    assert isinstance(contents, TextResourceContents)
    return contents.text


async def test_reference_resource(fake: FakeCoroot, settings: Settings) -> None:
    async with make_client(fake, settings) as client:
        listed = await client.list_resources()
        uris = {str(r.uri) for r in listed.resources}
        assert "coroot://reference" in uris
        data = json.loads(
            resource_text(await client.read_resource("coroot://reference"))
        )
    assert data["application_id_format"]["pattern"] == "cluster_id:namespace:Kind:name"
    assert "CPUContainer" in data["check_ids"]
    assert "error" in data["log_severities"]


async def test_projects_resource(fake: FakeCoroot, settings: Settings) -> None:
    fake.on("GET", "/api/user", {"projects": [{"id": "p1", "name": "prod"}]})
    async with make_client(fake, settings) as client:
        data = json.loads(
            resource_text(await client.read_resource("coroot://projects"))
        )
    assert data["projects"] == [{"id": "p1", "name": "prod"}]
    assert data["base_url"] == "http://coroot.test"


async def test_applications_resource_template(
    fake: FakeCoroot, settings: Settings
) -> None:
    fake.on(
        "GET",
        "/api/project/p1/overview/applications",
        {
            "context": {"status": {}, "search": {}},
            "data": {
                "applications": [
                    {
                        "id": "p1:default:Deployment:api",
                        "status": "ok",
                        "category": "application",
                    }
                ]
            },
        },
    )
    async with make_client(fake, settings) as client:
        templates = await client.list_resource_templates()
        assert any(
            "applications" in str(t.uri_template) for t in templates.resource_templates
        )
        data = json.loads(
            resource_text(
                await client.read_resource("coroot://project/p1/applications")
            )
        )
    assert data["count"] == 1
    assert data["applications"][0]["id"] == "p1:default:Deployment:api"


async def test_prompts_are_listed_and_rendered(
    fake: FakeCoroot, settings: Settings
) -> None:
    async with make_client(fake, settings) as client:
        listed = await client.list_prompts()
        names = {p.name for p in listed.prompts}
        assert {
            "investigate_application",
            "triage_project",
            "review_incident",
            "review_costs",
        } <= names

        rendered = await client.get_prompt(
            "investigate_application",
            {"application": "p1:default:Deployment:api", "project": "p1"},
        )
        content = rendered.messages[0].content
        assert isinstance(content, TextContent)
        assert "p1:default:Deployment:api" in content.text
        assert "summarize_trace_endpoints" in content.text

        incident = await client.get_prompt("review_incident", {"incident_key": "inc1"})
        incident_content = incident.messages[0].content
        assert isinstance(incident_content, TextContent)
        assert "incident=inc1" in incident_content.text
