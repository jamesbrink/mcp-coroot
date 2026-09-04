# Smoke test the Coroot MCP server

Exercise the read-only tools against the configured Coroot instance and report
what works. Nothing here modifies Coroot.

1. Call `health_check`. If it fails, stop and report the connection settings it
   returned.
2. Call `whoami` and note the role, since it decides which tools can succeed.
3. Call `list_projects`. Use the first project for everything below.
4. Call `get_project_status`. Note whether the metrics source, node agent and
   ClickHouse are healthy: logs and traces need ClickHouse.
5. Call `list_applications`. Note the status distribution and pick one
   application, preferring one at warning or critical.
6. For that application call `get_application`, then `get_log_patterns`.
7. Call `list_nodes`, and `get_node` for the first one.
8. Call `list_incidents` and `list_alerts`. If either returns something, open
   the first with `get_incident` or `get_alert`.
9. Call `get_traces`. If it reports no ClickHouse, note that and move on.
10. Call `list_metrics` with match `up.*`, then `get_metrics` with query `up`.
11. Call `list_deployments`, `list_risks` and `get_costs`.
12. Call `list_integrations`, `list_inspections` and `list_dashboards`.

Report a table of tool, outcome and one line of detail. For failures, give the
error message verbatim. Finish with whether the server looks healthy, and call
out anything that failed for a reason other than missing data.
