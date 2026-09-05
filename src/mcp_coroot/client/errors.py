"""Typed exceptions raised by the Coroot client.

Coroot reports errors as ``text/plain`` bodies (no JSON envelope), so every error
carries the HTTP status, the server's message and the request path. Tool code maps
these onto MCP ``ToolError`` messages the model can act on.
"""

from __future__ import annotations


class CorootError(Exception):
    """Base class for all client errors."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        detail: str | None = None,
        path: str | None = None,
        hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.detail = detail or None
        self.path = path
        self.hint = hint

    def __str__(self) -> str:
        text = self.message
        if self.status_code is not None:
            text = f"{text} (HTTP {self.status_code})"
        if self.detail:
            text = f"{text}: {self.detail}"
        if self.hint:
            text = f"{text}. {self.hint}"
        return text


class CorootConnectionError(CorootError):
    """Coroot could not be reached (DNS, TCP, TLS or timeout failure)."""


class CorootAuthenticationError(CorootError):
    """The session is missing, expired or the credentials were rejected."""


class CorootPermissionError(CorootError):
    """The authenticated user lacks the RBAC permission for the request."""


class CorootNotFoundError(CorootError):
    """The project, application, node, incident, alert or rule does not exist."""


class CorootValidationError(CorootError):
    """Coroot rejected the request body or query parameters."""


class CorootConflictError(CorootError):
    """The resource already exists (duplicate project, user or category name)."""


class CorootServerError(CorootError):
    """Coroot failed internally (database, cache or ClickHouse error)."""


class CorootUnsupportedError(CorootError):
    """The endpoint does not exist on this Coroot version or edition."""


_AUTH_HINT = (
    "Check COROOT_USERNAME/COROOT_PASSWORD or supply a fresh COROOT_SESSION_COOKIE"
)
_BOOTSTRAP_HINT = (
    "This Coroot instance has no admin password yet. Open its web UI once to set "
    "one (or start Coroot with --auth-bootstrap-admin-password)"
)


def error_from_status(status_code: int, detail: str, path: str) -> CorootError:
    """Translate an HTTP error response into the matching exception."""
    detail = detail.strip()
    if status_code == 401:
        if detail == "set_admin_password":
            return CorootAuthenticationError(
                "Coroot is not initialised",
                status_code=status_code,
                path=path,
                hint=_BOOTSTRAP_HINT,
            )
        return CorootAuthenticationError(
            "Authentication required",
            status_code=status_code,
            detail=detail,
            path=path,
            hint=_AUTH_HINT,
        )
    if status_code == 403:
        return CorootPermissionError(
            "Permission denied",
            status_code=status_code,
            detail=detail or "the current user's role does not allow this action",
            path=path,
        )
    if status_code == 404:
        return CorootNotFoundError(
            "Not found", status_code=status_code, detail=detail, path=path
        )
    if status_code == 405:
        return CorootUnsupportedError(
            "Operation not supported by this Coroot edition",
            status_code=status_code,
            detail=detail,
            path=path,
        )
    if status_code == 409:
        return CorootConflictError(
            "Conflict", status_code=status_code, detail=detail, path=path
        )
    if status_code == 400:
        return CorootValidationError(
            "Invalid request",
            status_code=status_code,
            detail=detail or "Coroot rejected the request parameters",
            path=path,
        )
    if status_code >= 500:
        return CorootServerError(
            "Coroot server error", status_code=status_code, detail=detail, path=path
        )
    return CorootError(
        "Unexpected response", status_code=status_code, detail=detail, path=path
    )
