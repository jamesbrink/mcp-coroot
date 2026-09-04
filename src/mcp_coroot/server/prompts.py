"""Prompts: reusable investigation workflows."""

from __future__ import annotations

from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from .state import AppState

AppArg = Annotated[
    str, Field(description="Application id, or its name if you do not have the id yet.")
]
ProjectArg = Annotated[
    str, Field(description="Project id. Leave empty to use the default project.")
]


def register(mcp: MCPServer[AppState]) -> None:
    """Register every prompt on ``mcp``."""

    @mcp.prompt(
        title="Investigate an unhealthy application",
        description="Walk an application from symptom to cause using Coroot.",
    )
    def investigate_application(application: AppArg, project: ProjectArg = "") -> str:
        scope = f" in project {project}" if project else ""
        return f"""\
Investigate why {application}{scope} is unhealthy, using the Coroot tools.

Work in this order and stop as soon as the evidence explains the problem:

1. Call get_application for {application} to see its failing checks and which
   audit reports are warning or critical.
2. If SLO checks are failing, call get_incidents for the application and open
   the most recent one with get_incident.
3. For latency: call summarize_trace_endpoints for the application's service,
   then explain_trace_latency for where the slow requests spend their time.
   Pull one example with list_traces, then get_trace_by_id.
4. For errors: call list_trace_error_reasons for failure reasons, and get_logs
   with severity error for the same window.
5. Check whether something changed: get_overview with view=deployments over a window
that starts
   before the problem did.
6. Check the dependencies: get_overview with view=map, then repeat step 1 for any
upstream
   that is also unhealthy.

Report what is wrong, the evidence for it, and what you would do next. If the
data is inconclusive, say which tool call would settle it rather than guessing.
"""

    @mcp.prompt(
        title="Triage what is broken",
        description="Survey a project's current health and rank what needs attention.",
    )
    def triage_project(project: ProjectArg = "") -> str:
        scope = f" for project {project}" if project else ""
        return f"""\
Give me a triage summary{scope} using the Coroot tools.

1. Call get_alerts to see what is firing now.
2. Call get_incidents with state_filter open for SLO breaches.
3. Call list_applications and note everything at warning or critical.
4. Call get_nodes to check whether any host is down or saturated.
5. Call get_projects if any of the above look empty, to confirm telemetry
   is actually arriving.

Then rank the problems by user impact, group the ones that share a likely cause,
and name the single thing worth looking at first. Keep it short: one line per
issue, with the application id and the evidence.
"""

    @mcp.prompt(
        title="Review an incident",
        description="Summarise a Coroot incident and its root cause analysis.",
    )
    def review_incident(
        incident_key: Annotated[
            str, Field(description="Incident key from get_incidents.")
        ],
        project: ProjectArg = "",
    ) -> str:
        scope = f" in project {project}" if project else ""
        return f"""\
Review Coroot incident {incident_key}{scope}.

1. Call get_incidents for {incident_key}: severity, duration, which SLO was
   breached and by how much.
2. Call get_application for the affected application over the incident window,
   passing incident={incident_key} so the charts cover the right period.
3. Call get_overview with view=deployments over the same window to see whether a rollout
coincided.
4. Call get_logs with severity error for the affected application and window.

Write it up as a short incident review: what users experienced, the timeline,
the most likely cause with its evidence, and the follow-up actions worth taking.
Mark anything you could not establish as unknown instead of speculating.
"""

    @mcp.prompt(
        title="Find cost savings",
        description="Look for over-provisioned workloads and idle capacity.",
    )
    def review_costs(project: ProjectArg = "") -> str:
        scope = f" for project {project}" if project else ""
        return f"""\
Find cloud cost savings{scope} using the Coroot tools.

1. Call get_overview with view=costs and note the applications with the largest gap
between
   allocated and used resources, and the nodes with the highest idle costs.
2. Call get_overview with view=risks: single-instance and spot-only workloads change
what is safe
   to shrink.
3. For the top few applications, call get_application with report Memory and
   report CPU to confirm the usage pattern before recommending a change.

Produce a table of proposed request changes with the current value, the
recommended value and the reason. Flag anything where shrinking would remove
redundancy.
"""
