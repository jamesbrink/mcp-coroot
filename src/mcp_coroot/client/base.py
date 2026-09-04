"""HTTP transport for the Coroot API.

One pooled :class:`httpx2.AsyncClient` lives for the whole server lifetime. Login
happens lazily on the first request and again, once, when a request comes back 401
(session cookies expire after seven days). Responses are decoded here so the
resource modules only deal with JSON values.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx2 as httpx

from .. import __version__
from ..config import API_KEY_HEADER, SESSION_COOKIE_NAME, Settings
from .errors import (
    CorootAuthenticationError,
    CorootConnectionError,
    CorootError,
    CorootUnsupportedError,
    error_from_status,
)
from .ids import encode_segment

logger = logging.getLogger("mcp_coroot.client")

JsonValue = Any
Params = Mapping[str, object] | None

_NO_LOGIN_HINT = (
    "Set COROOT_USERNAME and COROOT_PASSWORD, or COROOT_SESSION_COOKIE, to use "
    "the management API"
)


def clean_params(params: Params) -> dict[str, str | list[str]] | None:
    """Drop ``None`` values and render scalars the way Coroot expects."""
    if not params:
        return None
    cleaned: dict[str, str | list[str]] = {}
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, bool):
            cleaned[key] = "true" if value else "false"
        elif isinstance(value, list | tuple):
            cleaned[key] = [str(item) for item in value]
        else:
            cleaned[key] = str(value)
    return cleaned or None


@dataclass(slots=True)
class Enveloped:
    """A response that Coroot wrapped in ``{"context": ..., "data": ...}``.

    ``context`` carries project-wide status (metrics source health, open incident
    and firing alert counts, the application/node search index); ``data`` is the
    endpoint payload.
    """

    data: JsonValue
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def status(self) -> dict[str, Any]:
        status = self.context.get("status")
        return status if isinstance(status, dict) else {}

    @property
    def known_applications(self) -> list[str]:
        search = self.context.get("search") or {}
        apps = search.get("applications") if isinstance(search, dict) else None
        if not isinstance(apps, list):
            return []
        return [str(app.get("id")) for app in apps if isinstance(app, dict)]

    @property
    def known_nodes(self) -> list[str]:
        search = self.context.get("search") or {}
        nodes = search.get("nodes") if isinstance(search, dict) else None
        if not isinstance(nodes, list):
            return []
        return [str(node.get("name")) for node in nodes if isinstance(node, dict)]


def split_envelope(payload: JsonValue) -> Enveloped:
    """Separate a world envelope; un-enveloped payloads get an empty context."""
    if (
        isinstance(payload, dict)
        and set(payload) == {"context", "data"}
        and isinstance(payload["context"], dict)
    ):
        return Enveloped(data=payload["data"], context=payload["context"])
    return Enveloped(data=payload)


class Transport:
    """Authenticated HTTP transport with connection pooling."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._http = httpx.AsyncClient(
            base_url=settings.base_url,
            timeout=settings.timeout,
            verify=settings.verify_ssl,
            transport=transport,
            headers={
                "Accept": "application/json",
                "User-Agent": f"mcp-coroot/{__version__}",
            },
            follow_redirects=False,
        )
        self._login_lock = asyncio.Lock()
        self._logged_in = False
        if settings.session_cookie:
            self._http.cookies.set(SESSION_COOKIE_NAME, settings.session_cookie)
            self._logged_in = True

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def base_url(self) -> str:
        return self._settings.base_url

    async def aclose(self) -> None:
        await self._http.aclose()

    # -- authentication ---------------------------------------------------------

    async def login(self) -> None:
        """Log in with the configured username/password and store the cookie."""
        settings = self._settings
        if not settings.can_login:
            raise CorootAuthenticationError(
                "No Coroot credentials configured", hint=_NO_LOGIN_HINT
            )
        body = {"email": settings.username, "password": settings.password, "action": ""}
        try:
            response = await self._http.post("/api/login", json=body)
        except httpx.HTTPError as exc:
            raise self._connection_error("/api/login", exc) from exc
        if response.status_code in {400, 401, 403, 404}:
            raise CorootAuthenticationError(
                "Login failed",
                status_code=response.status_code,
                detail=response.text.strip() or "invalid email or password",
                path="/api/login",
                hint="Check COROOT_USERNAME and COROOT_PASSWORD",
            )
        if response.status_code >= 400:
            raise error_from_status(response.status_code, response.text, "/api/login")
        cookie = response.cookies.get(SESSION_COOKIE_NAME)
        if not cookie:
            raise CorootAuthenticationError(
                "Login succeeded but Coroot did not return a session cookie",
                path="/api/login",
            )
        self._http.cookies.set(SESSION_COOKIE_NAME, cookie)
        self._logged_in = True
        logger.info("Logged in to Coroot at %s as %s", self.base_url, settings.username)

    async def logout(self) -> None:
        """Invalidate the session cookie on the client side and tell Coroot."""
        try:
            await self._http.post("/api/logout")
        finally:
            self._http.cookies.delete(SESSION_COOKIE_NAME)
            self._logged_in = False

    async def _ensure_session(self) -> None:
        if self._logged_in or not self._settings.can_login:
            return
        async with self._login_lock:
            if not self._logged_in:
                await self.login()

    # -- requests ---------------------------------------------------------------

    def _connection_error(self, path: str, exc: Exception) -> CorootConnectionError:
        if isinstance(exc, httpx.TimeoutException):
            return CorootConnectionError(
                f"Coroot did not answer within {self._settings.timeout:g}s",
                path=path,
                hint="Raise COROOT_TIMEOUT or narrow the time range",
            )
        return CorootConnectionError(
            f"Could not reach Coroot at {self.base_url}",
            detail=str(exc) or exc.__class__.__name__,
            path=path,
            hint="Check COROOT_BASE_URL and network connectivity",
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Params = None,
        json_body: JsonValue = None,
        headers: Mapping[str, str] | None = None,
        use_api_key: bool = False,
    ) -> httpx.Response:
        """Send a request and return the raw response (raises on HTTP errors)."""
        request_headers = dict(headers or {})
        if use_api_key:
            if not self._settings.api_key:
                raise CorootAuthenticationError(
                    "COROOT_API_KEY is required for this endpoint",
                    path=path,
                    hint="Create a project API key in Coroot and set COROOT_API_KEY",
                )
            request_headers[API_KEY_HEADER] = self._settings.api_key
        else:
            await self._ensure_session()

        response = await self._send(method, path, params, json_body, request_headers)
        if response.status_code == 401 and not use_api_key and self._settings.can_login:
            logger.info("Session rejected by Coroot; logging in again")
            self._logged_in = False
            await self._ensure_session()
            response = await self._send(
                method, path, params, json_body, request_headers
            )
        if response.status_code >= 400:
            raise error_from_status(response.status_code, response.text, path)
        return response

    async def _send(
        self,
        method: str,
        path: str,
        params: Params,
        json_body: JsonValue,
        headers: dict[str, str],
    ) -> httpx.Response:
        try:
            return await self._http.request(
                method,
                path,
                params=clean_params(params),
                json=json_body,
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise self._connection_error(path, exc) from exc

    async def request_json(
        self,
        method: str,
        path: str,
        *,
        params: Params = None,
        json_body: JsonValue = None,
        headers: Mapping[str, str] | None = None,
        use_api_key: bool = False,
    ) -> JsonValue:
        """Send a request and decode the body (``None`` for empty bodies)."""
        response = await self.request(
            method,
            path,
            params=params,
            json_body=json_body,
            headers=headers,
            use_api_key=use_api_key,
        )
        return decode_body(response, path)

    async def request_text(
        self,
        method: str,
        path: str,
        *,
        params: Params = None,
        json_body: JsonValue = None,
    ) -> str:
        """Send a request and return the stripped text body."""
        response = await self.request(method, path, params=params, json_body=json_body)
        _reject_html(response, path)
        return response.text.strip()

    async def get(
        self, path: str, *, params: Params = None, use_api_key: bool = False
    ) -> JsonValue:
        return await self.request_json(
            "GET", path, params=params, use_api_key=use_api_key
        )

    async def post(
        self, path: str, json_body: JsonValue = None, *, params: Params = None
    ) -> JsonValue:
        return await self.request_json("POST", path, params=params, json_body=json_body)

    async def put(self, path: str, json_body: JsonValue = None) -> JsonValue:
        return await self.request_json("PUT", path, json_body=json_body)

    async def delete(self, path: str) -> JsonValue:
        return await self.request_json("DELETE", path)


def _reject_html(response: httpx.Response, path: str) -> None:
    content_type = response.headers.get("content-type", "")
    if "text/html" in content_type:
        raise CorootUnsupportedError(
            "Endpoint not available on this Coroot version",
            status_code=response.status_code,
            path=path,
            hint="Upgrade Coroot or check COROOT_BASE_URL (the server returned "
            "its web UI instead of an API response)",
        )


def decode_body(response: httpx.Response, path: str) -> JsonValue:
    """Decode a successful response body.

    * ``204`` or an empty body -> ``None``
    * JSON -> parsed value
    * ``text/plain`` (Coroot returns new ids this way) -> the stripped string
    * ``text/html`` (the SPA catch-all) -> :class:`CorootUnsupportedError`
    """
    if response.status_code == 204:
        return None
    text = response.text.strip()
    if not text:
        return None
    _reject_html(response, path)
    try:
        return json.loads(text)
    except ValueError:
        content_type = response.headers.get("content-type", "")
        if content_type.startswith("text/plain"):
            return text
        raise CorootError(
            "Unexpected non-JSON response from Coroot",
            status_code=response.status_code,
            detail=text[:200],
            path=path,
        ) from None


class BaseAPI:
    """Base class for the per-domain API groups."""

    def __init__(self, transport: Transport) -> None:
        self._t = transport

    @staticmethod
    def project_path(project_id: str, *segments: str) -> str:
        """Build ``/api/project/{id}/...`` with each segment percent-encoded."""
        if not project_id or not project_id.strip():
            raise CorootError("project id must not be empty")
        parts = [encode_segment(project_id.strip()), *segments]
        return "/api/project/" + "/".join(parts)
