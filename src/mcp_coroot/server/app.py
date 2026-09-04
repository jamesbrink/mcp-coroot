"""MCP server construction."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from .. import __version__
from ..client import CorootClient
from ..config import Settings
from .instructions import INSTRUCTIONS
from .state import AppState, StateHolder

logger = logging.getLogger("mcp_coroot.server")

#: Reads never change Coroot state and are safe to retry.
READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=True,
)

#: Writes that create or replace an object, but do not remove data.
WRITE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=True,
)

#: Writes that delete data or notify people; clients should confirm these.
DESTRUCTIVE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=True,
    idempotent_hint=False,
    open_world_hint=True,
)


def build_server(
    settings: Settings,
    *,
    client_factory: Callable[[Settings], CorootClient] | None = None,
) -> MCPServer[AppState]:
    """Create the MCP server for ``settings``.

    ``client_factory`` exists so tests can inject a client backed by a mock
    transport. In read-only mode the mutating tools are never registered, so they
    do not appear in ``tools/list`` at all.
    """
    make_client = client_factory or (lambda s: CorootClient(s))
    holder = StateHolder()

    @asynccontextmanager
    async def lifespan(_: MCPServer[AppState]) -> AsyncIterator[AppState]:
        coroot = make_client(settings)
        logger.info(
            "mcp-coroot %s connecting to %s (auth: %s%s)",
            __version__,
            settings.base_url,
            settings.auth_mode,
            ", read-only" if settings.read_only else "",
        )
        state = AppState(settings=settings, coroot=coroot)
        holder.set(state)
        try:
            yield state
        finally:
            holder.set(None)
            await coroot.aclose()

    server: MCPServer[AppState] = MCPServer(
        "coroot",
        title="Coroot",
        version=__version__,
        instructions=INSTRUCTIONS,
        website_url="https://coroot.com",
        lifespan=lifespan,
    )

    from . import prompts, resources
    from .tools import register_all

    register_all(server, settings)
    resources.register(server, holder)
    prompts.register(server)
    return server
