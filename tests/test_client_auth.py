"""Tests for client authentication functionality."""

from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from mcp_coroot.client import CorootClient, CorootError


class TestClientInitialization:
    """Test client initialization and configuration."""

    def test_init_with_direct_params(self):
        """Test client initialization with direct parameters."""
        client = CorootClient(
            base_url="http://example.com",
            api_key="key",
            session_cookie="cookie",
            username="user",
            password="pass",
        )
        assert client.base_url == "http://example.com"
        assert client.api_key == "key"
        assert client.session_cookie == "cookie"
        assert client.username == "user"
        assert client.password == "pass"

    def test_init_with_env_vars(self):
        """Test client initialization with environment variables."""
        with patch.dict(
            "os.environ",
            {
                "COROOT_BASE_URL": "http://env.example.com",
                "COROOT_API_KEY": "env-key",
                "COROOT_SESSION_COOKIE": "env-cookie",
                "COROOT_USERNAME": "env-user",
                "COROOT_PASSWORD": "env-pass",
            },
        ):
            client = CorootClient()
            assert client.base_url == "http://env.example.com"
            assert client.api_key == "env-key"
            assert client.session_cookie == "env-cookie"
            assert client.username == "env-user"
            assert client.password == "env-pass"

    def test_base_url_trailing_slash(self):
        """Test that base URL trailing slash is removed."""
        client = CorootClient(base_url="http://example.com/")
        assert client.base_url == "http://example.com"

    def test_default_base_url(self):
        """Test default base URL when not provided."""
        with patch.dict("os.environ", {}, clear=True):
            client = CorootClient()
            assert client.base_url == "http://localhost:8080"


class TestAuthentication:
    """Test authentication methods."""

    @pytest.mark.asyncio
    async def test_login_success(self, client):
        """Test successful login."""
        mock_response = AsyncMock()
        mock_response.cookies = {"coroot_session": "new-session-cookie"}
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            cookie = await client.login("user@example.com", "password")
            assert cookie == "new-session-cookie"

    @pytest.mark.asyncio
    async def test_login_no_cookie(self, client):
        """Test login with no cookie in response."""
        mock_response = AsyncMock()
        mock_response.cookies = {}
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            with pytest.raises(CorootError, match="no session cookie"):
                await client.login("user@example.com", "password")

    @pytest.mark.asyncio
    async def test_logout(self, client):
        """Test logout functionality."""
        mock_response = AsyncMock()
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response) as mock_req:
            await client.logout()
            mock_req.assert_called_once()
            call_args = mock_req.call_args
            assert call_args[0][0] == "POST"
            assert "/api/logout" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_automatic_login(self, client_with_creds):
        """Test automatic login when credentials are provided."""
        # Mock the login response
        login_response = AsyncMock()
        login_response.cookies = {"coroot_session": "auto-login-cookie"}
        login_response.raise_for_status = AsyncMock()

        # Mock the user response (list_projects now uses /api/user)
        user_response = AsyncMock()
        user_response.json = Mock(
            return_value={
                "email": "test@example.com",
                "projects": [{"id": "p1", "name": "Project 1"}],
            }
        )
        user_response.raise_for_status = AsyncMock()
        user_response.headers = {"content-type": "application/json"}

        with patch("httpx.AsyncClient.request") as mock_request:
            # First call will be the auto-login, second will be get_user
            mock_request.side_effect = [login_response, user_response]

            # This should trigger automatic login
            projects = await client_with_creds.list_projects()

            assert len(projects) == 1
            assert client_with_creds.session_cookie == "auto-login-cookie"
            assert mock_request.call_count == 2  # login + get_user

    @pytest.mark.asyncio
    async def test_automatic_login_failure_continues(self, client_with_creds):
        """Test that automatic login failure doesn't block requests."""
        # Mock failed login
        login_error = httpx.HTTPStatusError(
            "401 Client Error",
            request=AsyncMock(),
            response=AsyncMock(status_code=401, text="Unauthorized"),
        )

        # Mock the actual request also failing with auth error
        request_error = httpx.HTTPStatusError(
            "401 Client Error",
            request=AsyncMock(),
            response=AsyncMock(status_code=401, text="Unauthorized"),
        )

        with patch("httpx.AsyncClient.request") as mock_request:
            mock_request.side_effect = [login_error, request_error]

            with pytest.raises(CorootError, match="Authentication failed"):
                await client_with_creds.list_projects()

    @pytest.mark.asyncio
    async def test_get_current_user(self, client, mock_user):
        """Test getting current user information."""
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value=mock_user)
        mock_response.raise_for_status = AsyncMock()
        mock_response.headers = {"content-type": "application/json"}

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            user = await client.get_current_user()
            assert user == mock_user

    @pytest.mark.asyncio
    async def test_auth_headers_with_api_key(self, client):
        """Test that API key is included in headers when specified."""
        headers = client._get_auth_headers(use_api_key=True)
        assert headers["X-API-Key"] == "test-api-key"

    @pytest.mark.asyncio
    async def test_auth_headers_without_api_key(self, client):
        """Test headers without API key."""
        headers = client._get_auth_headers(use_api_key=False)
        assert "X-API-Key" not in headers

    def test_get_cookies_with_session(self, client):
        """Test cookie generation with session."""
        cookies = client._get_cookies()
        assert cookies["coroot_session"] == "test-session-cookie"

    def test_get_cookies_without_session(self, client_minimal):
        """Test cookie generation without session."""
        cookies = client_minimal._get_cookies()
        assert cookies == {}


class TestErrorHandling:
    """Test error handling in authentication."""

    @pytest.mark.asyncio
    async def test_authentication_error(self, client):
        """Test handling of authentication errors."""
        mock_response = AsyncMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"

        error = httpx.HTTPStatusError(
            "401 Client Error",
            request=AsyncMock(),
            response=mock_response,
        )

        with patch("httpx.AsyncClient.request", side_effect=error):
            with pytest.raises(CorootError, match="Authentication failed"):
                await client.list_projects()

    @pytest.mark.asyncio
    async def test_no_base_url_error(self):
        """Test error when base URL is not configured."""
        client = CorootClient()
        client.base_url = None  # type: ignore

        with pytest.raises(CorootError, match="Base URL not configured"):
            await client.list_projects()
