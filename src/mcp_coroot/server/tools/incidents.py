"""Tools for incidents, alerts and alerting rules."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from ...client.ids import normalize_app_id
from ...client.timerange import ms_to_iso
from ...config import Settings
from ..app import CREATE, DESTRUCTIVE, READ_ONLY, WRITE
from ..compact import compact, limit_items, status_counts
from ..errors import guard
from ..state import AppState, ToolContext
from ._common import FromParam, ProjectIdParam, ToParam, ok, respond, target

#: Widest page this server will pull when it has to filter client-side.
MAX_SCAN = 1000

AlertIdsParam = Annotated[
    list[str], Field(description="Alert ids from list_alerts.", min_length=1)
]


def _incident_digest(incident: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": incident.get("key"),
        "application_id": incident.get("application_id"),
        "severity": incident.get("severity"),
        "opened_at": ms_to_iso(incident.get("opened_at")),
        "resolved_at": ms_to_iso(incident.get("resolved_at")),
        "open": incident.get("resolved_at") in (None, 0),
        "summary": incident.get("short_description"),
        "impact": incident.get("impact"),
        "category": incident.get("application_category"),
    }


def _is_firing(alert: dict[str, Any]) -> bool:
    """Whether Coroot considers an alert still firing.

    It counts an alert as resolved when it resolved itself, when somebody
    resolved it by hand, or when it was suppressed (``db/alert.go``), so all
    three have to be checked.
    """
    return not (
        (alert.get("resolved_at") or 0) > 0
        or (alert.get("manually_resolved_at") or 0) > 0
        or bool(alert.get("suppressed"))
    )


def _alert_digest(alert: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": alert.get("id"),
        "rule": alert.get("rule_name"),
        "application_id": alert.get("application_id"),
        "severity": alert.get("severity"),
        "summary": alert.get("summary"),
        "opened_at": ms_to_iso(alert.get("opened_at")),
        "resolved_at": ms_to_iso(
            alert.get("resolved_at") or alert.get("manually_resolved_at")
        ),
        "firing": _is_firing(alert),
        "suppressed": bool(alert.get("suppressed")),
        "resolved_by": alert.get("resolved_by") or None,
    }


def register(mcp: MCPServer[AppState], settings: Settings) -> None:
    @mcp.tool(title="List SLO incidents", annotations=READ_ONLY)
    @guard
    async def list_incidents(
        ctx: ToolContext,
        project_id: ProjectIdParam = None,
        state_filter: Annotated[
            Literal["open", "resolved", "any"],
            Field(description="Which incidents to return."),
        ] = "any",
        app_id: Annotated[
            str | None, Field(description="Only incidents for this application id.")
        ] = None,
        limit: Annotated[
            int, Field(description="Maximum incidents to return.", ge=1, le=500)
        ] = 50,
        from_time: FromParam = None,
        to_time: ToParam = None,
    ) -> dict[str, Any]:
        """List SLO incidents: availability or latency objectives being violated.

        Open incidents come first, then the most recent resolved ones. Use
        get_incident for the full analysis of one.
        """
        state, pid = await target(ctx, project_id)
        wanted = state_filter
        # Coroot filters neither by state nor by application, so a filtered
        # request has to scan more rows than it returns.
        filtering = wanted != "any" or app_id is not None
        scan = min(max(limit * 5, 200), MAX_SCAN) if filtering else limit
        result = await state.coroot.incidents.list(
            pid, limit=scan, from_=from_time, to=to_time
        )
        incidents = [i for i in (result.data or []) if isinstance(i, dict)]
        digests = [_incident_digest(i) for i in incidents]
        wanted_app = normalize_app_id(app_id, project_id=pid) if app_id else None
        matched = [
            d
            for d in digests
            if (wanted_app is None or d.get("application_id") == wanted_app)
            and (
                wanted == "any"
                or (wanted == "open" and d["open"])
                or (wanted == "resolved" and not d["open"])
            )
        ]
        kept, omitted = limit_items(matched, limit)
        return respond(
            state,
            {
                "project_id": pid,
                "scanned": len(digests),
                "matched": len(matched),
                "returned": len(kept),
                "omitted": omitted or None,
                "open_in_scan": sum(1 for d in digests if d["open"]),
                "incidents": kept,
                "note": (
                    f"Only {len(digests)} incidents were scanned (open ones "
                    "first, then most recent); older ones may also match. "
                    "Coroot does not filter incidents by time, so raise limit "
                    "rather than narrowing the window."
                )
                if filtering and len(digests) >= scan
                else None,
            },
        )

    @mcp.tool(title="Get incident details", annotations=READ_ONLY)
    @guard
    async def get_incident(
        ctx: ToolContext,
        incident_key: Annotated[
            str, Field(description="Incident key from list_incidents.")
        ],
        project_id: ProjectIdParam = None,
    ) -> dict[str, Any]:
        """Get one incident with its SLO breach details and root cause analysis.

        The time window is set to the incident automatically, so charts cover the
        right period.
        """
        state, pid = await target(ctx, project_id)
        result = await state.coroot.incidents.get(pid, incident_key)
        data = result.data if isinstance(result.data, dict) else {}
        rca = data.get("rca") or {}
        return respond(
            state,
            {
                "project_id": pid,
                **_incident_digest(data),
                "availability_slo": data.get("availability_slo"),
                "latency_slo": data.get("latency_slo"),
                "actual_from": ms_to_iso(data.get("actual_from")),
                "actual_to": ms_to_iso(data.get("actual_to")),
                "details": compact(data.get("details")),
                "rca": {
                    "status": rca.get("status"),
                    "summary": rca.get("short_summary"),
                    "root_cause": rca.get("root_cause"),
                    "immediate_fixes": rca.get("immediate_fixes"),
                }
                if isinstance(rca, dict) and rca
                else None,
            },
        )

    @mcp.tool(title="List alerts", annotations=READ_ONLY)
    @guard
    async def list_alerts(
        ctx: ToolContext,
        project_id: ProjectIdParam = None,
        state_filter: Annotated[
            Literal["firing", "resolved", "any"],
            Field(description="Which alerts to return."),
        ] = "firing",
        search: Annotated[
            str | None,
            Field(description="Substring match over summary, application id or rule."),
        ] = None,
        app_id: Annotated[
            str | None, Field(description="Only alerts for this application id.")
        ] = None,
        limit: Annotated[
            int, Field(description="Maximum alerts to return.", ge=1, le=1000)
        ] = 50,
        offset: Annotated[
            int,
            Field(
                description=(
                    "Skip this many alerts before returning any, to reach past "
                    "what an earlier call scanned."
                ),
                ge=0,
            ),
        ] = 0,
    ) -> dict[str, Any]:
        """List alerts raised by Coroot's alerting rules.

        Firing alerts are what needs attention now. Each entry carries the rule
        that produced it and the application it concerns.
        """
        state, pid = await target(ctx, project_id)
        wanted = state_filter
        # Coroot matches `search` against the application id server-side, which
        # is the only way to filter by application without scanning every page.
        # It cannot return resolved alerts alone, so that state is filtered here
        # and needs a wider scan than the caller asked for.
        server_search = normalize_app_id(app_id, project_id=pid) if app_id else search
        filtering = wanted == "resolved" or app_id is not None or search is not None
        scan = min(max(limit * 5, 200), MAX_SCAN) if filtering else limit
        result = await state.coroot.alerts.list(
            pid,
            include_resolved=wanted != "firing",
            search=server_search,
            limit=scan,
            offset=offset,
        )
        data = result.data if isinstance(result.data, dict) else {}
        alerts = [a for a in (data.get("alerts") or []) if isinstance(a, dict)]
        digests = [_alert_digest(a) for a in alerts]
        needle = (search or "").lower()
        wanted_app = normalize_app_id(app_id, project_id=pid) if app_id else None
        matched = [
            d
            for d in digests
            if (wanted_app is None or d.get("application_id") == wanted_app)
            and (
                wanted == "any"
                or (wanted == "firing" and d["firing"])
                or (wanted == "resolved" and not d["firing"])
            )
            and (
                not needle
                or needle in str(d.get("summary") or "").lower()
                or needle in str(d.get("rule") or "").lower()
                or needle in str(d.get("application_id") or "").lower()
            )
        ]
        kept, omitted = limit_items(matched, limit)
        return respond(
            state,
            {
                "project_id": pid,
                # Coroot computes these over the same search it applied, so
                # they are project-wide only when no filter was passed.
                "totals": {
                    "scope": "search" if server_search else "project",
                    "firing": data.get("firing"),
                    "resolved": data.get("resolved"),
                    "total": data.get("total"),
                },
                "scanned": len(digests),
                "matched": len(matched),
                "returned": len(kept),
                "omitted": omitted or None,
                "by_severity": status_counts(matched, key="severity"),
                "alerts": kept,
                "note": (
                    f"Only the {len(digests)} most recent alerts were scanned; "
                    "older ones may also match."
                )
                if filtering and len(digests) >= scan
                else None,
            },
        )

    @mcp.tool(title="Get alert details", annotations=READ_ONLY)
    @guard
    async def get_alert(
        ctx: ToolContext,
        alert_id: Annotated[str, Field(description="Alert id from list_alerts.")],
        project_id: ProjectIdParam = None,
    ) -> dict[str, Any]:
        """Get one alert with the details and charts behind it."""
        state, pid = await target(ctx, project_id)
        result = await state.coroot.alerts.get(pid, alert_id)
        data = result.data if isinstance(result.data, dict) else {}
        return respond(
            state,
            {
                "project_id": pid,
                **_alert_digest(data),
                "rule_id": data.get("rule_id"),
                "report": data.get("report"),
                "details": data.get("details"),
                "notifications": data.get("notifications"),
                "widgets": compact(data.get("widgets")),
            },
        )

    @mcp.tool(title="List alerting rules", annotations=READ_ONLY)
    @guard
    async def list_alerting_rules(
        ctx: ToolContext, project_id: ProjectIdParam = None
    ) -> dict[str, Any]:
        """List alerting rules, built-in and custom, with how many alerts each fired."""
        state, pid = await target(ctx, project_id)
        result = await state.coroot.alerting_rules.list(pid)
        data = result.data if isinstance(result.data, dict) else {}
        rules = [r for r in (data.get("rules") or []) if isinstance(r, dict)]
        counts = data.get("alert_counts") or {}
        digests = [
            {
                "id": r.get("id"),
                "name": r.get("name"),
                "severity": r.get("severity"),
                "enabled": r.get("enabled"),
                "builtin": r.get("builtin"),
                "readonly": r.get("readonly"),
                "source": (r.get("source") or {}).get("type"),
                "selector": (r.get("selector") or {}).get("type"),
                "alerts": counts.get(str(r.get("id")))
                if isinstance(counts, dict)
                else None,
            }
            for r in rules
        ]
        return respond(
            state,
            {
                "project_id": pid,
                "count": len(digests),
                "checks": data.get("checks"),
                "rules": digests,
            },
        )

    @mcp.tool(title="Get an alerting rule", annotations=READ_ONLY)
    @guard
    async def get_alerting_rule(
        ctx: ToolContext,
        rule_id: Annotated[str, Field(description="Rule id from list_alerting_rules.")],
        project_id: ProjectIdParam = None,
    ) -> dict[str, Any]:
        """Get one alerting rule's full definition, including its condition."""
        state, pid = await target(ctx, project_id)
        rule = await state.coroot.alerting_rules.get(pid, rule_id)
        return respond(state, {"project_id": pid, **rule})

    @mcp.tool(title="Export alerting rules", annotations=READ_ONLY)
    @guard
    async def export_alerting_rules(
        ctx: ToolContext, project_id: ProjectIdParam = None
    ) -> dict[str, Any]:
        """Export every alerting rule as YAML for Coroot's configuration file."""
        state, pid = await target(ctx, project_id)
        yaml = await state.coroot.alerting_rules.export(pid)
        return respond(state, {"project_id": pid, "yaml": yaml})

    # Acting on alerts and editing rules belong to the alerts group.
    if settings.read_only or not settings.enabled("alerts"):
        return

    @mcp.tool(title="Resolve alerts", annotations=DESTRUCTIVE)
    @guard
    async def resolve_alerts(
        ctx: ToolContext,
        alert_ids: AlertIdsParam,
        project_id: ProjectIdParam = None,
    ) -> dict[str, Any]:
        """Mark alerts as resolved, notifying the configured channels.

        Only do this once the underlying problem is actually fixed: an alert whose
        condition still holds fires again at the next evaluation.
        """
        state, pid = await target(ctx, project_id)
        await state.coroot.alerts.resolve(pid, alert_ids)
        return ok(f"Resolved {len(alert_ids)} alert(s)", project_id=pid)

    @mcp.tool(title="Suppress alerts", annotations=DESTRUCTIVE)
    @guard
    async def suppress_alerts(
        ctx: ToolContext,
        alert_ids: AlertIdsParam,
        project_id: ProjectIdParam = None,
    ) -> dict[str, Any]:
        """Silence alerts without resolving them, for known or planned conditions."""
        state, pid = await target(ctx, project_id)
        await state.coroot.alerts.suppress(pid, alert_ids)
        return ok(f"Suppressed {len(alert_ids)} alert(s)", project_id=pid)

    @mcp.tool(title="Reopen alerts", annotations=WRITE)
    @guard
    async def reopen_alerts(
        ctx: ToolContext,
        alert_ids: AlertIdsParam,
        project_id: ProjectIdParam = None,
    ) -> dict[str, Any]:
        """Reopen alerts that were resolved or suppressed too early."""
        state, pid = await target(ctx, project_id)
        await state.coroot.alerts.reopen(pid, alert_ids)
        return ok(f"Reopened {len(alert_ids)} alert(s)", project_id=pid)

    @mcp.tool(title="Create an alerting rule", annotations=CREATE)
    @guard
    async def create_alerting_rule(
        ctx: ToolContext,
        rule: Annotated[
            dict[str, Any],
            Field(
                description=(
                    "Rule definition. Required: name, severity ('warning' or "
                    "'critical'), enabled, source and selector. source is "
                    '{"type": "check", "check": {"check_id": "CPUContainer"}} or '
                    '{"type": "promql", "promql": {"expression": "..."}} or '
                    '{"type": "log_patterns", ...} or '
                    '{"type": "kubernetes_events", ...}. selector is '
                    '{"type": "all"} or {"type": "category", "categories": [...]} '
                    'or {"type": "applications", "application_id_patterns": '
                    '["namespace:Kind:name"]}. Optional: for and keep_firing_for '
                    '(e.g. "5m"), templates {summary, description}.'
                )
            ),
        ],
        project_id: ProjectIdParam = None,
    ) -> dict[str, Any]:
        """Create a custom alerting rule.

        Look at an existing rule with get_alerting_rule first to copy its shape.
        """
        state, pid = await target(ctx, project_id)
        created = await state.coroot.alerting_rules.create(pid, rule)
        rule_id = created.get("id") if isinstance(created, dict) else None
        return ok("Created alerting rule", project_id=pid, rule_id=rule_id)

    @mcp.tool(title="Update an alerting rule", annotations=DESTRUCTIVE)
    @guard
    async def update_alerting_rule(
        ctx: ToolContext,
        rule_id: Annotated[str, Field(description="Rule id from list_alerting_rules.")],
        rule: Annotated[
            dict[str, Any],
            Field(
                description=(
                    "The complete rule definition, as returned by "
                    "get_alerting_rule with your changes applied. Fields left out "
                    "are cleared."
                )
            ),
        ],
        project_id: ProjectIdParam = None,
    ) -> dict[str, Any]:
        """Update an alerting rule, or enable and disable a built-in one.

        Fetch the current definition with get_alerting_rule, change what you need
        and send the whole object back.
        """
        state, pid = await target(ctx, project_id)
        await state.coroot.alerting_rules.update(pid, rule_id, rule)
        return ok(f"Updated rule {rule_id}", project_id=pid, rule_id=rule_id)

    @mcp.tool(title="Delete an alerting rule", annotations=DESTRUCTIVE)
    @guard
    async def delete_alerting_rule(
        ctx: ToolContext,
        rule_id: Annotated[str, Field(description="Rule id from list_alerting_rules.")],
        project_id: ProjectIdParam = None,
    ) -> dict[str, Any]:
        """Delete a custom alerting rule and resolve the alerts it raised.

        Built-in rules cannot be deleted; disable them with update_alerting_rule.
        """
        state, pid = await target(ctx, project_id)
        await state.coroot.alerting_rules.delete(pid, rule_id)
        return ok(f"Deleted rule {rule_id}", project_id=pid, rule_id=rule_id)
