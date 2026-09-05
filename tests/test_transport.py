"""Tests for the HTTP transport: auth flows, retries and body decoding."""

from __future__ import annotations

import httpx2 as httpx
import pytest

from mcp_coroot.client.base import Transport, decode_body, split_envelope
from mcp_coroot.client.errors import (
    CorootAuthenticationError,
    CorootConflictError,
    CorootConnectionError,
    CorootError,
    CorootNotFoundError,
    CorootPermissionError,
    CorootServerError,
    CorootUnsupportedError,
    CorootValidationError,
)
from mcp_coroot.config import SESSION_COOKIE_NAME, Settings
from tests.conftest import FakeCoroot


async def test_lazy_login_then_cookie_reuse(
    fake: FakeCoroot, settings: Settings
) -> None:
    fake.on("GET", "/api/user", {"email": "admin"})
    with_transport = Transport(settings, transport=httpx.MockTransport(fake))
    try:
        assert await with_transport.get("/api/user") == {"email": "admin"}
        assert await with_transport.get("/api/user") == {"email": "admin"}
    finally:
        await with_transport.aclose()
    methods = [(r.method, r.url.path) for r in fake.requests]
    assert methods == [
        ("POST", "/api/login"),
        ("GET", "/api/user"),
        ("GET", "/api/user"),
    ]
    login_body = fake.body(fake.requests[0])
    assert login_body == {"email": "admin", "password": "secret", "action": ""}
    assert SESSION_COOKIE_NAME in fake.requests[2].headers["cookie"]


async def test_session_cookie_is_sent_without_login(fake: FakeCoroot) -> None:
    fake.on("GET", "/api/user", {"email": "sso"})
    settings = Settings(base_url="http://coroot.test", session_cookie="session-token")
    transport = Transport(settings, transport=httpx.MockTransport(fake))
    try:
        assert await transport.get("/api/user") == {"email": "sso"}
    finally:
        await transport.aclose()
    assert [r.url.path for r in fake.requests] == ["/api/user"]


async def test_expired_session_triggers_single_relogin(
    fake: FakeCoroot, settings: Settings
) -> None:
    fake.on("GET", "/api/user", {"email": "admin"})
    transport = Transport(settings, transport=httpx.MockTransport(fake))
    try:
        await transport.get("/api/user")
        fake.session_cookie = "rotated"  # server no longer accepts the old cookie
        assert await transport.get("/api/user") == {"email": "admin"}
    finally:
        await transport.aclose()
    methods = [(r.method, r.url.path) for r in fake.requests]
    assert methods == [
        ("POST", "/api/login"),
        ("GET", "/api/user"),
        ("GET", "/api/user"),  # 401
        ("POST", "/api/login"),
        ("GET", "/api/user"),
    ]


async def test_bad_password_raises_authentication_error(fake: FakeCoroot) -> None:
    settings = Settings(
        base_url="http://coroot.test", username="admin", password="nope"
    )
    transport = Transport(settings, transport=httpx.MockTransport(fake))
    try:
        with pytest.raises(CorootAuthenticationError) as excinfo:
            await transport.get("/api/user")
    finally:
        await transport.aclose()
    assert "Login failed" in str(excinfo.value)
    assert excinfo.value.status_code == 404


async def test_no_credentials_yields_401_error(fake: FakeCoroot) -> None:
    settings = Settings(base_url="http://coroot.test")
    transport = Transport(settings, transport=httpx.MockTransport(fake))
    try:
        with pytest.raises(CorootAuthenticationError) as excinfo:
            await transport.get("/api/user")
    finally:
        await transport.aclose()
    assert excinfo.value.status_code == 401
    assert "COROOT_USERNAME" in str(excinfo.value)


async def test_bootstrap_hint(fake: FakeCoroot) -> None:
    fake.require_auth = False
    fake.on("GET", "/api/user", status=401, text="set_admin_password")
    settings = Settings(base_url="http://coroot.test")
    transport = Transport(settings, transport=httpx.MockTransport(fake))
    try:
        with pytest.raises(CorootAuthenticationError) as excinfo:
            await transport.get("/api/user")
    finally:
        await transport.aclose()
    assert "admin password" in str(excinfo.value)


async def test_api_key_header(fake: FakeCoroot) -> None:
    fake.on("GET", "/api/v1/series", {"status": "success", "data": []})
    settings = Settings(base_url="http://coroot.test", api_key=fake.api_key)
    transport = Transport(settings, transport=httpx.MockTransport(fake))
    try:
        data = await transport.get("/api/v1/series", use_api_key=True)
    finally:
        await transport.aclose()
    assert data["status"] == "success"
    assert fake.last.headers["X-API-Key"] == fake.api_key


async def test_wrong_api_key_is_rejected(fake: FakeCoroot) -> None:
    # Coroot answers an unknown key with 404 "no project found"; sending an
    # empty or wrong key must not look like success.
    fake.on("GET", "/api/v1/series", {"status": "success", "data": []})
    settings = Settings(base_url="http://coroot.test", api_key="not-the-key")
    transport = Transport(settings, transport=httpx.MockTransport(fake))
    try:
        with pytest.raises(CorootNotFoundError, match="no project found"):
            await transport.get("/api/v1/series", use_api_key=True)
    finally:
        await transport.aclose()


async def test_session_cookie_is_not_accepted_on_api_key_routes(
    fake: FakeCoroot, settings: Settings
) -> None:
    # Coroot's two middlewares are separate: a cookie does not authenticate
    # /api/v1, and a key does not authenticate /api/project.
    fake.on("GET", "/api/v1/series", {"status": "success"})
    transport = Transport(settings, transport=httpx.MockTransport(fake))
    try:
        with pytest.raises(CorootValidationError, match="no api key"):
            await transport.get("/api/v1/series")
    finally:
        await transport.aclose()


