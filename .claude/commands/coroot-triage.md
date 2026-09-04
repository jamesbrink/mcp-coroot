# Triage a Coroot project

Work out what is wrong with the system right now, using the Coroot MCP tools.

Start with `list_alerts` for what is firing, `list_incidents` with
`state_filter` open for SLO breaches, and `list_applications` for anything at
warning or critical. Check `list_nodes` for a host that is down or saturated.

If all of those come back empty, call `get_project_status` before concluding
that everything is fine: an empty result can mean telemetry is not arriving.

Then, for the most serious problem, follow it down:

- Latency: `get_traces` for the service, then `get_trace_latency`, then
  `get_trace` on a sample.
- Errors: `get_trace_errors`, then `get_logs` with severity error over the same
  window.
- Resource pressure: `get_application` with the CPU or Memory report, and
  `get_node` for its host.
- Something changed: `list_deployments` over a window starting before the
  problem did.
- Blame upstream: `get_service_map`, then repeat for any unhealthy dependency.

Report the ranked problems with the application id and the evidence for each,
then name the single thing worth doing first. Say what you could not establish
rather than guessing.
