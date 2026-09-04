"""Tools for applications, nodes, deployments, risks and costs."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from ...client.ids import normalize_app_id
from ...config import Settings
from ..app import READ_ONLY, WRITE
from ..compact import compact, limit_items, status_counts
from ..errors import guard
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
            Literal["ok", "info", "warning", "critical", "unknown"] | None,
            Field(description="Only return applications at this status."),
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
            digests = [a for a in digests if a.get("status") == status]
        if category:
            digests = [a for a in digests if a.get("category") == category.strip()]
        kept, omitted = limit_items(digests, limit)
        return respond(
            state,
            {
                "project_id": pid,
                "total_in_project": len(apps),
                "matched": len(digests),
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
                    "Incident key from get_incidents. Sets the window to that "
                    "incident and overrides from_time/to_time."
                )
            ),
        ] = None,
    ) -> dict[str, Any]:
        """Get one application's health: failing checks, dependencies and clients.

        By default this returns the diagnosis — every failing check across every
        audit report — plus the names of the reports available. That answers
        "what is wrong with this application" without pulling the charts.

        Pass `report` to read one report in full (SLO, CPU, Memory, Postgres,
        Logs, Instances, Net, ...) when you need the numbers behind a check.
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
        payload: dict[str, Any] = {
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
            "clients": app_map.get("clients") if isinstance(app_map, dict) else None,
            "failing_checks": failing,
            "report_names": [r.get("name") for r in (data.get("reports") or [])],
        }
        if report:
            payload["reports"] = compact(reports)
        else:
            # Every report in full runs to tens of thousands of tokens, most of
            # it chart summaries for checks that are already passing.
            payload["note"] = (
                "Showing failing checks only. Call get_application again with "
                "report=<name> from report_names for one report's full detail."
            )
        return respond(state, payload)

    @mcp.tool(title="Get nodes", annotations=READ_ONLY)
    @guard
    async def get_nodes(
        ctx: ToolContext,
        project_id: ProjectIdParam = None,
        node: Annotated[
            str | None,
            Field(
                description=(
                    "Report one host in full: its CPU, memory, disk and network "
                    "checks. Omit to list every host."
                )
            ),
        ] = None,
        from_time: FromParam = None,
        to_time: ToParam = None,
    ) -> dict[str, Any]:
        """List hosts with their utilisation, or open one's audit report.

        Use the listing to spot a host that is down or saturated, then name it
        to see which of its checks are failing.
        """
        state, pid = await target(ctx, project_id)
        if node:
            result = await state.coroot.nodes.get(
                pid, node, from_=from_time, to=to_time
            )
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

        listed = await state.coroot.overview.nodes(pid, from_=from_time, to=to_time)
        nodes = [n for n in (listed.data or []) if isinstance(n, dict)]
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

    @mcp.tool(title="Get a project overview", annotations=READ_ONLY)
    @guard
    async def get_overview(
        ctx: ToolContext,
        view: Annotated[
            Literal["map", "deployments", "risks", "costs"],
            Field(
                description=(
                    "map: which applications call which, and their health. "
                    "deployments: recent rollouts and their measured impact. "
                    "risks: single-instance or unreplicated workloads and "
                    "exposed databases. costs: per-node and per-application "
                    "spend, with over-provisioning."
                )
            ),
        ],
        project_id: ProjectIdParam = None,
        include_dismissed: Annotated[
            bool,
            Field(description="For risks: include ones somebody has accepted."),
        ] = False,
        limit: Annotated[
            int, Field(description="Maximum entries to return.", ge=1, le=1000)
        ] = 50,
        from_time: FromParam = None,
        to_time: ToParam = None,
    ) -> dict[str, Any]:
        """Answer a project-wide question: dependencies, changes, risks or spend.

        Use `map` to trace a failure to its upstream cause, `deployments` to
        answer "what changed?" over a window that starts before the problem did,
        `risks` for availability and security exposure, and `costs` for
        over-provisioned workloads and idle capacity.
        """
        state, pid = await target(ctx, project_id)
        result = await state.coroot.overview.get(pid, view, from_=from_time, to=to_time)
        payload: dict[str, Any] = {"project_id": pid, "view": view}

        if view == "map":
            apps = [a for a in (result.data or []) if isinstance(a, dict)]
            payload["applications"] = [
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
            payload["count"] = len(apps)
            return respond(state, payload)

        if view == "deployments":
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
                            {"status": x.get("status"), "message": x.get("message")}
                            for x in (dep.get("summary") or [])
                            if isinstance(x, dict)
                        ],
                    }
                )
            kept, omitted = limit_items(digests, limit)
            payload |= {
                "count": len(digests),
                "omitted": omitted or None,
                "deployments": kept,
            }
            return respond(state, payload)

        if view == "risks":
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
            kept, omitted = limit_items(digests, limit)
            payload |= {
                "count": len(digests),
                "omitted": omitted or None,
                "risks": kept,
            }
            return respond(state, payload)

        data = result.data if isinstance(result.data, dict) else {}
        nodes, nodes_omitted = limit_items(data.get("nodes") or [], limit)
        apps_kept, apps_omitted = limit_items(data.get("applications") or [], limit)
        payload |= {
            "custom_pricing": data.get("custom_pricing"),
            "nodes": nodes,
            "nodes_omitted": nodes_omitted or None,
            "applications": apps_kept,
            "applications_omitted": apps_omitted or None,
        }
        return respond(state, payload)

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
                    "Risk category from get_overview(view='risks'): 'Availability' "
                    "or 'Security'."
                )
            ),
        ],
        risk_type: Annotated[
            str,
            Field(
                description=(
                    "Risk type from get_overview(view='risks'), e.g. "
                    "'single-instance-app', "
                    "'unreplicated-database', 'db-internet-exposure'."
                )
            ),
        ],
        action: Annotated[
            Literal["dismiss", "activate"],
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
        await state.coroot.applications.set_risk_override(
            pid,
            app_id,
            action="dismiss" if action == "dismiss" else "mark_as_active",
            category=risk_category,
            risk_type=risk_type,
            reason=reason,
        )
        return ok(
            f"Risk {risk_type} {'dismissed' if action == 'dismiss' else 'reactivated'}",
            application_id=normalize_app_id(app_id, project_id=pid),
        )
