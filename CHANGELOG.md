# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-09-04

A full rewrite against Coroot 1.25 and the current Model Context Protocol
specification. Configuration is unchanged; tool names are not.

### Added

- `COROOT_TOOLSETS`, which selects the groups of tools to expose. The default,
  `diagnose`, carries the 20 tools needed to investigate a running system, and
  costs about 9,000 tokens of context rather than 17,000. Set it to `all` to
  expose all 44.
- Incidents and alerts: `get_incidents`, `get_alerts` and `set_alert_state`,
  which resolves, suppresses or reopens.
- Alerting rules: `get_alerting_rules` (list, one rule, or the whole set as
  YAML), `save_alerting_rule` and `delete_alerting_rule`.
- `get_overview`, which serves the project-wide views: the dependency map,
  deployments, availability and security risks, and cloud spend.
- `get_metrics` and `list_metrics` for PromQL queries and metric discovery.
- Trace tools split by intent: `summarize_trace_endpoints`, `list_traces`,
  `list_trace_error_reasons`, `explain_trace_latency` and `get_trace_by_id`.
  `list_traces` in particular finds individual slow or failed traces; without
  it the path from "this endpoint's p99 is bad" to "show me one of those
  requests" had no first step.
- `get_logs(view="patterns")`, which groups repeated messages without needing
  ClickHouse.
- Four prompts (`investigate_application`, `triage_project`, `review_incident`,
  `review_costs`) and resources for projects, per-project applications and a
  reference of id formats and check ids.
- MCP Streamable HTTP transport via `--transport http`, alongside stdio.
- `COROOT_READ_ONLY`, which removes every mutating tool from `tools/list`.
- `COROOT_PROJECT`, so tool calls can omit `project_id`; the server also
  resolves it automatically when the account can see only one project.
- `--check`, which prints the resolved configuration without starting a server.
- `scripts/smoke_test.py`, which starts the packaged script over stdio.

### Changed

- Built on the official `mcp` 2.x SDK instead of FastMCP 2.x.
- Tools report failures as MCP tool errors instead of `{"success": false}`
  payloads, so clients can distinguish a failed call from a successful one.
- Every tool carries read-only, destructive and idempotent annotations.
- Responses are reduced to fit a context window: chart series become
  last/min/max/avg, flame graphs become their heaviest frames, long lists are
  cut with a `truncated` note. Traces and profiling previously returned
  six-figure token counts.
- One pooled HTTP client for the process, rather than a new one per request,
  with automatic re-login when a session expires.
- 44 tools instead of 0.1.x's 61, with more of Coroot's API covered. Reads fold into
  the list tool for their domain (`get_projects`, `get_incidents`,
  `get_alerts`, `get_inspections`, `get_project_config`, `get_dashboards`,
  `get_users`), create and update become one `save_` tool each, and the three
  alert actions become `set_alert_state`. The full surface is the README's
  inventory; see "Upgrading from 0.1.x" there for the old-to-new mapping.
- Three-part application ids are completed with the project's cluster id, and
  path segments are encoded the way Coroot's router expects.
- Docker image rebuilt as a multi-stage `uv` build running as a non-root user.

### Security

- Integration and database credentials are redacted before they reach the
  model. Coroot returns them in clear to any account allowed to edit them,
  which is the account this server normally runs as, so `get_integrations` was
  exposing Slack tokens, PagerDuty and Opsgenie keys, Teams webhook URLs and
  AWS access keys, and `get_db_instrumentation` was exposing database
  passwords. Set `COROOT_REVEAL_SECRETS` to opt out of the redaction.
- Both write paths refuse a redaction placeholder rather than storing it
  verbatim and breaking the integration.
- Credentials embedded in `COROOT_BASE_URL` are rejected: they bypassed the
  settings redaction and reached logs, `--check` output and tool responses.
- The README documents the prompt-injection surface, since tool results carry
  text written by whoever can write to the monitored system.

### Removed

- `change_password`, whose success invalidates the credential this server
  authenticates with, and `set_notification_base_url`, an install-day setting.
  `delete_custom_cloud_pricing` folded into `set_cloud_pricing`, which resets
  when called with no prices.
- Automatic loading of a `.env` file. Settings come from the process
  environment only, so export them or pass them in your client's `env` block.
- `update_sso_config` and `update_ai_config`. Those settings are readable
  through `get_server_settings` but no longer writable.
- The FastMCP string-coercion workarounds. `sample_rate` and `excluded_paths`
  take a number and a list; they no longer need to be strings.
- `configure_profiling`, `configure_tracing` and `configure_logs`, replaced by
  `link_telemetry_service`, which is what those endpoints actually do.
- `create_or_update_role`, which Coroot answers with 405 in every edition.

### Fixed

- Unknown API paths return Coroot's web UI with status 200; that is now
  reported as an unsupported endpoint instead of being parsed as data.
- An unknown project id returns an empty 200 body; that is now a not-found
  error.
- Wrong credentials return 404 from Coroot, which is now reported as an
  authentication failure rather than a missing resource.
- The trace tools are named so no two differ by one character:
  `summarize_trace_endpoints`, `list_traces`, `get_trace_by_id`,
  `list_trace_error_reasons` and `explain_trace_latency`.
- Trace latency bounds are sent as the float seconds Coroot parses. Go-style
  durations resolved to zero, which selected no traces and left the server
  diffing against a nil flame graph.
- Updating one field of an application category no longer erases the others.
  Coroot replaces the whole category on save, so patterns and notification
  routing are read first and merged.
- Charts inside a chart group survive summarisation. Audit reports are built
  mostly from chart groups, so CPU, memory, JVM and GPU reports were arriving
  with their series stripped.
- A profile category is resolved to a concrete profile type before an instance
  filter is applied; otherwise Coroot searched for a profile type named "cpu".
- Alert and incident filters scan beyond a single server page, and the
  application filter is pushed into Coroot's search. Asking for resolved alerts
  previously returned an empty list next to a non-zero resolved count.
- A project whose API key list serialises as null no longer breaks key
  creation.
- health_check probes without authenticating, so it can still tell a
  connectivity problem from a credentials one.
- Unexpected exceptions are reported with the tool name and exception type
  instead of a bare "Error executing tool".
- The output budget now holds for payloads that cannot be truncated, and
  relative trace timestamp bounds are resolved before Coroot splits them.

## [0.1.1] - 2025-07-27

- Docker support and CI/CD improvements.

## [0.1.0] - 2025-07-26

- Initial release.
