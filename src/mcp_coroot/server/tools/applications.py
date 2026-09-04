"""Tools for applications, nodes, deployments, risks and costs."""

from __future__ import annotations

from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from ...client.ids import normalize_app_id
from ...config import Settings
from ..app import READ_ONLY, WRITE
from ..compact import compact, limit_items, status_counts
from ..errors import guard, one_of
from ..state import AppState, ToolContext
from ._common import AppIdParam, FromParam, ProjectIdParam, ToParam, ok, respond, target

LimitParam = Annotated[
    int, Field(description="Maximum items to return.", ge=1, le=1000)
]


def _app_digest(app: dict[str, Any]) -> dict[str, Any]:
    """Keep the triage-relevant fields of an overview application entry."""
    issues = [
        f"{name}: {value.get('status')}"
        for name, value in app.items()
        if isinstance(value, dict)
        and value.get("status") in {"warning", "critical"}
        and name not in {"type"}
    ]
    app_type = app.get("type")
    return {
        "id": app.get("id"),
        "category": app.get("category"),
        "cluster": app.get("cluster"),
        "status": app.get("status"),
        "type": app_type.get("name") if isinstance(app_type, dict) else app_type,
        "issues": issues or None,
    }


def register(mcp: MCPServer[AppState], settings: Settings) -> None:
    @mcp.tool(title="List applications", annotations=READ_ONLY)
    @guard
    async def list_applications(
        ctx: ToolContext,
        project_id: ProjectIdParam = None,
        status: Annotated[
            str | None,
            Field(
                description=(
                    "Only return applications at this status: 'ok', 'info', "
                    "'warning', 'critical' or 'unknown'. Omit for all."
                )
            ),
        ] = None,
        category: Annotated[
            str | None,
            Field(
                description=(
                    "Only return applications in this category, e.g. 'application'."
                )
            ),
        ] = None,
        from_time: FromParam = None,
        to_time: ToParam = None,
        limit: LimitParam = 200,
    ) -> dict[str, Any]:
        """List applications with their health and failing inspections.

        The starting point for triage: it shows which applications are warning or
        critical and why. Drill into one with get_application.
        """
        state, pid = await target(ctx, project_id)
        result = await state.coroot.overview.applications(
            pid, from_=from_time, to=to_time
        )
        apps = [a for a in (result.data or []) if isinstance(a, dict)]
        digests = [_app_digest(a) for a in apps]
        if status:
            wanted = status.strip().lower()
            digests = [a for a in digests if a.get("status") == wanted]
        if category:
            digests = [a for a in digests if a.get("category") == category.strip()]
        kept, omitted = limit_items(digests, limit)
        return respond(
            state,
            {
                "project_id": pid,
                "total": len(apps),
                "returned": len(kept),
                "omitted": omitted or None,
                "by_status": status_counts(apps),
                "categories": result.context.get("categories") or [],
                "applications": kept,
            },
        )

    @mcp.tool(title="Get application details", annotations=READ_ONLY)
    @guard
    async def get_application(
        ctx: ToolContext,
        app_id: AppIdParam,
        project_id: ProjectIdParam = None,
        report: Annotated[
            str | None,
            Field(
                description=(
                    "Return only this audit report, e.g. 'SLO', 'CPU', 'Memory', "
                    "'Postgres', 'Logs', 'Instances', 'Net'. Omit for all reports, "
                    "which is a much larger response."
                )
            ),
        ] = None,
        from_time: FromParam = None,
        to_time: ToParam = None,
        incident: Annotated[
            str | None,
            Field(
                description=(
                    "Incident key from list_incidents. Sets the window to that "
                    "incident and overrides from_time/to_time."
                )
            ),
        ] = None,
    ) -> dict[str, Any]:
        """Get one application's health: audit reports, failing checks and dependencies.

        Each report covers one aspect (SLO, CPU, Memory, Postgres, Logs, ...) and
        carries checks with their thresholds. Pass `report` to look at a single
        aspect; the full response is large.
        """
        state, pid = await target(ctx, project_id)
        result = await state.coroot.applications.get(
            pid, app_id, from_=from_time, to=to_time, incident=incident
        )
        data = result.data if isinstance(result.data, dict) else {}
        reports = [r for r in (data.get("reports") or []) if isinstance(r, dict)]
        if report:
            wanted = report.strip().lower()
            reports = [r for r in reports if str(r.get("name", "")).lower() == wanted]
            if not reports:
                available = [str(r.get("name")) for r in (data.get("reports") or [])]
                return respond(
                    state,
                    {
                        "project_id": pid,
                        "application_id": normalize_app_id(app_id, project_id=pid),
                        "error": f"No report named {report!r}",
                        "available_reports": available,
                    },
                )
        app_map = data.get("app_map") or {}
        application = app_map.get("application") if isinstance(app_map, dict) else {}
        failing = [
            {
                "report": r.get("name"),
                "check": c.get("title"),
                "status": c.get("status"),
                "message": c.get("message"),
            }
            for r in reports
            for c in (r.get("checks") or [])
            if isinstance(c, dict) and c.get("status") in {"warning", "critical"}
        ]
        return respond(
            state,
            {
                "project_id": pid,
                "application_id": normalize_app_id(app_id, project_id=pid),
                "status": (application or {}).get("status"),
                "indicators": (application or {}).get("indicators"),
                "instances": app_map.get("instances")
                if isinstance(app_map, dict)
                else None,
                "dependencies": app_map.get("dependencies")
                if isinstance(app_map, dict)
                else None,
                "clients": app_map.get("clients")
                if isinstance(app_map, dict)
                else None,
                "failing_checks": failing,
                "report_names": [r.get("name") for r in (data.get("reports") or [])],
                "reports": compact(reports),
            },
        )

    @mcp.tool(title="Get the service map", annotations=READ_ONLY)
    @guard
    async def get_service_map(
        ctx: ToolContext,
        project_id: ProjectIdParam = None,
        from_time: FromParam = None,
        to_time: ToParam = None,
    ) -> dict[str, Any]:
        """Get the dependency graph: which applications call which, and their health.

        Use it to trace a failure from a symptom to its upstream cause.
        """
        state, pid = await target(ctx, project_id)
        result = await state.coroot.overview.service_map(
            pid, from_=from_time, to=to_time
        )
        apps = [a for a in (result.data or []) if isinstance(a, dict)]
        edges = [
            {
                "id": app.get("id"),
                "status": app.get("status"),
                "category": app.get("category"),
                "upstreams": [
                    {"id": u.get("id"), "status": u.get("status")}
                    for u in (app.get("upstreams") or [])
                    if isinstance(u, dict)
                ],
            }
            for app in apps
        ]
        return respond(
            state,
            {"project_id": pid, "count": len(edges), "applications": edges},
        )

    @mcp.tool(title="List nodes", annotations=READ_ONLY)
    @guard
    async def list_nodes(
        ctx: ToolContext,
        project_id: ProjectIdParam = None,
        from_time: FromParam = None,
        to_time: ToParam = None,
    ) -> dict[str, Any]:
        """List hosts with status, CPU and memory utilisation and instance type."""
        state, pid = await target(ctx, project_id)
        result = await state.coroot.overview.nodes(pid, from_=from_time, to=to_time)
        nodes = [n for n in (result.data or []) if isinstance(n, dict)]
        digests = [
            {
                "name": n.get("name"),
                "cluster": n.get("cluster_name"),
                "status": (n.get("status") or {}).get("status")
                if isinstance(n.get("status"), dict)
                else n.get("status"),
                "cpu_percent": n.get("cpu_percent"),
                "memory_percent": n.get("memory_percent"),
                "instance_type": n.get("instance_type"),
                "availability_zone": n.get("availability_zone"),
                "cloud_provider": n.get("cloud_provider"),
                "os": n.get("os"),
            }
            for n in nodes
        ]
        return respond(
            state,
            {
                "project_id": pid,
                "count": len(digests),
                "by_status": status_counts(nodes),
                "nodes": digests,
            },
        )

    @mcp.tool(title="Get node details", annotations=READ_ONLY)
    @guard
    async def get_node(
        ctx: ToolContext,
        node: Annotated[str, Field(description="Node name from list_nodes.")],
        project_id: ProjectIdParam = None,
        from_time: FromParam = None,
        to_time: ToParam = None,
    ) -> dict[str, Any]:
        """Get one host's audit report: CPU, memory, disk and network checks."""
        state, pid = await target(ctx, project_id)
        result = await state.coroot.nodes.get(pid, node, from_=from_time, to=to_time)
        data = result.data if isinstance(result.data, dict) else {}
        return respond(
            state,
            {
                "project_id": pid,
                "node": node,
                "status": data.get("status"),
                "checks": data.get("checks"),
                "report": compact(data),
            },
        )

    @mcp.tool(title="List deployments", annotations=READ_ONLY)
    @guard
    async def list_deployments(
        ctx: ToolContext,
        project_id: ProjectIdParam = None,
        from_time: FromParam = None,
        to_time: ToParam = None,
        limit: LimitParam = 50,
    ) -> dict[str, Any]:
        """List recent deployments and the impact Coroot measured for each.

        Use it to answer "what changed?" when a problem started at a known time;
        widen from_time to look further back.
        """
        state, pid = await target(ctx, project_id)
        result = await state.coroot.overview.deployments(
            pid, from_=from_time, to=to_time
        )
        deployments = [d for d in (result.data or []) if isinstance(d, dict)]
        digests = []
        for dep in deployments:
            application = dep.get("application") or {}
            digests.append(
                {
                    "application_id": application.get("id")
                    if isinstance(application, dict)
                    else None,
                    "version": dep.get("version"),
                    "deployed": dep.get("deployed"),
                    "age": dep.get("age"),
                    "status": dep.get("status"),
                    "summary": [
                        {"status": s.get("status"), "message": s.get("message")}
                        for s in (dep.get("summary") or [])
                        if isinstance(s, dict)
                    ],
                }
            )
        kept, omitted = limit_items(digests, limit)
        return respond(
            state,
            {
                "project_id": pid,
                "total": len(digests),
                "omitted": omitted or None,
                "deployments": kept,
            },
        )

    @mcp.tool(title="List risks", annotations=READ_ONLY)
    @guard
    async def list_risks(
        ctx: ToolContext,
        project_id: ProjectIdParam = None,
        include_dismissed: Annotated[
            bool, Field(description="Include risks somebody has dismissed.")
        ] = False,
        from_time: FromParam = None,
        to_time: ToParam = None,
    ) -> dict[str, Any]:
        """List availability and security risks Coroot detected.

        Covers single-instance or single-node applications, unreplicated
        databases, spot-only workloads and databases exposed to the internet.
        """
        state, pid = await target(ctx, project_id)
        result = await state.coroot.overview.risks(pid, from_=from_time, to=to_time)
        risks = [r for r in (result.data or []) if isinstance(r, dict)]
        if not include_dismissed:
            risks = [r for r in risks if not r.get("dismissal")]
        digests = [
            {
                "application_id": r.get("application_id"),
                "category": (r.get("key") or {}).get("category"),
                "type": (r.get("key") or {}).get("type"),
                "severity": r.get("severity"),
                "dismissed": bool(r.get("dismissal")),
                "exposure": r.get("exposure"),
                "availability": r.get("availability"),
            }
            for r in risks
        ]
        return respond(
            state,
            {"project_id": pid, "count": len(digests), "risks": digests},
        )

    @mcp.tool(title="Get cloud costs", annotations=READ_ONLY)
    @guard
    async def get_costs(
        ctx: ToolContext,
        project_id: ProjectIdParam = None,
        from_time: FromParam = None,
        to_time: ToParam = None,
        limit: LimitParam = 50,
    ) -> dict[str, Any]:
        """Get per-node and per-application cloud costs, including over-provisioning.

        Application entries include recommended CPU and memory requests, which is
        where most of the savings usually are.
        """
        state, pid = await target(ctx, project_id)
        result = await state.coroot.overview.costs(pid, from_=from_time, to=to_time)
        data = result.data if isinstance(result.data, dict) else {}
        nodes, nodes_omitted = limit_items(data.get("nodes") or [], limit)
        apps, apps_omitted = limit_items(data.get("applications") or [], limit)
        return respond(
            state,
            {
                "project_id": pid,
                "custom_pricing": data.get("custom_pricing"),
                "nodes": nodes,
                "nodes_omitted": nodes_omitted or None,
                "applications": apps,
                "applications_omitted": apps_omitted or None,
            },
        )

    @mcp.tool(title="Get AI root cause analysis", annotations=READ_ONLY)
    @guard
    async def get_application_rca(
        ctx: ToolContext,
        app_id: AppIdParam,
        project_id: ProjectIdParam = None,
        from_time: FromParam = None,
        to_time: ToParam = None,
    ) -> dict[str, Any]:
        """Ask Coroot for an AI root cause analysis of an application's problems.

        Requires a Coroot Cloud API key on the server; without one the response
        carries a status explaining that it is unconfigured. The result includes a
        summary, the suspected root cause, suggested fixes and a propagation map.
        """
        state, pid = await target(ctx, project_id)
        data = await state.coroot.applications.rca(
            pid, app_id, from_=from_time, to=to_time
        )
        payload = data if isinstance(data, dict) else {}
        return respond(
            state,
            {
                "project_id": pid,
                "application_id": normalize_app_id(app_id, project_id=pid),
                "status": payload.get("status"),
                "error": payload.get("error") or None,
                "summary": payload.get("short_summary"),
                "root_cause": payload.get("root_cause"),
                "immediate_fixes": payload.get("immediate_fixes"),
                "details": payload.get("detailed_root_cause_analysis"),
                "propagation_map": compact(payload.get("propagation_map")),
            },
        )

    if settings.read_only:
        return

    @mcp.tool(title="Dismiss or restore a risk", annotations=WRITE)
    @guard
    async def set_risk_status(
        ctx: ToolContext,
        app_id: AppIdParam,
        risk_category: Annotated[
            str,
            Field(
                description=(
                    "Risk category from list_risks: 'Availability' or 'Security'."
                )
            ),
        ],
        risk_type: Annotated[
            str,
            Field(
                description=(
                    "Risk type from list_risks, e.g. 'single-instance-app', "
                    "'unreplicated-database', 'db-internet-exposure'."
                )
            ),
        ],
        action: Annotated[
            str,
            Field(
                description=(
                    "'dismiss' to accept the risk, 'activate' to track it again."
                )
            ),
        ] = "dismiss",
        reason: Annotated[
            str,
            Field(
                description="Why the risk is being dismissed. Recorded with your name."
            ),
        ] = "",
        project_id: ProjectIdParam = None,
    ) -> dict[str, Any]:
        """Dismiss a detected risk as accepted, or bring a dismissed one back."""
        state, pid = await target(ctx, project_id)
        choice = one_of(action, ("dismiss", "activate"), name="action")
        await state.coroot.applications.set_risk_override(
            pid,
            app_id,
            action="dismiss" if choice == "dismiss" else "mark_as_active",
            category=risk_category,
            risk_type=risk_type,
            reason=reason,
        )
        return ok(
            f"Risk {risk_type} {'dismissed' if choice == 'dismiss' else 'reactivated'}",
            application_id=normalize_app_id(app_id, project_id=pid),
        )
