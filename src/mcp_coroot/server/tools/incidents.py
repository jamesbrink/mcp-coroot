"""Tools for incidents, alerts and alerting rules."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from ...client.ids import normalize_app_id
from ...client.timerange import ms_to_iso
from ...config import Settings
from ..app import DESTRUCTIVE, READ_ONLY, WRITE
from ..compact import compact, limit_items, status_counts
from ..errors import guard
from ..state import AppState, ToolContext
from ._common import FromParam, ProjectIdParam, ToParam, ok, respond, target

#: Widest page this server will pull when it has to filter client-side.
MAX_SCAN = 1000

AlertIdsParam = Annotated[
    list[str], Field(description="Alert ids from get_alerts.", min_length=1)
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
    @mcp.tool(title="Get SLO incidents", annotations=READ_ONLY)
    @guard
    async def get_incidents(
        ctx: ToolContext,
        project_id: ProjectIdParam = None,
        incident_key: Annotated[
            str | None,
            Field(
                description=(
                    "Open one incident in full, with its SLO breach detail and "
                    "root cause analysis. Omit to list them."
                )
            ),
        ] = None,
        state_filter: Annotated[
            Literal["open", "resolved", "any"],
            Field(description="Which incidents to list."),
        ] = "any",
        app_id: Annotated[
            str | None, Field(description="Only incidents for this application id.")
        ] = None,
        limit: Annotated[
            int, Field(description="Maximum incidents to list.", ge=1, le=500)
        ] = 50,
        from_time: FromParam = None,
        to_time: ToParam = None,
    ) -> dict[str, Any]:
        """List SLO incidents, or open one by key.

        An incident is an availability or latency objective being violated. Open
        ones are listed first, then the most recent resolved. Pass incident_key
        for the full analysis of one: its burn rates, the SLO it broke, and
        Coroot's root cause analysis if it ran.
        """
        state, pid = await target(ctx, project_id)
        if incident_key:
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

        # Coroot filters neither by state nor by application, so a filtered
        # request has to scan more rows than it returns.
        filtering = state_filter != "any" or app_id is not None
        scan = min(max(limit * 5, 200), MAX_SCAN) if filtering else limit
        listed = await state.coroot.incidents.list(
            pid, limit=scan, from_=from_time, to=to_time
        )
        incidents = [i for i in (listed.data or []) if isinstance(i, dict)]
        digests = [_incident_digest(i) for i in incidents]
        wanted_app = normalize_app_id(app_id, project_id=pid) if app_id else None
        matched = [
            d
            for d in digests
            if (wanted_app is None or d.get("application_id") == wanted_app)
            and (
                state_filter == "any"
                or (state_filter == "open" and d["open"])
                or (state_filter == "resolved" and not d["open"])
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

    @mcp.tool(title="Get alerts", annotations=READ_ONLY)
    @guard
    async def get_alerts(
        ctx: ToolContext,
        project_id: ProjectIdParam = None,
        alert_id: Annotated[
            str | None,
            Field(
                description=(
                    "Open one alert in full, with the charts behind it. Omit to "
                    "list them."
                )
            ),
        ] = None,
        state_filter: Annotated[
            Literal["firing", "resolved", "any"],
            Field(description="Which alerts to list."),
        ] = "firing",
        search: Annotated[
            str | None,
            Field(description="Substring match over summary, application id or rule."),
        ] = None,
        app_id: Annotated[
            str | None, Field(description="Only alerts for this application id.")
        ] = None,
        limit: Annotated[
            int, Field(description="Maximum alerts to list.", ge=1, le=1000)
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
        """List alerts raised by Coroot's alerting rules, or open one by id.

        Firing alerts are what needs attention now. Each entry carries the rule
        that produced it and the application it concerns.
        """
        state, pid = await target(ctx, project_id)
        if alert_id:
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

        # Coroot matches `search` against the application id server-side, which
        # is the only way to filter by application without scanning every page.
        server_search = normalize_app_id(app_id, project_id=pid) if app_id else search
        # It cannot return resolved alerts alone, so that state is filtered here
        # and needs a wider scan than the caller asked for.
        filtering = (
            state_filter == "resolved" or app_id is not None or search is not None
        )
        scan = min(max(limit * 5, 200), MAX_SCAN) if filtering else limit
        listed = await state.coroot.alerts.list(
            pid,
            include_resolved=state_filter != "firing",
            search=server_search,
            limit=scan,
            offset=offset,
        )
        data = listed.data if isinstance(listed.data, dict) else {}
        alerts = [a for a in (data.get("alerts") or []) if isinstance(a, dict)]
        digests = [_alert_digest(a) for a in alerts]
        needle = (search or "").lower()
        wanted_app = normalize_app_id(app_id, project_id=pid) if app_id else None
        matched = [
            d
            for d in digests
            if (wanted_app is None or d.get("application_id") == wanted_app)
            and (
                state_filter == "any"
                or (state_filter == "firing" and d["firing"])
                or (state_filter == "resolved" and not d["firing"])
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
                    "raise offset to reach older ones."
                )
                if filtering and len(digests) >= scan
                else None,
            },
        )

    @mcp.tool(title="Get alerting rules", annotations=READ_ONLY)
    @guard
    async def get_alerting_rules(
        ctx: ToolContext,
        project_id: ProjectIdParam = None,
        rule_id: Annotated[
            str | None,
            Field(
                description=(
                    "Return one rule's full definition. Omit to list them all."
                )
            ),
        ] = None,
        as_yaml: Annotated[
            bool,
            Field(
                description=(
                    "Return every rule as YAML for Coroot's configuration file "
                    "instead of as a listing."
                )
            ),
        ] = False,
    ) -> dict[str, Any]:
        """List alerting rules, open one, or export them all as YAML.

        Explains why something did or did not alert. Built-in rules are marked;
        they can be disabled but not deleted.
        """
        state, pid = await target(ctx, project_id)
        if as_yaml:
            yaml = await state.coroot.alerting_rules.export(pid)
            return respond(state, {"project_id": pid, "yaml": yaml})
        if rule_id:
            rule = await state.coroot.alerting_rules.get(pid, rule_id)
            return respond(state, {"project_id": pid, **rule})

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

    # Acting on alerts and editing rules belong to the alerts group.
    if settings.read_only or not settings.enabled("alerts"):
        return

    @mcp.tool(title="Change alert state", annotations=DESTRUCTIVE)
    @guard
    async def set_alert_state(
        ctx: ToolContext,
        alert_ids: AlertIdsParam,
        action: Annotated[
            Literal["resolve", "suppress", "reopen"],
            Field(
                description=(
                    "resolve: mark fixed and notify the configured channels. "
                    "suppress: silence without resolving. reopen: undo either."
                )
            ),
        ],
        project_id: ProjectIdParam = None,
    ) -> dict[str, Any]:
        """Resolve, suppress or reopen alerts.

        Resolving notifies whoever is on call, so only do it once the underlying
        problem is actually fixed: an alert whose condition still holds fires
        again at the next evaluation. Suppress silences a known or planned
        condition instead. Both hide the alert from the default alert listing.
        """
        state, pid = await target(ctx, project_id)
        call = {
            "resolve": state.coroot.alerts.resolve,
            "suppress": state.coroot.alerts.suppress,
            "reopen": state.coroot.alerts.reopen,
        }[action]
        await call(pid, alert_ids)
        return ok(f"{action}d {len(alert_ids)} alert(s)", project_id=pid)

    @mcp.tool(title="Create or update an alerting rule", annotations=WRITE)
    @guard
    async def save_alerting_rule(
        ctx: ToolContext,
        rule: Annotated[
            dict[str, Any],
            Field(
                description=(
                    "The complete rule. Required: name, severity ('warning' or "
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
        rule_id: Annotated[
            str | None,
            Field(
                description=(
                    "Update this rule instead of creating one. Fields left out "
                    "of `rule` are cleared, so send the whole object."
                )
            ),
        ] = None,
        project_id: ProjectIdParam = None,
    ) -> dict[str, Any]:
        """Create a custom alerting rule, or replace an existing one.

        Read an existing rule with get_alerting_rules first to copy its shape.
        Built-in rules can be updated (to disable one, say) but not created.
        """
        state, pid = await target(ctx, project_id)
        if rule_id:
            await state.coroot.alerting_rules.update(pid, rule_id, rule)
            return ok(f"Updated rule {rule_id}", project_id=pid, rule_id=rule_id)
        created = await state.coroot.alerting_rules.create(pid, rule)
        new_id = created.get("id") if isinstance(created, dict) else None
        return ok("Created alerting rule", project_id=pid, rule_id=new_id)

    @mcp.tool(title="Delete an alerting rule", annotations=DESTRUCTIVE)
    @guard
    async def delete_alerting_rule(
        ctx: ToolContext,
        rule_id: Annotated[str, Field(description="Rule id from get_alerting_rules.")],
        project_id: ProjectIdParam = None,
    ) -> dict[str, Any]:
        """Delete a custom alerting rule and resolve the alerts it raised.

        Built-in rules cannot be deleted; disable them with save_alerting_rule.
        """
        state, pid = await target(ctx, project_id)
        await state.coroot.alerting_rules.delete(pid, rule_id)
        return ok(f"Deleted rule {rule_id}", project_id=pid, rule_id=rule_id)
