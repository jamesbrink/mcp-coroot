# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-09-04

A full rewrite against Coroot 1.25 and the current Model Context Protocol
specification. Configuration is unchanged; tool names are not.

### Added

- Incidents and alerts: `list_incidents`, `get_incident`, `list_alerts`,
  `get_alert`, `resolve_alerts`, `suppress_alerts`, `reopen_alerts`.
- Alerting rules: list, get, create, update, delete and YAML export.
- `get_service_map` for the dependency graph, `get_costs` for cloud spend and
  over-provisioning, `list_risks` for availability and security risks.
- `get_metrics` and `list_metrics` for PromQL queries and metric discovery.
- Trace tools split by intent: `get_traces`, `get_trace_errors`,
  `get_trace_latency` and `get_trace`.
- `get_log_patterns`, which groups repeated messages without needing ClickHouse.
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
- Overview tools renamed to verbs: `list_applications`, `list_nodes`,
  `list_deployments`, `list_risks`.
- Three-part application ids are completed with the project's cluster id, and
  path segments are encoded the way Coroot's router expects.
- Docker image rebuilt as a multi-stage `uv` build running as a non-root user.

### Removed

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

## [0.1.1] - 2025-07-27

- Docker support and CI/CD improvements.

## [0.1.0] - 2025-07-26

- Initial release.
