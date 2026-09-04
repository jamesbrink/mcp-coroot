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
| `COROOT_API_KEY` | Project API key. Coroot accepts it only on its Prometheus-compatible query endpoints, which no tool currently calls, so it cannot substitute for a login. |
| `COROOT_PROJECT` | Default project id, so tool calls can omit `project_id`. |
| `COROOT_TIMEOUT` | HTTP timeout in seconds. Defaults to 30. |
| `COROOT_VERIFY_SSL` | Set to `false` to skip TLS verification. Only for a self-signed certificate on a trusted network: it exposes the password and session cookie to anyone on the path. |
| `COROOT_TOOLSETS` | Which groups of tools to expose, comma separated: `diagnose`, `alerts`, `dashboards`, `config`, `admin`, or `all`. Defaults to `diagnose`. |
| `COROOT_READ_ONLY` | Set to `true` to expose only the tools that read from Coroot. |
| `COROOT_REVEAL_SECRETS` | Set to `true` to let integration and database credentials reach the model. Off by default. |
| `COROOT_MAX_OUTPUT_CHARS` | Character budget for one tool response. Defaults to 40000. |

Username and password authentication is the best choice when it is available:
the server logs in on demand and logs in again by itself when the session
expires, which Coroot does after seven days.

### Toolsets

The whole surface is 75 tools, and carrying it costs roughly 23,000 tokens of
context in every conversation before a single call. Most of it configures
Coroot rather than investigating a running system, so the default exposes the
`diagnose` group only: 42 tools, about 14,000 tokens, covering applications,
nodes, logs, traces, profiles, metrics, incidents and alerts.

Add what you need:

```bash
COROOT_TOOLSETS=diagnose,alerts   # also resolve alerts and edit alerting rules
COROOT_TOOLSETS=all               # everything, including user and project admin
```

| Group | What it adds |
| --- | --- |
| `diagnose` (default) | Reading applications, nodes, telemetry, incidents, alerts and configuration |
| `alerts` | Resolving, suppressing and reopening alerts; alerting rule changes |
| `dashboards` | Custom dashboards and ad-hoc panel queries |
| `config` | Categories, custom applications, integrations, instrumentation, pricing |
| `admin` | Projects, API keys, users and roles |

Finding a project (`list_projects`, `get_project_status`, `health_check`,
`whoami`) is always available.

### Read-only mode

`COROOT_READ_ONLY=true` (or `--read-only`) removes the 32 mutating tools from
the server entirely. They do not appear in `tools/list`, so a model cannot call
one by mistake. Worth setting for anyone pointing a client at production.

It stops writes; it is not a confidentiality control. The reads it leaves in
place still return a project's telemetry ingestion keys (`list_api_keys`), and
`get_integration` and `get_db_instrumentation` still reach settings that hold
credentials — those are redacted separately, see below.

### Credentials in responses

Coroot returns integration and database secrets in clear to any account allowed
to edit them, which is the account this server usually runs as. Slack tokens,
PagerDuty and Opsgenie keys, Teams webhook URLs, AWS access keys and database
passwords are therefore redacted before they reach the model. Set
`COROOT_REVEAL_SECRETS=true` if you genuinely need to read one back.

### Untrusted content

Tool results carry text from the monitored system: log lines, span attributes,
application names, alert summaries. Anyone who can write a log line in that
system can put words in front of the model. Treat that text as data, never as
instructions — and prefer read-only mode when the monitored environment is not
fully trusted.

### Transports

The default is stdio, which is what desktop clients launch. To run the server as
a shared network service instead:

```bash
mcp-coroot --transport http --host 127.0.0.1 --port 8000
```

That serves MCP Streamable HTTP at `/mcp` (`--path` moves it). Add `--stateless`
and `--json-response` when running several replicas behind a load balancer.

This transport has no authentication of its own. Anyone who can reach the port
gets every tool, including the destructive ones. Bind it to localhost, put an
authenticating proxy in front, and combine it with `COROOT_READ_ONLY` unless
writes are genuinely needed.

Other flags: `--read-only`, `--log-level`, `--check` (print the resolved
configuration and exit) and `--version`.

## What the model gets

**75 tools**, of which 42 are exposed by default. Grouped below by what they touch. Every tool is annotated as
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
- `create_project`, `update_project`, `delete_project` *(admin)*
- `create_api_key`, `delete_api_key` *(admin)*

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

#### Logs, traces, profiles and metrics (10)

