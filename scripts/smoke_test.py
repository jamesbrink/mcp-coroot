#!/usr/bin/env python3
"""Start the server over stdio and check that it answers a tools/list call.

Run by CI to catch packaging and transport regressions that unit tests, which
build the server in-process, cannot see.
"""

from __future__ import annotations

import asyncio
import os
import sys

from mcp import Client, StdioServerParameters

EXPECTED_TOOLS = {
    "health_check",
    "list_projects",
    "list_applications",
    "get_application",
    "get_logs",
    "get_traces",
    "get_metrics",
    "list_incidents",
    "list_alerts",
}


async def main() -> int:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_coroot"],
        env={**os.environ},
    )
    async with Client(params) as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}
        prompts = {prompt.name for prompt in (await client.list_prompts()).prompts}
        resources = {str(r.uri) for r in (await client.list_resources()).resources}

    missing = EXPECTED_TOOLS - tools
    if missing:
        print(f"missing tools: {sorted(missing)}", file=sys.stderr)
        return 1
    if not prompts or not resources:
        print("server exposed no prompts or no resources", file=sys.stderr)
        return 1

    print(f"ok: {len(tools)} tools, {len(prompts)} prompts, {len(resources)} resources")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
