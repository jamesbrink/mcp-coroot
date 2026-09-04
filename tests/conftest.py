"""Shared fixtures: an in-memory fake Coroot served through httpx2.MockTransport."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx2 as httpx
import pytest

from mcp_coroot.config import SESSION_COOKIE_NAME, Settings

Handler = Callable[[httpx.Request], httpx.Response]


def raw_path(request: httpx.Request) -> str:
    """The request path as sent on the wire (percent-encoding preserved).

    Coroot registers its routes with ``UseEncodedPath``, so application and node
    ids reach the server encoded; matching on the decoded path would hide
    encoding bugs.
    """
    return request.url.raw_path.decode("ascii").split("?", 1)[0]


@dataclass
class FakeCoroot:
    """Minimal scripted Coroot backend.

    Register responses with :meth:`on`; every request is recorded in ``requests``
    so tests can assert on paths, query strings, bodies and cookies.
    """

    routes: dict[tuple[str, str], Handler] = field(default_factory=dict)
    requests: list[httpx.Request] = field(default_factory=list)
    session_cookie: str = "session-token"
    username: str = "admin"
    password: str = "secret"
    api_key: str = "test-api-key"
    require_auth: bool = True

    def on(
        self,
        method: str,
        path: str,
        body: Any = None,
        *,
        status: int = 200,
        text: str | None = None,
        content_type: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        def handler(_: httpx.Request) -> httpx.Response:
            hdrs = dict(headers or {})
            if text is not None:
                hdrs.setdefault("content-type", content_type or "text/plain")
                return httpx.Response(status, text=text, headers=hdrs)
            if body is None:
                return httpx.Response(status, headers=hdrs)
            hdrs.setdefault("content-type", content_type or "application/json")
            return httpx.Response(status, content=json.dumps(body), headers=hdrs)

        self.routes[(method.upper(), path)] = handler

    def handle(self, method: str, path: str, handler: Handler) -> None:
        self.routes[(method.upper(), path)] = handler

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = raw_path(request)
        if request.method == "POST" and path == "/api/login":
            # A test can script its own login (a proxy stripping the cookie, a
            # 500, a cookie the server then refuses).
            if custom := self.routes.get(("POST", "/api/login")):
                return custom(request)
            payload = json.loads(request.content or b"{}")
            if (
                payload.get("email") == self.username
                and payload.get("password") == self.password
            ):
                return httpx.Response(
                    200,
                    headers={
                        "set-cookie": f"{SESSION_COOKIE_NAME}={self.session_cookie}; "
                        "Path=/; HttpOnly"
                    },
                )
            return httpx.Response(404, text="Invalid email or password.\n")
        if path == "/health":
            return self.routes.get(("GET", "/health"), lambda _: httpx.Response(200))(
                request
            )
        if self.require_auth and (denied := self._check_auth(request, path)):
            return denied
        handler = self.routes.get((request.method, path))
        if handler is None:
            if any(route == path for _, route in self.routes):
                # gorilla answers a known path with an unknown method as 405.
                return httpx.Response(405, text="")
            # Coroot's SPA catch-all: unknown /api paths return HTML with 200.
            return httpx.Response(
                200,
                text="<!doctype html><html></html>",
                headers={"content-type": "text/html"},
            )
        return handler(request)

    def _check_auth(self, request: httpx.Request, path: str) -> httpx.Response | None:
        """Reject a request the way Coroot's two auth middlewares would.

        ``/api/v1/*`` and the ClickHouse routes take an API key and nothing
        else; every other ``/api/`` route takes the session cookie and ignores
        the key entirely.
        """
        key_route = path.startswith("/api/v1/") or path.startswith("/api/clickhouse")
        if key_route:
            key = request.headers.get("X-API-Key")
            if key is None:
                return httpx.Response(400, text="no api key")
            if key != self.api_key:
                return httpx.Response(404, text="no project found")
            return None
        if not path.startswith("/api/"):
            return None
        cookie = f"{SESSION_COOKIE_NAME}={self.session_cookie}"
        if cookie not in request.headers.get("cookie", ""):
            return httpx.Response(401, text="")
        return None

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]

    def calls(self, method: str, path: str) -> list[httpx.Request]:
        return [r for r in self.requests if r.method == method and raw_path(r) == path]

    @property
    def last_path(self) -> str:
        """The percent-encoded path of the most recent request."""
        return raw_path(self.last)

    @staticmethod
    def body(request: httpx.Request) -> Any:
        return json.loads(request.content)


@pytest.fixture
def fake() -> FakeCoroot:
    return FakeCoroot()


#: Every group, so a test can reach any tool. Production defaults to
#: `diagnose` alone; test_toolsets_select_what_is_registered covers that.
ALL_TOOLSETS = frozenset({"diagnose", "alerts", "dashboards", "config", "admin"})


@pytest.fixture
def settings() -> Settings:
    return Settings(
        base_url="http://coroot.test",
        username="admin",
        password="secret",
        toolsets=ALL_TOOLSETS,
    )


@pytest.fixture
def mock_transport(fake: FakeCoroot) -> httpx.MockTransport:
    return httpx.MockTransport(fake)
