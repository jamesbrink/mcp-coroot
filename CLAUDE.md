# CLAUDE.md

Internal notes for working on this repository.

## Documentation policy

This project keeps exactly two prose documents: `README.md` (public) and
`CLAUDE.md` (this file). `LICENSE` and `CHANGELOG.md` are also allowed. Do not
add other markdown files; fold new documentation into one of these.

## Testing standards

- Test files are named `test_<module>.py` and mirror the module they cover.
- Never use suffixes like `test_final_*.py`, `test_new_*.py` or
  `test_all_remaining_*.py`. Consolidate into the existing file instead.
- Tests run against a scripted fake Coroot (`tests/conftest.py`), never a live
  instance and never the network.

## Layout

```
src/mcp_coroot/
  config.py            Settings, read from the environment once at startup
  cli.py               Argument parsing, logging to stderr, transport selection
  client/
    base.py            Pooled httpx2 transport, lazy login, body decoding
    errors.py          Exception types mapped from Coroot's status codes
    ids.py             ApplicationId parsing and path-segment encoding
    timerange.py       Relative, epoch and ISO time parsing
    accounts.py projects.py overview.py applications.py incidents.py
    dashboards.py configuration.py metrics.py
    client.py          CorootClient, composing the above
  server/
    app.py             build_server, lifespan, annotation constants
    state.py           AppState, project resolution, StateHolder
    errors.py          guard decorator turning client errors into ToolError
    compact.py         Chart, flame graph and budget reduction
    instructions.py    The instructions string sent to clients
    resources.py       prompts.py
    tools/             One module per domain, registered by register_all
```

## Architecture decisions

**SDK.** The official `mcp` 2.x SDK (`mcp.server.mcpserver.MCPServer`), not
jlowin `fastmcp`. It ships the same day as the spec revisions it implements,
masks unexpected exceptions instead of leaking them to the model, and pre-parses
JSON strings for list and object parameters, which removes the string-coercion
workarounds 0.1.x carried. Note that `mcp.server.fastmcp` no longer exists in
`mcp` 2.x, and that `fastmcp>=4` depends on `mcp>=2` itself.

**HTTP.** `httpx2`, because the MCP SDK depends on it; using `httpx` as well
would ship two HTTP stacks. One `AsyncClient` lives for the whole server
lifetime, created by the lifespan, so connections are pooled.

**Authentication.** Coroot's session cookie is named `coroot_session` and lasts
seven days with no server-side store. The transport logs in on the first request
that needs it, and once more if a request comes back 401. API keys only work for
`/api/v1/*`, never for `/api/project/...`.

**Errors.** Coroot answers errors as `text/plain` with no JSON envelope, and its
router serves the web UI with status 200 for unknown `/api` paths. Both are
handled in `client/base.py`: a non-JSON 200 becomes `CorootUnsupportedError`.
Wrong credentials return 404, not 401.

**Response size.** Tools return summaries, not raw payloads, and `compact.fit`
enforces `COROOT_MAX_OUTPUT_CHARS` as a last resort. `chart_summary` and
`flamegraph_summary` are idempotent, because payloads get compacted more than
once as they pass through nested structures.

**Read-only mode.** Mutating tools are never registered when
`COROOT_READ_ONLY` is set, rather than failing at call time, so they are absent
from `tools/list`.

**Tool errors.** Every tool is wrapped in `server/errors.py::guard`, which
converts client exceptions into `ToolError`. `functools.wraps` keeps the
signature visible to the SDK's schema generation, which follows `__wrapped__`.

## Gotchas found in Coroot's source

These come from reading `coroot/coroot` at v1.25 and are easy to get wrong:

- Application ids must be the full four-part form. A three-part id parses but
  matches nothing, because lookup is a map access. `client/ids.py` fills in the
  cluster id.
- Routes use `UseEncodedPath`, and handlers query-unescape `{app}` and `{node}`.
  A literal `+` must be sent as `%2B`; `encode_segment` handles it.
- `GET /api/project/{id}` for an unknown project returns 200 with an empty body,
  not 404. `ProjectsAPI.get` converts that into a not-found error.
- World-loading routes wrap payloads in `{"context": ..., "data": ...}`; others
  do not. `split_envelope` normalises both.
- `POST /api/project/` returns the new id as `text/plain`, and dashboard
  creation returns 201 with a plain-text id.
- `POST /integrations/{type}` only tests; `PUT` saves. Prometheus cannot be
  deleted through the API.
- Simple inspection configs are positional: index 0 is Coroot's default, 1 the
  project override, 2 the application override, and null clears one.
- Instrumentation stores the `type` from the body, ignoring the path segment,
  so the body must always carry it.
- `POST /api/roles` always returns 405, and `/api/sso` and `/api/ai` are stubs
  in Community Edition.
- The project-wide scope for inspection config is the application id `::`.
- `dur_from`/`dur_to` on the traces view are parsed by `ParseHeatmapDuration`,
  which accepts **float seconds only**. A Go-style duration yields zero, no
  selection is defined, and the latency view then calls `FlameGraphNode.Diff`
  on a nil comparison, which dereferences it.
- Saving an application category replaces it: `CustomPatterns` and
  `NotificationSettings` are both assigned from the body, so a partial update
  must read the current form first.
- The profiling `query` parameter is a category (`cpu`/`memory`/`lock`) only
  when it is not JSON. Inside JSON the field is a concrete `ProfileType`, and
  the category is resolved only when that type is empty.
- `QueryAlerts` pages in SQL while its firing/resolved counts are unlimited,
  and it cannot return resolved alerts alone. Its `search` does match
  `application_id`, which is the only server-side way to filter by application.
- `ApiKeys` has no `omitempty`, so a project without keys serialises
  `"keys": null`.
- A `ChartGroup` is `{"title", "charts": [Chart]}`, not a chart. A
  `timeseries.TimeSeries` is a bare array of floats and also appears under a
  `chart` key; a dashboard panel's `widget.chart` is `{"display", "stacked"}`
  and is not a chart at all.
- Integration and instrumentation secrets are masked **only** when the caller
  may not edit them (`form.Get(project, !isAllowed)`). An Admin or Editor reads
  them in clear, so `server/secrets.py` redacts them here.
- `FlameGraphNode.Diff` dereferences its argument without a nil check, and
  `getTraceLatencyFlamegraph` returns nil for an empty trace list, so asking
  the traces view for `diff` can crash the handler. Never request it.
- An alert is resolved if `resolved_at`, `manually_resolved_at` **or**
  `suppressed` is set; checking only the first misses alerts a person closed.
- Coroot ignores `from`/`to` when listing incidents, so a narrower window
  cannot surface older ones; only a larger `limit` can.

## Verification

Everything below must pass before a commit:

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src
uv run pytest
uv run python scripts/smoke_test.py
```

The smoke test starts the packaged console script over stdio, which the
in-process tests cannot cover.

## CI note

The `.github/workflows/` files in this repository are the 0.1.x versions. An
improved set (separate lint job, stdio smoke test, Docker build on pull
requests without pushing) was written during the 1.0 rewrite but could not be
pushed, because the GitHub App used for that work lacks the `workflows`
permission. The existing workflows still pass against the current code.
