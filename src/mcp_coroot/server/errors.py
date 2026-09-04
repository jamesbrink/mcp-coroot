"""Translate client exceptions into MCP tool errors.

Every tool is wrapped with :func:`guard`, which turns a :class:`CorootError` into
a :class:`ToolError`. The MCP SDK reports those as ``isError`` results carrying the
message, so the model can correct itself instead of seeing a traceback.
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar

from mcp.server.mcpserver.exceptions import ToolError

from ..client import (
    CorootAuthenticationError,
    CorootConflictError,
    CorootConnectionError,
    CorootError,
    CorootNotFoundError,
    CorootPermissionError,
    CorootServerError,
    CorootUnsupportedError,
    InvalidApplicationId,
    InvalidTimeError,
)

logger = logging.getLogger("mcp_coroot.server")

P = ParamSpec("P")
R = TypeVar("R")

_ADVICE: dict[type[CorootError], str] = {
    CorootNotFoundError: (
        "Verify the id with list_projects, list_applications, list_nodes, "
        "list_incidents or list_alerts"
    ),
    CorootPermissionError: "This account's Coroot role does not allow the action",
    CorootConflictError: "Choose a different name, or update the existing object",
    CorootUnsupportedError: (
        "This endpoint is not available on the connected Coroot version or edition"
    ),
    CorootServerError: (
        "Coroot itself failed; check its logs and its ClickHouse/Prometheus "
        "integrations with get_project_status"
    ),
}


def describe(error: Exception) -> str:
    """Build the message shown to the model."""
    if isinstance(error, InvalidApplicationId | InvalidTimeError):
        return str(error)
    if isinstance(error, CorootError):
        text = str(error)
        advice = _ADVICE.get(type(error))
        if advice and not error.hint:
            text = f"{text}. {advice}"
        return text
    return str(error)


def guard(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    """Wrap a tool implementation so Coroot failures become tool errors."""

    @functools.wraps(fn)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await fn(*args, **kwargs)
        except ToolError:
            raise
        except (
            CorootError,
            InvalidApplicationId,
            InvalidTimeError,
            ValueError,
        ) as exc:
            level = (
                logging.WARNING
                if isinstance(
                    exc,
                    CorootAuthenticationError
                    | CorootConnectionError
                    | CorootServerError,
                )
                else logging.INFO
            )
            logger.log(level, "%s failed: %s", fn.__name__, exc)
            raise ToolError(describe(exc)) from exc

    return wrapper


def one_of(value: str, allowed: tuple[str, ...], *, name: str) -> str:
    """Validate an enum-like argument, listing the valid values on failure."""
    candidate = value.strip()
    if candidate not in allowed:
        raise ToolError(f"{name} must be one of: {', '.join(allowed)} (got {value!r})")
    return candidate