- `get_logs` - Search log entries by severity and text, per application or project-wide.
- `get_log_patterns` - Repeated messages grouped by pattern, with volumes.
- `summarize_trace_endpoints` - Per-endpoint request rate, error rate and latency quantiles, worst first.
- `list_traces` - Individual slow or failed traces, with the ids to open them.
- `list_trace_error_reasons` - Top failure reasons with a sample trace id each.
- `explain_trace_latency` - Where the slow tail spends its time.
- `get_trace_by_id` - One trace as a span tree with attributes and events.
- `get_profile` - CPU, memory or lock profile reduced to its hottest frames.
- `get_metrics` - Run a PromQL range query.
- `list_metrics` - Discover metric names.

#### Incidents and alerts (13)

- `list_incidents`, `get_incident` - SLO breaches with burn rates and analysis.
- `list_alerts`, `get_alert` - Alerts from Coroot's alerting rules.
- `resolve_alerts`, `suppress_alerts`, `reopen_alerts`
- `list_alerting_rules`, `get_alerting_rule`, `export_alerting_rules`
- `create_alerting_rule`, `update_alerting_rule`, `delete_alerting_rule`

#### Configuration (19)

- `list_inspections`, `get_inspection_config`, `update_inspection_config` - Check thresholds and custom SLOs.
- `list_application_categories`, `save_application_category`, `delete_application_category`
- `list_custom_applications`, `save_custom_application`, `delete_custom_application`
- `list_integrations`, `get_integration`, `configure_integration`, `delete_integration`
- `get_db_instrumentation`, `configure_db_instrumentation` - Let Coroot collect database statistics.
- `link_telemetry_service` - Map an OpenTelemetry service name onto an application.
- `get_cloud_pricing`, `set_cloud_pricing` (omit both prices to reset)
- `get_server_settings`

#### Dashboards (7)

- `list_dashboards`, `get_dashboard`, `create_dashboard`, `update_dashboard`
- `update_dashboard_panels`, `delete_dashboard`
- `get_panel_data` - Evaluate PromQL queries as a chart without saving a dashboard.

#### Users and roles (5)

- `list_users`, `list_roles`
- `create_user`, `update_user`, `delete_user`

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
needs a Coroot Cloud key. Single sign-on cannot be configured through this
server at all; `get_server_settings` reads the instance's role list and its AI
provider, which is empty on Community Edition.

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

- Settings no longer come from a `.env` file. 0.1.x loaded one automatically; 1.0 reads the process environment only, so export the variables or pass them in your MCP client's `env` block.
- Overviews became verbs: `get_applications_overview` is now `list_applications`, `get_nodes_overview` is `list_nodes`, `get_deployments_overview` is `list_deployments`, `get_risks_overview` is `list_risks`, `get_traces_overview` is `summarize_trace_endpoints`.
- Telemetry tools were split by intent: `get_application_traces` became `summarize_trace_endpoints`, `list_traces`, `list_trace_error_reasons`, `explain_trace_latency` and `get_trace_by_id`; `get_application_logs` became `get_logs` and `get_log_patterns`; `get_application_profiling` became `get_profile`.
- Renamed: `get_current_user` is `whoami`, `get_roles` is `list_roles`, `get_application_categories` is `list_application_categories`, `get_custom_applications` is `list_custom_applications`, `update_project_settings` is `update_project`, `update_db_instrumentation` is `configure_db_instrumentation`, `update_application_risks` is `set_risk_status`, `get_custom_cloud_pricing` is `get_cloud_pricing`, `update_custom_cloud_pricing` is `set_cloud_pricing`, `delete_custom_cloud_pricing` is `reset_cloud_pricing`.
- Merged: `create_application_category` and `update_application_category` are `save_application_category`; `update_custom_applications` is `save_custom_application` and `delete_custom_application`; `update_current_user` is `update_user` and `change_password`; `get_sso_config` and `get_ai_config` are `get_server_settings`; `test_integration` is `configure_integration(test_only=true)`.
- Removed with no replacement: `update_sso_config` and `update_ai_config`. Those settings are readable through `get_server_settings` but no longer writable.
- Also removed: `change_password` (its success invalidates the credential this server authenticates with), `set_notification_base_url` (an install-day setting) and `delete_custom_cloud_pricing` (call `set_cloud_pricing` with no prices to reset).
- Failures are reported as MCP tool errors instead of `{"success": false}` payloads.
- Numeric and list arguments are real numbers and lists. The 0.1.x string workarounds (`sample_rate` as `"0.1"`, `excluded_paths` as a JSON string) are gone.
- New areas: incidents, alerts, alerting rules, the service map, costs, PromQL queries and Coroot Cloud status.

## License

MIT. See [LICENSE](LICENSE).