async def test_wrong_method_on_a_known_path_is_reported_as_unsupported(
    fake: FakeCoroot, settings: Settings
) -> None:
    # gorilla answers a registered path with an unregistered method as 405,
    # which is a different failure from an unknown path.
    fake.on("GET", "/api/project/p1/alerts", {"alerts": []})
    transport = Transport(settings, transport=httpx.MockTransport(fake))
    try:
        with pytest.raises(CorootUnsupportedError) as excinfo:
            await transport.post("/api/project/p1/alerts")
    finally:
        await transport.aclose()
    assert excinfo.value.status_code == 405


async def test_api_key_missing(fake: FakeCoroot) -> None:
    settings = Settings(base_url="http://coroot.test")
    transport = Transport(settings, transport=httpx.MockTransport(fake))
    try:
        with pytest.raises(CorootAuthenticationError, match="COROOT_API_KEY"):
            await transport.get("/api/v1/series", use_api_key=True)
    finally:
        await transport.aclose()


@pytest.mark.parametrize(
    ("status", "text", "exc"),
    [
        (400, "Invalid form", CorootValidationError),
        (403, "You are not allowed to configure the project.", CorootPermissionError),
        (404, "Application not found", CorootNotFoundError),
        (405, "", CorootUnsupportedError),
        (409, "This project name is already being used.", CorootConflictError),
        (500, "ClickHouse is not available", CorootServerError),
        (418, "teapot", CorootError),
    ],
)
async def test_status_mapping(
    fake: FakeCoroot, settings: Settings, status: int, text: str, exc: type[CorootError]
) -> None:
    fake.on("GET", "/api/project/p1", status=status, text=text)
    transport = Transport(settings, transport=httpx.MockTransport(fake))
    try:
        with pytest.raises(exc) as excinfo:
            await transport.get("/api/project/p1")
    finally:
        await transport.aclose()
    assert excinfo.value.status_code == status
    if text:
        assert text in str(excinfo.value)
    assert excinfo.value.path == "/api/project/p1"


async def test_unknown_route_returns_spa_html(
    fake: FakeCoroot, settings: Settings
) -> None:
    transport = Transport(settings, transport=httpx.MockTransport(fake))
    try:
        with pytest.raises(CorootUnsupportedError):
            await transport.get("/api/sso-status")
    finally:
        await transport.aclose()


async def test_params_are_cleaned(fake: FakeCoroot, settings: Settings) -> None:
    fake.on("GET", "/api/project/p1/alerts", {"alerts": []})
    transport = Transport(settings, transport=httpx.MockTransport(fake))
    try:
        await transport.get(
            "/api/project/p1/alerts",
            params={
                "include_resolved": True,
                "limit": 5,
                "search": None,
                "ids": ["a", "b"],
            },
        )
    finally:
        await transport.aclose()
    query = dict(fake.last.url.params.multi_items())
    assert fake.last.url.params.get_list("ids") == ["a", "b"]
    assert query["include_resolved"] == "true"
    assert query["limit"] == "5"
    assert "search" not in query


async def test_connection_errors(settings: Settings) -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    transport = Transport(settings, transport=httpx.MockTransport(boom))
    try:
        with pytest.raises(CorootConnectionError, match="Could not reach"):
            await transport.get("/api/user")
    finally:
        await transport.aclose()

    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    transport = Transport(settings, transport=httpx.MockTransport(slow))
    try:
        with pytest.raises(CorootConnectionError, match="did not answer"):
            await transport.get("/api/user")
    finally:
        await transport.aclose()


async def test_logout_clears_cookie(fake: FakeCoroot, settings: Settings) -> None:
    fake.on("GET", "/api/user", {"email": "admin"})
    fake.on("POST", "/api/logout")
    transport = Transport(settings, transport=httpx.MockTransport(fake))
    try:
        await transport.get("/api/user")
        await transport.logout()
        await transport.get("/api/user")
    finally:
        await transport.aclose()
    methods = [(r.method, r.url.path) for r in fake.requests]
    assert methods.count(("POST", "/api/login")) == 2


def test_decode_body_variants() -> None:
    req = httpx.Request("GET", "http://coroot.test/x")
    assert decode_body(httpx.Response(204, request=req), "/x") is None
    assert decode_body(httpx.Response(200, text="  ", request=req), "/x") is None
    assert decode_body(httpx.Response(200, json={"a": 1}, request=req), "/x") == {
        "a": 1
    }
    plain = httpx.Response(
        200,
        text="abcd1234\n",
        headers={"content-type": "text/plain; charset=utf-8"},
        request=req,
    )
    assert decode_body(plain, "/x") == "abcd1234"
    weird = httpx.Response(
        200, text="<xml/>", headers={"content-type": "application/xml"}, request=req
    )
    with pytest.raises(CorootError, match="non-JSON"):
        decode_body(weird, "/x")


def test_split_envelope() -> None:
    env = split_envelope(
        {
            "context": {
                "status": {"status": "ok"},
                "search": {
                    "applications": [{"id": "c:ns:Deployment:a"}],
                    "nodes": [{"name": "n1"}],
                },
            },
            "data": {"x": 1},
        }
    )
    assert env.data == {"x": 1}
    assert env.status == {"status": "ok"}
    assert env.known_applications == ["c:ns:Deployment:a"]
    assert env.known_nodes == ["n1"]
    bare = split_envelope([1, 2])
    assert bare.data == [1, 2]
    assert bare.context == {}
    assert bare.known_applications == []
