# MCP Server for Coroot

[![CI](https://github.com/jamesbrink/mcp-coroot/actions/workflows/ci.yml/badge.svg)](https://github.com/jamesbrink/mcp-coroot/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/jamesbrink/mcp-coroot/branch/main/graph/badge.svg)](https://codecov.io/gh/jamesbrink/mcp-coroot)
[![PyPI version](https://img.shields.io/pypi/v/mcp-coroot.svg)](https://pypi.org/project/mcp-coroot/)
[![Python versions](https://img.shields.io/pypi/pyversions/mcp-coroot.svg)](https://pypi.org/project/mcp-coroot/)

A [Model Context Protocol](https://modelcontextprotocol.io) server for
[Coroot](https://coroot.com). It lets an MCP client investigate a running system
through Coroot: application health, logs, distributed traces, profiles, metrics,
SLO incidents, alerts, deployments, costs and configuration.

`mcp-name: io.github.jamesbrink/mcp-coroot`

## Quick start

```json
{
  "mcpServers": {
    "coroot": {
      "command": "uvx",
      "args": ["mcp-coroot"],
      "env": {
        "COROOT_BASE_URL": "http://localhost:8080",
        "COROOT_USERNAME": "admin",
        "COROOT_PASSWORD": "your-password"
      }
    }
  }
}
```

For single sign-on or multi-factor logins, where a password cannot be used, copy
the `coroot_session` cookie out of a browser session instead:

```json
{
  "mcpServers": {
    "coroot": {
      "command": "uvx",
      "args": ["mcp-coroot"],
      "env": {
        "COROOT_BASE_URL": "https://coroot.example.com",
        "COROOT_SESSION_COOKIE": "your-session-cookie"
      }
    }
  }
}
```

With Docker:

```json
{
  "mcpServers": {
    "coroot": {
      "command": "docker",
      "args": ["run", "--rm", "-i",
               "-e", "COROOT_BASE_URL=http://host.docker.internal:8080",
               "-e", "COROOT_USERNAME=admin",
               "-e", "COROOT_PASSWORD=your-password",
               "jamesbrink/mcp-coroot:latest"]
    }
  }
}
```

Check the configuration without starting a server:

```bash
COROOT_BASE_URL=http://localhost:8080 uvx mcp-coroot --check
```

## Configuration

| Variable | Purpose |
| --- | --- |
| `COROOT_BASE_URL` | Coroot URL. Defaults to `http://localhost:8080`. `COROOT_URL` also works. |
| `COROOT_USERNAME` | Username for automatic login. Must be set with `COROOT_PASSWORD`. |
| `COROOT_PASSWORD` | Password for automatic login. |
| `COROOT_SESSION_COOKIE` | An existing `coroot_session` cookie, for SSO and MFA logins. |
| `COROOT_API_KEY` | Project API key. Only the Prometheus-compatible query endpoints accept it. |
| `COROOT_PROJECT` | Default project id, so tool calls can omit `project_id`. |
| `COROOT_TIMEOUT` | HTTP timeout in seconds. Defaults to 30. |
| `COROOT_VERIFY_SSL` | Set to `false` to skip TLS verification. |
| `COROOT_READ_ONLY` | Set to `true` to expose only the tools that read from Coroot. |
| `COROOT_MAX_OUTPUT_CHARS` | Character budget for one tool response. Defaults to 40000. |

Username and password authentication is the best choice when it is available:
the server logs in on demand and logs in again by itself when the session
expires, which Coroot does after seven days.

### Read-only mode

`COROOT_READ_ONLY=true` (or `--read-only`) removes the 33 mutating tools from
the server entirely. They do not appear in `tools/list`, so a model cannot call
one by mistake. Worth setting for anyone pointing a client at production.

### Transports

The default is stdio, which is what desktop clients launch. To run the server as
a shared network service instead:

```bash
mcp-coroot --transport http --host 0.0.0.0 --port 8000
```

That serves MCP Streamable HTTP at `/mcp`. Add `--stateless` and
`--json-response` when running several replicas behind a load balancer. The
server has no authentication of its own, so put it behind something that does.

## What the model gets

**77 tools.** Grouped below by what they touch. Every tool is annotated as
read-only, write or destructive, so clients can prompt for confirmation on the
ones that change something.

**4 prompts.** `investigate_application`, `triage_project`, `review_incident`
and `review_costs`, each an ordered workflow rather than a single question.

**2 resources.** `coroot://projects` lists the projects the account can see, and
`coroot://reference` describes id formats, time expressions, statuses and check
ids. A resource template, `coroot://project/{project_id}/applications`, lists
application ids for one project.

### Working with the tools

Application ids are four-part strings, `cluster_id:namespace:Kind:name`, for
example `hwvop6p7:default:Deployment:checkout`. Pass them back exactly as
returned. A three-part id is completed with the project's cluster id
automatically.

Time arguments accept `now-1h`, a bare duration such as `30m`, epoch seconds or
milliseconds, or an ISO-8601 date. Windows default to the last hour.

`project_id` can be omitted when `COROOT_PROJECT` is set or the account can see
only one project. Otherwise the server replies with the list to choose from.

### Response size

Coroot's API returns everything its web UI needs to draw a page. A single traces
or profiling response can run past a hundred thousand tokens, which is more than
most context windows hold.

This server reduces those before returning them. Chart series become
last, minimum, maximum and average. Flame graphs become their heaviest leaves.
Long lists are cut. Whenever something was dropped the response says so in a
`truncated` field, which is the signal to narrow the time range or lower a limit
rather than assume the data was complete.

### Tools

#### Projects and connectivity (11)

- `health_check` - Check that the configured Coroot instance is reachable.
- `whoami` - Show the authenticated user, their role and their projects.
- `list_projects` - List the projects (clusters) this account can see.
- `get_project` - Get a project's settings, refresh interval and API keys.
- `get_project_status` - Check whether a project is actually collecting telemetry.
- `list_api_keys` - List a project's telemetry ingestion keys.
- `create_project`, `update_project`, `delete_project`
- `create_api_key`, `delete_api_key`

#### Applications and infrastructure (10)

- `list_applications` - Applications with health and failing inspections. The triage starting point.
- `get_application` - One application's audit reports, failing checks and dependencies.
- `get_service_map` - The dependency graph and each service's health.
- `list_nodes`, `get_node` - Hosts and their audit reports.
- `list_deployments` - Recent rollouts and the impact Coroot measured.
- `list_risks` - Single-instance workloads, unreplicated databases, exposed databases.
- `get_costs` - Per-node and per-application cost, with over-provisioning.
- `get_application_rca` - Coroot's AI root cause analysis, when Coroot Cloud is configured.
- `set_risk_status` - Dismiss a risk as accepted, or restore it.

#### Logs, traces, profiles and metrics (9)

- `get_logs` - Search log entries by severity and text, per application or project-wide.
- `get_log_patterns` - Repeated messages grouped by pattern, with volumes.
- `get_traces` - Per-endpoint request rate, error rate and latency quantiles.
- `get_trace_errors` - Top failure reasons with a sample trace id each.
- `get_trace_latency` - Why the slow tail is slow, as a differential flame graph.
- `get_trace` - One trace as a span tree with attributes and events.
- `get_profile` - CPU, memory or lock profile reduced to its hottest frames.
- `get_metrics` - Run a PromQL range query.
- `list_metrics` - Discover metric names.

#### Incidents and alerts (13)

- `list_incidents`, `get_incident` - SLO breaches with burn rates and analysis.
- `list_alerts`, `get_alert` - Alerts from Coroot's alerting rules.
- `resolve_alerts`, `suppress_alerts`, `reopen_alerts`
- `list_alerting_rules`, `get_alerting_rule`, `export_alerting_rules`
- `create_alerting_rule`, `update_alerting_rule`, `delete_alerting_rule`

#### Configuration (21)

- `list_inspections`, `get_inspection_config`, `update_inspection_config` - Check thresholds and custom SLOs.
- `list_application_categories`, `save_application_category`, `delete_application_category`
- `list_custom_applications`, `save_custom_application`, `delete_custom_application`
- `list_integrations`, `get_integration`, `configure_integration`, `delete_integration`, `set_notification_base_url`
- `get_db_instrumentation`, `configure_db_instrumentation` - Let Coroot collect database statistics.
- `link_telemetry_service` - Map an OpenTelemetry service name onto an application.
- `get_cloud_pricing`, `set_cloud_pricing`, `reset_cloud_pricing`
- `get_server_settings`

#### Dashboards (7)

- `list_dashboards`, `get_dashboard`, `create_dashboard`, `update_dashboard`
- `update_dashboard_panels`, `delete_dashboard`
- `get_panel_data` - Evaluate PromQL queries as a chart without saving a dashboard.

#### Users and roles (6)

- `list_users`, `list_roles`
- `create_user`, `update_user`, `delete_user`, `change_password`

## Examples

Triage:

```
Which applications are unhealthy in production?
What is firing right now, and what should I look at first?
```

Investigation:

```
Why is the checkout service slow? Look at the last three hours.
Show me the error logs for the payment API since 14:00 and find the trace behind them.
What deployed just before the latency went up?
```

Configuration:

```
Send critical alerts for the database category to the #db-oncall Slack channel.
Raise the CPU threshold for the batch workers to 95%.
Which applications are over-provisioned, and what should their requests be?
```

## Requirements

Coroot 1.x, tested against the API as of Coroot 1.25. Python 3.11 or newer.
Community Edition covers everything here except AI root cause analysis, which
needs a Coroot Cloud key, and single sign-on configuration, which is an
Enterprise feature and reads back empty.

Logs and traces need ClickHouse configured in Coroot; `get_project_status` says
whether it is. Some management endpoints require an Admin or Editor role, and
permission failures explain which role would be needed.

## Development

```bash
git clone https://github.com/jamesbrink/mcp-coroot.git
cd mcp-coroot
uv sync --all-groups

uv run pytest                       # tests with coverage
uv run ruff check src tests         # lint
uv run ruff format src tests        # format
uv run mypy src                     # type check (strict)
uv run python scripts/smoke_test.py # start over stdio and list tools
```

Tests run against a scripted in-memory Coroot rather than a live one, so the
suite needs no network and no running instance.

## Upgrading from 0.1.x

Version 1.0 is a rewrite. Configuration is compatible, but tool names are not:

- Overviews became verbs: `get_applications_overview` is now `list_applications`, `get_nodes_overview` is `list_nodes`, `get_deployments_overview` is `list_deployments`, `get_risks_overview` is `list_risks`.
- Telemetry tools were split by intent: `get_application_traces` became `get_traces`, `get_trace_errors`, `get_trace_latency` and `get_trace`; `get_application_logs` became `get_logs` and `get_log_patterns`; `get_application_profiling` became `get_profile`.
- Failures are reported as MCP tool errors instead of `{"success": false}` payloads.
- Numeric and list arguments are real numbers and lists. The 0.1.x string workarounds (`sample_rate` as `"0.1"`, `excluded_paths` as a JSON string) are gone.
- New areas: incidents, alerts, alerting rules, the service map, costs, PromQL queries, and Coroot Cloud settings.

## License

MIT. See [LICENSE](LICENSE).
