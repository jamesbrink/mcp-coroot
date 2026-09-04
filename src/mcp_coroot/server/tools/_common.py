"""Shared parameter types and response helpers for tools."""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Field

from ..compact import compact, fit
from ..state import AppState, ToolContext, state_of

ProjectIdParam = Annotated[
    str | None,
    Field(
        description=(
            "Coroot project (cluster) id from get_projects. Optional when the "
            "server has a default project or the account can see only one."
        )
    ),
]

AppIdParam = Annotated[
    str,
    Field(
        description=(
            "Application id from list_applications, in the form "
            "'cluster_id:namespace:Kind:name', e.g. "
            "'hwvop6p7:default:Deployment:checkout'. Pass it back exactly as "
            "returned."
        )
    ),
]

FromParam = Annotated[
    str | None,
    Field(
        description=(
            "Start of the time window: 'now-1h', a bare duration like '30m', an "
            "epoch timestamp, or an ISO-8601 date. Defaults to one hour ago."
        )
    ),
]

ToParam = Annotated[
    str | None,
    Field(
        description=(
            "End of the time window, same formats as from_time. Defaults to now."
        )
    ),
]


def context(ctx: ToolContext) -> AppState:
    """The lifespan state behind a tool call."""
    return state_of(ctx)


async def target(ctx: ToolContext, project_id: str | None) -> tuple[AppState, str]:
    """Resolve the state and the project a tool should act on."""
    state = state_of(ctx)
    return state, await state.resolve_project(project_id)


def respond(
    state: AppState, payload: dict[str, Any], *, summarise: bool = True
) -> dict[str, Any]:
    """Summarise and budget a tool response.

    ``summarise=False`` keeps the payload verbatim and only enforces the
    character budget. Use it for configuration a caller has to send back
    unchanged: the summarising pass drops presentation fields, which are exactly
    the settings in a saved dashboard panel.
    """
    if summarise:
        compacted = compact(payload)
        payload = compacted if isinstance(compacted, dict) else {"data": compacted}
    return fit(payload, state.settings.max_output_chars)


def ok(message: str, **fields: Any) -> dict[str, Any]:
    """A small confirmation payload for write tools."""
    return {"ok": True, "message": message, **fields}
