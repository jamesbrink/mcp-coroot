"""Tests for the Coroot MCP client."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from mcp_coroot.client import CorootClient, CorootError

# ============================================================================
# Client Initialization and Authentication Tests
# ============================================================================


class TestClientInitialization:
    """Test client initialization."""

    def test_init_with_direct_params(self):
        """Test client initialization with direct parameters."""
        client = CorootClient(
            base_url="http://localhost:8080",
            username="admin",
            password="password",
            session_cookie="test-cookie",
            api_key="test-key",
        )

        assert client.base_url == "http://localhost:8080"
        assert client.username == "admin"
        assert client.password == "password"
        assert client.session_cookie == "test-cookie"
        assert client.api_key == "test-key"

    def test_init_with_env_vars(self, monkeypatch):
        """Test client initialization with environment variables."""
        monkeypatch.setenv("COROOT_BASE_URL", "http://env-url:8080")
        monkeypatch.setenv("COROOT_USERNAME", "env-user")
        monkeypatch.setenv("COROOT_PASSWORD", "env-pass")
        monkeypatch.setenv("COROOT_SESSION_COOKIE", "env-cookie")
        monkeypatch.setenv("COROOT_API_KEY", "env-key")

        client = CorootClient()

        assert client.base_url == "http://env-url:8080"
        assert client.username == "env-user"
        assert client.password == "env-pass"
        assert client.session_cookie == "env-cookie"
        assert client.api_key == "env-key"

    def test_base_url_trailing_slash(self):
        """Test that base URL trailing slash is removed."""
        client = CorootClient(base_url="http://localhost:8080/")
        assert client.base_url == "http://localhost:8080"

    def test_default_base_url(self, monkeypatch):
        """Test default base URL when not provided."""
        # Clear any environment variable
        monkeypatch.delenv("COROOT_BASE_URL", raising=False)

        client = CorootClient(username="admin", password="pass")
        assert client.base_url == "http://localhost:8080"

    def test_init_with_mixed_auth_env_vars(self, monkeypatch):
        """Test client initialization with both session cookie and username/password."""
        monkeypatch.setenv("COROOT_BASE_URL", "http://localhost:8080")
        monkeypatch.setenv("COROOT_USERNAME", "user")
        monkeypatch.setenv("COROOT_PASSWORD", "pass")
        monkeypatch.setenv("COROOT_SESSION_COOKIE", "existing-session")

        client = CorootClient()

        assert client.username == "user"
        assert client.password == "pass"
        assert client.session_cookie == "existing-session"

    async def test_auth_priority_session_cookie_over_credentials(self):
        """Test that session cookie takes priority over username/password."""
        client = CorootClient(
            base_url="http://localhost:8080",
            username="user",
            password="pass",
            session_cookie="existing-session",
        )

        # Mock the request to check headers
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value={"projects": []})
        mock_response.raise_for_status = AsyncMock()

        with patch(
            "httpx.AsyncClient.request", return_value=mock_response
        ) as mock_request:
            await client.list_projects()

        # Should use session cookie, not attempt login
        call_args = mock_request.call_args
        assert call_args.kwargs["cookies"]["coroot_session"] == "existing-session"
        # Login endpoint should not have been called
        assert mock_request.call_count == 1
        assert "/api/login" not in str(call_args.args[1])

    async def test_auth_fallback_to_credentials_no_session(self):
        """Test that credentials are used when no session cookie exists."""
        client = CorootClient(
            base_url="http://localhost:8080", username="user", password="pass"
        )

        # Mock login response
        mock_login_response = AsyncMock()
        mock_login_response.cookies = {"coroot_session": "new-session"}
        mock_login_response.raise_for_status = AsyncMock()

        # Mock actual API response
        mock_api_response = AsyncMock()
        mock_api_response.status_code = 200
        mock_api_response.json = Mock(return_value={"projects": []})
        mock_api_response.raise_for_status = AsyncMock()

        with patch(
            "httpx.AsyncClient.request",
            side_effect=[mock_login_response, mock_api_response],
        ) as mock_request:
            await client.list_projects()

        # Should have attempted login first
        assert mock_request.call_count == 2
        login_call = mock_request.call_args_list[0]
        assert "/api/login" in str(login_call.args[1])
        assert client.session_cookie == "new-session"


@pytest.mark.asyncio
class TestAuthentication:
    """Test authentication functionality."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return CorootClient(
            base_url="http://localhost:8080", username="admin", password="password"
        )

    async def test_login_success(self, client):
        """Test successful login."""
        mock_response = AsyncMock()
        mock_response.cookies = {"coroot_session": "test-session-cookie"}
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            cookie = await client.login("admin@example.com", "password")

        assert cookie == "test-session-cookie"
        # Note: login() doesn't set session_cookie directly, that happens in _request()

    async def test_login_no_cookie(self, client):
        """Test login failure when no cookie is returned."""
        mock_response = AsyncMock()
        mock_response.cookies = {}
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            with pytest.raises(
                CorootError, match="Login successful but no session cookie received"
            ):
                await client.login("admin@example.com", "password")

    async def test_logout(self, client):
        """Test logout functionality."""
        client.session_cookie = "test-session-cookie"

        mock_response = AsyncMock()
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            await client.logout()

        # Session cookie should remain as logout doesn't clear it in the client
        assert client.session_cookie == "test-session-cookie"

    async def test_automatic_login(self, client):
        """Test automatic login when credentials are available."""
        # Mock the login response
        mock_login_response = AsyncMock()
        mock_login_response.cookies = {"coroot_session": "auto-login-cookie"}
        mock_login_response.raise_for_status = AsyncMock()

        # Mock the actual API response
        mock_api_response = AsyncMock()
        mock_api_response.json = Mock(return_value={"test": "data"})
        mock_api_response.raise_for_status = AsyncMock()

        with patch(
            "httpx.AsyncClient.request",
            side_effect=[mock_login_response, mock_api_response],
        ):
            response = await client._request("GET", "/api/test")

        assert client.session_cookie == "auto-login-cookie"
        assert response.json() == {"test": "data"}

    async def test_automatic_login_failure_continues(self, client):
        """Test that automatic login failure doesn't prevent the request."""
        # Mock login failure
        mock_login_response = AsyncMock()
        mock_login_response.cookies = {}
        mock_login_response.raise_for_status = AsyncMock()

        # Mock the actual API response (will fail with 401)
        mock_api_response = AsyncMock()
        mock_api_response.status_code = 401
        mock_api_response.raise_for_status = Mock(side_effect=Exception("Unauthorized"))

        with patch(
            "httpx.AsyncClient.request",
            side_effect=[mock_login_response, mock_api_response],
        ):
            with pytest.raises(CorootError):
                await client._request("GET", "/api/test")

    async def test_get_current_user(self, client):
        """Test getting current user information."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={"id": "user123", "email": "admin@example.com"}
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            user = await client.get_current_user()

        assert user["id"] == "user123"
        assert user["email"] == "admin@example.com"

    def test_auth_headers_with_api_key(self, client):
        """Test authentication headers with API key."""
        client.api_key = "test-api-key"
        headers = client._get_auth_headers(use_api_key=True)

        assert headers["X-API-Key"] == "test-api-key"
        assert "Accept" in headers
        assert headers["Accept"] == "application/json"

    def test_auth_headers_without_api_key(self, client):
        """Test authentication headers without API key."""
        headers = client._get_auth_headers(use_api_key=False)

        assert "X-API-Key" not in headers
        assert "Accept" in headers

    def test_get_cookies_with_session(self, client):
        """Test getting cookies with session cookie."""
        client.session_cookie = "test-session"
        cookies = client._get_cookies()

        assert cookies["coroot_session"] == "test-session"

    def test_get_cookies_without_session(self, client):
        """Test getting cookies without session cookie."""
        client.session_cookie = None
        cookies = client._get_cookies()

        assert cookies == {}


@pytest.mark.asyncio
class TestAuthenticationErrorHandling:
    """Test authentication error handling."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return CorootClient(base_url="http://localhost:8080")

    async def test_authentication_failed_error(self, client):
        """Test handling of authentication failures."""
        import httpx

        mock_response = AsyncMock()
        mock_response.status_code = 401
        mock_response.text = "Invalid credentials"
        mock_request = Mock()
        mock_error = httpx.HTTPStatusError(
            "401 Error", request=mock_request, response=mock_response
        )
        mock_response.raise_for_status = Mock(side_effect=mock_error)

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            with pytest.raises(
                CorootError, match="Authentication failed: Invalid session cookie"
            ):
                await client._request("GET", "/api/test")

    async def test_401_unauthorized_error(self, client):
        """Test 401 error handling."""
        import httpx

        # Set up client with API key to test API key auth error
        client.api_key = "test-key"

        mock_response = AsyncMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        mock_request = Mock()
        mock_error = httpx.HTTPStatusError(
            "401", request=mock_request, response=mock_response
        )
        mock_response.raise_for_status = Mock(side_effect=mock_error)

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            with pytest.raises(
                CorootError, match="Authentication failed: Invalid API key"
            ):
                await client._request("GET", "/api/test", use_api_key=True)

    async def test_other_api_error(self, client):
        """Test handling of non-authentication API errors."""
        mock_response = AsyncMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.raise_for_status = Mock(side_effect=Exception("500 Server Error"))

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            with pytest.raises(CorootError, match="API request failed: 500"):
                await client._request("GET", "/api/test")

    async def test_validation_error(self, client):
        """Test handling of validation errors."""
        mock_response = AsyncMock()
        mock_response.status_code = 400
        mock_response.text = "Invalid request parameters"
        mock_response.raise_for_status = Mock(side_effect=Exception("400 Bad Request"))

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            with pytest.raises(CorootError, match="API request failed: 400"):
                await client._request("POST", "/api/test", json={"invalid": "data"})

    async def test_unexpected_error(self, client):
        """Test handling of unexpected errors."""
        with patch(
            "httpx.AsyncClient.request", side_effect=RuntimeError("Network error")
        ):
            with pytest.raises(CorootError, match="API request failed: Network error"):
                await client._request("GET", "/api/test")

    async def test_no_base_url_error(self):
        """Test error when base URL is not configured."""
        client = CorootClient()
        client.base_url = None  # Force None

        with pytest.raises(CorootError, match="Base URL not configured"):
            await client._request("GET", "/api/test")


# ============================================================================
# Project Management Tests
# ============================================================================


@pytest.mark.asyncio
class TestProjectManagement:
    """Test project management functionality."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return CorootClient(
            base_url="http://localhost:8080", username="admin", password="password"
        )

    async def test_list_projects_success(self, client):
        """Test successful project listing."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "projects": [
                    {"id": "proj1", "name": "Project 1"},
                    {"id": "proj2", "name": "Project 2"},
                ]
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            projects = await client.list_projects()

        assert len(projects) == 2
        assert projects[0]["name"] == "Project 1"

    async def test_get_project(self, client):
        """Test getting project details."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={"id": "proj1", "name": "Test Project", "settings": {}}
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            project = await client.get_project("proj1")

        assert project["id"] == "proj1"
        assert project["name"] == "Test Project"

    async def test_create_project_success(self, client):
        """Test successful project creation with JSON response."""
        mock_response = AsyncMock()
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json = Mock(
            return_value={"id": "new-proj", "name": "new-project"}
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.create_project("new-project")

        assert result["id"] == "new-proj"
        assert result["name"] == "new-project"

    async def test_create_project_non_json_response(self, client):
        """Test project creation with non-JSON response."""
        mock_response = AsyncMock()
        mock_response.headers = {"content-type": "text/plain"}
        mock_response.text = AsyncMock(return_value="Created")
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.create_project("new-project")

        assert result["name"] == "new-project"
        assert result["id"] == "new-project"

    async def test_create_project_json_parse_error(self, client):
        """Test project creation when JSON parsing fails."""
        mock_response = AsyncMock()
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json = Mock(side_effect=ValueError("Invalid JSON"))
        mock_response.text = AsyncMock(return_value="Success")
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.create_project("new-project")

        assert result["name"] == "new-project"
        assert result["id"] == "new-project"

    async def test_get_project_status(self, client):
        """Test getting project status."""
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value={"healthy": True, "stats": {}})
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            status = await client.get_project_status("proj1")

        assert status["healthy"] is True

    async def test_update_project(self, client):
        """Test updating project settings."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={"id": "project123", "settings": {"retention": "60d"}}
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.update_project("project123", {"retention": "60d"})

        assert result["settings"]["retention"] == "60d"

    async def test_delete_project_with_204(self, client):
        """Test deleting a project with 204 response."""
        mock_response = AsyncMock()
        mock_response.status_code = 204
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.delete_project("project123")

        assert result["status"] == "deleted"

    async def test_delete_project_with_empty_body(self, client):
        """Test deleting a project with 200 and empty body."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = ""
        mock_response.json = Mock(
            side_effect=ValueError("No JSON object could be decoded")
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.delete_project("project123")

        assert result["status"] == "deleted"

    async def test_list_api_keys(self, client):
        """Test listing API keys."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "keys": [
                    {"id": "key1", "name": "Ingestion Key"},
                    {"id": "key2", "name": "Backup Key"},
                ]
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.list_api_keys("project123")

        assert len(result["keys"]) == 2

    async def test_create_api_key_with_description(self, client):
        """Test creating an API key with description."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "id": "key3",
                "name": "Test Key",
                "secret": "sk_test_123",
                "description": "For testing",
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch(
            "httpx.AsyncClient.request", return_value=mock_response
        ) as mock_request:
            result = await client.create_api_key(
                "project123", "Test Key", "For testing"
            )

            # Verify the correct structure was sent
            call_args = mock_request.call_args
            assert call_args.kwargs["json"]["action"] == "generate"
            assert (
                call_args.kwargs["json"]["description"] == "Test Key"
            )  # Uses name as description
            assert result["secret"] == "sk_test_123"

    async def test_create_api_key_without_description(self, client):
        """Test creating an API key without description."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={"id": "key3", "name": "Test Key", "secret": "sk_test_123"}
        )
        mock_response.raise_for_status = AsyncMock()

        with patch(
            "httpx.AsyncClient.request", return_value=mock_response
        ) as mock_request:
            await client.create_api_key("project123", "Test Key")

            # Verify the correct structure was sent (description is always included)
            call_args = mock_request.call_args
            assert call_args.kwargs["json"]["action"] == "generate"
            assert (
                call_args.kwargs["json"]["description"] == "Test Key"
            )  # Always uses name

    async def test_delete_api_key(self, client):
        """Test deleting an API key."""
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value={"status": "success"})
        mock_response.text = ""
        mock_response.raise_for_status = AsyncMock()
        mock_response.status_code = 200

        with patch(
            "httpx.AsyncClient.request", return_value=mock_response
        ) as mock_request:
            result = await client.delete_api_key(
                "project123", "EMUHGTklu-miwJKD5IjO2Z4OSyO8Vrzn"
            )

            # Verify request (should be 2 calls: login + delete)
            assert mock_request.call_count == 2
            # Check the second call (delete API key)
            delete_call = mock_request.call_args_list[1]
            assert delete_call.args[0] == "POST"
            assert delete_call.args[1].endswith("/api/project/project123/api_keys")

            # Verify the correct structure was sent
            call_args = mock_request.call_args
            assert call_args.kwargs["json"]["action"] == "delete"
            assert call_args.kwargs["json"]["key"] == "EMUHGTklu-miwJKD5IjO2Z4OSyO8Vrzn"

            # Verify result
            assert result["status"] == "success"


# ============================================================================
# Application Monitoring Tests
# ============================================================================


@pytest.mark.asyncio
class TestApplicationMonitoring:
    """Test application monitoring functionality."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return CorootClient(
            base_url="http://localhost:8080", username="admin", password="password"
        )

    async def test_get_application_with_params(self, client):
        """Test getting application with time parameters."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "id": {"name": "test-app", "namespace": "default"},
                "status": {"value": "healthy"},
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch(
            "httpx.AsyncClient.request", return_value=mock_response
        ) as mock_request:
            app = await client.get_application(
                "proj1",
                "default/deployment/test-app",
                from_timestamp=1000,
                to_timestamp=2000,
            )

            # Check that query params were added correctly
            call_args = mock_request.call_args
            assert call_args.kwargs["params"]["from"] == "1000"
            assert call_args.kwargs["params"]["to"] == "2000"

        assert app["id"]["name"] == "test-app"

    async def test_get_application_logs(self, client):
        """Test getting application logs."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "logs": [
                    {"timestamp": 1234567890, "message": "Log entry 1"},
                    {"timestamp": 1234567891, "message": "Log entry 2"},
                ]
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            logs = await client.get_application_logs(
                "proj1",
                "default/deployment/test-app",
                from_timestamp=1000,
                to_timestamp=2000,
            )

        assert len(logs["logs"]) == 2

    async def test_get_application_traces(self, client):
        """Test getting application traces."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "traces": [
                    {"trace_id": "trace1", "spans": []},
                    {"trace_id": "trace2", "spans": []},
                ]
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            traces = await client.get_application_traces(
                "proj1",
                "default/deployment/test-app",
                from_timestamp=1000,
                to_timestamp=2000,
            )

        assert len(traces["traces"]) == 2

    async def test_get_application_rca(self, client):
        """Test getting root cause analysis for an application."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "status": "completed",
                "issues": ["High CPU usage", "Memory leak detected"],
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.get_application_rca(
                "project123", "default/deployment/myapp"
            )

        assert result["status"] == "completed"
        assert len(result["issues"]) == 2

    async def test_get_application_profiling_with_params(self, client):
        """Test getting profiling data with parameters."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={"profiles": [{"type": "cpu", "samples": 1000}]}
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.get_application_profiling(
                "project123",
                "default/deployment/myapp",
                from_timestamp=1234567890,
                to_timestamp=1234567900,
                query="cpu",
            )

        assert result["profiles"][0]["type"] == "cpu"

    async def test_get_application_profiling_no_params(self, client):
        """Test getting profiling data without parameters."""
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value={"profiles": []})
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.get_application_profiling(
                "project123", "default/deployment/myapp"
            )

        assert result["profiles"] == []

    async def test_update_application_risks_json_response(self, client):
        """Test updating application risks with JSON response."""
        mock_response = AsyncMock()
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json = Mock(return_value={"status": "updated", "risks": []})
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.update_application_risks(
                "project123", "default/deployment/myapp", {"risk1": "acknowledged"}
            )

        assert result["status"] == "updated"

    async def test_update_application_risks_non_json_response(self, client):
        """Test updating application risks with non-JSON response."""
        mock_response = AsyncMock()
        mock_response.headers = {"content-type": "text/plain"}
        mock_response.text = "OK"
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.update_application_risks(
                "project123", "default/deployment/myapp", {"risk1": "acknowledged"}
            )

        assert result["status"] == "updated"
        assert result["risks"] == {"risk1": "acknowledged"}

    async def test_update_application_risks_json_parse_error(self, client):
        """Test updating application risks when JSON parsing fails."""
        mock_response = AsyncMock()
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json = Mock(side_effect=ValueError("Invalid JSON"))
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.update_application_risks(
                "project123", "default/deployment/myapp", {"risk1": "acknowledged"}
            )

        assert result["status"] == "updated"

    async def test_get_rca_with_encoded_app_id(self, client):
        """Test RCA with app ID that needs URL encoding."""
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value={"status": "completed"})
        mock_response.raise_for_status = AsyncMock()

        with patch(
            "httpx.AsyncClient.request", return_value=mock_response
        ) as mock_request:
            await client.get_application_rca("project123", "namespace/kind/name")

            # Verify URL encoding
            call_args = mock_request.call_args
            url = call_args.args[1]
            assert "namespace%2Fkind%2Fname" in url

    async def test_profiling_with_special_app_id(self, client):
        """Test profiling with special characters in app ID."""
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value={"profiles": []})
        mock_response.raise_for_status = AsyncMock()

        with patch(
            "httpx.AsyncClient.request", return_value=mock_response
        ) as mock_request:
            await client.get_application_profiling(
                "project123", "namespace/deployment/app-name"
            )

            # Verify URL encoding
            call_args = mock_request.call_args
            url = call_args.args[1]
            assert "namespace%2Fdeployment%2Fapp-name" in url


# ============================================================================
# Overview and Infrastructure Tests
# ============================================================================


@pytest.mark.asyncio
class TestOverviewEndpoints:
    """Test overview endpoints."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return CorootClient(
            base_url="http://localhost:8080", username="admin", password="password"
        )

    async def test_get_applications_overview(self, client):
        """Test getting applications overview with query."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "applications": [{"name": "app1"}, {"name": "app2"}],
                "total": 2,
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch(
            "httpx.AsyncClient.request", return_value=mock_response
        ) as mock_request:
            overview = await client.get_applications_overview("proj1", query="test")

            # Check query param
            call_args = mock_request.call_args
            assert call_args.kwargs["params"]["query"] == "test"

        assert overview["total"] == 2

    async def test_get_applications_overview_no_query(self, client):
        """Test getting applications overview without query."""
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value={"applications": [], "total": 0})
        mock_response.raise_for_status = AsyncMock()

        with patch(
            "httpx.AsyncClient.request", return_value=mock_response
        ) as mock_request:
            overview = await client.get_applications_overview("proj1")

            # Check no query param
            call_args = mock_request.call_args
            params = call_args.kwargs.get("params", {})
            assert params.get("query") is None

        assert overview["total"] == 0

    async def test_get_nodes_overview(self, client):
        """Test getting nodes overview."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={"nodes": [{"name": "node1"}, {"name": "node2"}]}
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            overview = await client.get_nodes_overview("proj1")

        assert len(overview["nodes"]) == 2

    async def test_get_traces_overview(self, client):
        """Test getting traces overview."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={"total_traces": 100, "error_rate": 0.05}
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            overview = await client.get_traces_overview("proj1")

        assert overview["total_traces"] == 100
        assert overview["error_rate"] == 0.05

    async def test_get_deployments_overview(self, client):
        """Test getting deployments overview."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={"deployments": [{"app": "app1", "version": "v1.0"}]}
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            overview = await client.get_deployments_overview("proj1")

        assert overview["deployments"][0]["version"] == "v1.0"

    async def test_get_risks_overview(self, client):
        """Test getting risks overview."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "high_risk_apps": ["app1", "app2"],
                "total_risks": 5,
                "critical_issues": 2,
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.get_risks_overview("project123")

        assert result["total_risks"] == 5
        assert len(result["high_risk_apps"]) == 2

    async def test_get_node(self, client):
        """Test getting node details."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "id": "node1",
                "name": "worker-node-1",
                "cpu": {"usage": 0.56},
                "memory": {"usage": 0.78},
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.get_node("project123", "node1")

        assert result["id"] == "node1"
        assert result["cpu"]["usage"] == 0.56

    async def test_get_incident(self, client):
        """Test getting incident details."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "id": "incident1",
                "title": "Service degradation",
                "severity": "warning",
                "affected_apps": ["app1", "app2"],
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.get_incident("project123", "incident1")

        assert result["title"] == "Service degradation"
        assert len(result["affected_apps"]) == 2


# ============================================================================
# Integration and Configuration Tests
# ============================================================================


@pytest.mark.asyncio
class TestIntegrations:
    """Test integration functionality."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return CorootClient(
            base_url="http://localhost:8080", username="admin", password="password"
        )

    async def test_list_integrations(self, client):
        """Test listing integrations."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "integrations": [
                    {"type": "prometheus", "configured": True},
                    {"type": "slack", "configured": False},
                ]
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            integrations = await client.list_integrations("proj1")

        assert len(integrations["integrations"]) == 2

    async def test_configure_integration_success(self, client):
        """Test successful integration configuration with JSON response."""
        mock_response = AsyncMock()
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json = Mock(
            return_value={"type": "slack", "status": "configured"}
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.configure_integration(
                "proj1", "slack", {"webhook_url": "https://slack.com/webhook"}
            )

        assert result["status"] == "configured"

    async def test_configure_integration_non_json_response(self, client):
        """Test integration configuration with non-JSON response."""
        mock_response = AsyncMock()
        mock_response.headers = {"content-type": "text/plain"}
        mock_response.text = "OK"
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.configure_integration(
                "proj1", "slack", {"webhook_url": "https://slack.com/webhook"}
            )

        assert result["type"] == "slack"
        assert result["status"] == "configured"

    async def test_configure_integration_json_parse_error(self, client):
        """Test integration configuration when JSON parsing fails."""
        mock_response = AsyncMock()
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json = Mock(side_effect=ValueError("Invalid JSON"))
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.configure_integration(
                "proj1", "slack", {"webhook_url": "https://slack.com/webhook"}
            )

        assert result["type"] == "slack"
        assert result["status"] == "configured"

    async def test_test_integration(self, client):
        """Test testing an integration."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={"status": "success", "message": "Connection verified"}
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.test_integration("project123", "prometheus")

        assert result["status"] == "success"

    async def test_delete_integration_with_204(self, client):
        """Test deleting an integration with 204 response."""
        mock_response = AsyncMock()
        mock_response.status_code = 204
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.delete_integration("project123", "slack")

        assert result["status"] == "deleted"

    async def test_delete_integration_with_json(self, client):
        """Test deleting an integration with JSON response."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value={"status": "removed", "type": "slack"})
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.delete_integration("project123", "slack")

        assert result["type"] == "slack"

    async def test_get_integration(self, client):
        """Test getting specific integration config."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "type": "prometheus",
                "url": "http://prometheus:9090",
                "enabled": True,
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.get_integration("project123", "prometheus")

        assert result["type"] == "prometheus"
        assert result["enabled"] is True


@pytest.mark.asyncio
class TestHealthCheck:
    """Test health check functionality."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return CorootClient(
            base_url="http://localhost:8080", username="admin", password="password"
        )

    async def test_health_check_success(self, client):
        """Test successful health check."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = "OK"
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.health_check()

        assert result is True

    async def test_health_check_failure(self, client):
        """Test failed health check."""
        mock_response = AsyncMock()
        mock_response.status_code = 503
        mock_response.text = "Service Unavailable"
        mock_response.raise_for_status = Mock(side_effect=Exception("503 Error"))

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.health_check()
            assert result is False


@pytest.mark.asyncio
class TestConfigurationManagement:
    """Test configuration management functionality."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return CorootClient(
            base_url="http://localhost:8080", username="admin", password="password"
        )

    async def test_list_inspections(self, client):
        """Test listing inspections."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "inspections": [
                    {"type": "cpu", "enabled": True},
                    {"type": "memory", "enabled": True},
                ]
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            inspections = await client.list_inspections("proj1")

        assert len(inspections["inspections"]) == 2

    async def test_get_inspection_config(self, client):
        """Test getting inspection configuration."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={"type": "cpu", "threshold": 0.8, "enabled": True}
        )
        mock_response.raise_for_status = AsyncMock()

        with patch(
            "httpx.AsyncClient.request", return_value=mock_response
        ) as mock_request:
            config = await client.get_inspection_config(
                "proj1", "default/deployment/app", "cpu"
            )

            # Check URL encoding
            call_args = mock_request.call_args
            url = call_args.args[1]
            assert "default%2Fdeployment%2Fapp" in url

        assert config["threshold"] == 0.8

    async def test_update_inspection_config(self, client):
        """Test updating inspection configuration."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={"type": "cpu", "threshold": 0.9, "enabled": True}
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            config = await client.update_inspection_config(
                "proj1", "default/deployment/app", "cpu", {"threshold": 0.9}
            )

        assert config["threshold"] == 0.9

    async def test_get_application_categories(self, client):
        """Test getting application categories."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "categories": [
                    {"name": "frontend", "patterns": ["*/frontend/*"]},
                    {"name": "backend", "patterns": ["*/backend/*"]},
                ]
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            categories = await client.get_application_categories("proj1")

        assert len(categories["categories"]) == 2

    async def test_create_application_category(self, client):
        """Test creating a new application category."""
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value={"status": "success"})
        mock_response.text = ""
        mock_response.raise_for_status = AsyncMock()
        mock_response.status_code = 200

        with patch(
            "httpx.AsyncClient.request", return_value=mock_response
        ) as mock_request:
            # The client method takes a category dictionary
            category = {
                "name": "test-category",
                "custom_patterns": "test/* qa/*",
                "notification_settings": {
                    "incidents": {"enabled": True},
                    "deployments": {"enabled": False},
                },
            }
            result = await client.create_application_category("project123", category)

            # Verify request
            assert mock_request.call_count == 2  # login + create
            create_call = mock_request.call_args_list[1]
            assert create_call.args[0] == "POST"
            assert create_call.args[1].endswith(
                "/api/project/project123/application_categories"
            )

            # Verify the correct structure was sent
            call_args = mock_request.call_args
            json_data = call_args.kwargs["json"]
            assert json_data["name"] == "test-category"
            assert json_data["custom_patterns"] == "test/* qa/*"
            assert json_data["notification_settings"]["incidents"]["enabled"] is True
            assert json_data["notification_settings"]["deployments"]["enabled"] is False

            # Verify result
            assert result["status"] == "success"

    async def test_update_application_category(self, client):
        """Test updating an existing application category."""
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value={"status": "success"})
        mock_response.text = ""
        mock_response.raise_for_status = AsyncMock()
        mock_response.status_code = 200

        category_update = {
            "name": "test-category",
            "custom_patterns": "test/* updated/*",
            "notification_settings": {
                "incidents": {"enabled": True},
                "deployments": {"enabled": True},
            },
        }

        with patch(
            "httpx.AsyncClient.request", return_value=mock_response
        ) as mock_request:
            result = await client.update_application_category(
                "project123", "test-category", category_update
            )

            # Verify request
            assert mock_request.call_count == 2  # login + update
            update_call = mock_request.call_args_list[1]
            assert update_call.args[0] == "POST"
            assert update_call.args[1].endswith(
                "/api/project/project123/application_categories"
            )

            # Verify the correct structure was sent (NO action field for updates)
            call_args = mock_request.call_args
            json_data = call_args.kwargs["json"]
            assert "action" not in json_data
            assert json_data["id"] == "test-category"
            assert json_data["name"] == "test-category"
            assert json_data["custom_patterns"] == "test/* updated/*"
            assert json_data["notification_settings"]["incidents"]["enabled"] is True
            assert json_data["notification_settings"]["deployments"]["enabled"] is True

            # Verify result
            assert result["status"] == "success"

    async def test_delete_application_category(self, client):
        """Test deleting an application category."""
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value={"status": "success"})
        mock_response.text = ""
        mock_response.raise_for_status = AsyncMock()
        mock_response.status_code = 200

        with patch(
            "httpx.AsyncClient.request", return_value=mock_response
        ) as mock_request:
            result = await client.delete_application_category(
                "project123", "test-category"
            )

            # Verify request
            assert mock_request.call_count == 2  # login + delete
            delete_call = mock_request.call_args_list[1]
            assert delete_call.args[0] == "POST"
            assert delete_call.args[1].endswith(
                "/api/project/project123/application_categories"
            )

            # Verify the correct structure was sent
            call_args = mock_request.call_args
            json_data = call_args.kwargs["json"]
            assert json_data["action"] == "delete"
            assert json_data["id"] == "test-category"
            assert json_data["name"] == "test-category"  # Required for validation
            assert json_data["custom_patterns"] == ""  # Required for validation

            # Verify result
            assert result["status"] == "success"

    async def test_get_custom_applications(self, client):
        """Test getting custom applications."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "apps": [
                    {"name": "custom-app", "instances": ["instance1", "instance2"]}
                ]
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            apps = await client.get_custom_applications("proj1")

        assert len(apps["apps"]) == 1

    async def test_update_custom_applications(self, client):
        """Test updating custom applications."""
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value={"status": "updated"})
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.update_custom_applications(
                "proj1", {"custom-app": {"instances": ["instance1"]}}
            )

        assert result["status"] == "updated"


# ============================================================================
# Dashboard Management Tests
# ============================================================================


@pytest.mark.asyncio
class TestDashboardManagement:
    """Test dashboard management functionality."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return CorootClient(
            base_url="http://localhost:8080", username="admin", password="password"
        )

    async def test_list_dashboards(self, client):
        """Test listing dashboards."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "dashboards": [
                    {"id": "dash1", "name": "Overview"},
                    {"id": "dash2", "name": "Performance"},
                ]
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.list_dashboards("project123")

        assert result["dashboards"][0]["name"] == "Overview"

    async def test_create_dashboard(self, client):
        """Test creating a dashboard."""
        dashboard = {"name": "Custom Dashboard", "panels": []}
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value={"id": "dash3", **dashboard})
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.create_dashboard("project123", dashboard)

        assert result["id"] == "dash3"
        assert result["name"] == "Custom Dashboard"

    async def test_get_dashboard(self, client):
        """Test getting a specific dashboard."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "id": "dash1",
                "name": "Overview",
                "panels": [{"type": "graph"}],
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.get_dashboard("project123", "dash1")

        assert result["panels"][0]["type"] == "graph"

    async def test_update_dashboard(self, client):
        """Test updating a dashboard."""
        dashboard = {"name": "Updated Dashboard"}
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value={"id": "dash1", **dashboard})
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.update_dashboard("project123", "dash1", dashboard)

        assert result["name"] == "Updated Dashboard"

    async def test_get_panel_data(self, client):
        """Test getting panel data."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "metrics": [{"timestamp": 1234567890, "value": 42.5}],
                "title": "CPU Usage",
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch(
            "httpx.AsyncClient.request", return_value=mock_response
        ) as mock_request:
            result = await client.get_panel_data(
                "project123", "dashboard1", "panel1", {"from": "-1h", "to": "now"}
            )

            # Check that params were properly constructed
            call_args = mock_request.call_args
            assert call_args.kwargs["params"]["dashboard"] == "dashboard1"
            assert call_args.kwargs["params"]["panel"] == "panel1"
            assert call_args.kwargs["params"]["from"] == "-1h"
            assert result["metrics"][0]["value"] == 42.5


# ============================================================================
# User and Role Management Tests
# ============================================================================


@pytest.mark.asyncio
class TestUserRoleManagement:
    """Test user and role management functionality."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return CorootClient(
            base_url="http://localhost:8080", username="admin", password="password"
        )

    async def test_update_current_user(self, client):
        """Test updating current user."""
        user_data = {"name": "Jane Doe"}
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={"id": "user1", "email": "jane@example.com", **user_data}
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.update_current_user(user_data)

        assert result["name"] == "Jane Doe"

    async def test_list_users(self, client):
        """Test listing users."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "users": [
                    {"id": "user1", "email": "admin@example.com", "role": "Admin"},
                    {"id": "user2", "email": "user@example.com", "role": "Editor"},
                ]
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.list_users()

        assert result["users"][0]["role"] == "Admin"

    async def test_create_user(self, client):
        """Test creating a user."""
        user_data = {"email": "new@example.com", "name": "New User", "role": "Viewer"}
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value={"id": "user3", **user_data})
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.create_user(user_data)

        assert result["email"] == "new@example.com"
        assert result["role"] == "Viewer"

    async def test_get_roles(self, client):
        """Test getting available roles."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "roles": [
                    {"name": "Admin", "permissions": ["all"]},
                    {"name": "Editor", "permissions": ["read", "write"]},
                    {"name": "Viewer", "permissions": ["read"]},
                ]
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.get_roles()

        assert len(result["roles"]) == 3
        assert result["roles"][0]["name"] == "Admin"

    async def test_create_or_update_role(self, client):
        """Test creating or updating a role."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "name": "CustomRole",
                "permissions": ["read", "write"],
                "description": "Custom role for testing",
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.create_or_update_role(
                {
                    "name": "CustomRole",
                    "permissions": ["read", "write"],
                    "description": "Custom role for testing",
                }
            )

        assert result["name"] == "CustomRole"
        assert "write" in result["permissions"]


# ============================================================================
# Advanced Configuration Tests
# ============================================================================


@pytest.mark.asyncio
class TestAdvancedConfiguration:
    """Test advanced configuration functionality."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return CorootClient(
            base_url="http://localhost:8080", username="admin", password="password"
        )

    async def test_get_custom_cloud_pricing(self, client):
        """Test getting custom cloud pricing."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "cpu_hourly_cost": 0.05,
                "memory_gb_hourly_cost": 0.01,
                "storage_gb_monthly_cost": 0.10,
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.get_custom_cloud_pricing("project123")

        assert result["cpu_hourly_cost"] == 0.05
        assert result["memory_gb_hourly_cost"] == 0.01

    async def test_update_custom_cloud_pricing(self, client):
        """Test updating custom cloud pricing."""
        pricing = {"cpu_hourly_cost": 0.06}
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value=pricing)
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.update_custom_cloud_pricing("project123", pricing)

        assert result["cpu_hourly_cost"] == 0.06

    async def test_delete_custom_cloud_pricing_with_204(self, client):
        """Test deleting custom cloud pricing with 204 response."""
        mock_response = AsyncMock()
        mock_response.status_code = 204
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.delete_custom_cloud_pricing("project123")

        assert result["status"] == "deleted"

    async def test_get_sso_config(self, client):
        """Test getting SSO configuration."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "enabled": True,
                "provider": "okta",
                "roles": ["Admin", "Editor", "Viewer"],
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.get_sso_config()

        assert result["enabled"] is True
        assert result["provider"] == "okta"

    async def test_update_sso_config(self, client):
        """Test updating SSO configuration."""
        config = {"enabled": True, "provider": "saml"}
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value=config)
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.update_sso_config(config)

        assert result["provider"] == "saml"

    async def test_get_ai_config(self, client):
        """Test getting AI configuration."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={"provider": "openai", "model": "gpt-4", "enabled": True}
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.get_ai_config()

        assert result["provider"] == "openai"
        assert result["model"] == "gpt-4"

    async def test_update_ai_config(self, client):
        """Test updating AI configuration."""
        config = {"provider": "anthropic", "model": "claude-3"}
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value=config)
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.update_ai_config(config)

        assert result["provider"] == "anthropic"

    async def test_get_db_instrumentation(self, client):
        """Test getting database instrumentation config."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "enabled": True,
                "sample_rate": 0.1,
                "slow_query_threshold_ms": 100,
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch(
            "httpx.AsyncClient.request", return_value=mock_response
        ) as mock_request:
            result = await client.get_db_instrumentation(
                "project123", "namespace/deployment/app", "mysql"
            )

            # Check URL encoding
            call_args = mock_request.call_args
            url = call_args.args[1]
            assert "namespace%2Fdeployment%2Fapp" in url
            assert result["enabled"] is True

    async def test_update_db_instrumentation(self, client):
        """Test updating database instrumentation config."""
        config = {"enabled": True, "sample_rate": 0.2}
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value=config)
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.update_db_instrumentation(
                "project123", "namespace/deployment/app", "postgres", config
            )

        assert result["sample_rate"] == 0.2

    async def test_configure_profiling(self, client):
        """Test configuring profiling."""
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value={"enabled": True, "sample_rate": 0.1})
        mock_response.raise_for_status = AsyncMock()

        with patch(
            "httpx.AsyncClient.request", return_value=mock_response
        ) as mock_request:
            result = await client.configure_profiling(
                "project123",
                "namespace/deployment/app",
                {"enabled": True, "sample_rate": 0.1},
            )

            # Check URL encoding
            call_args = mock_request.call_args
            url = call_args.args[1]
            assert "namespace%2Fdeployment%2Fapp" in url
            assert result["sample_rate"] == 0.1

    async def test_configure_tracing(self, client):
        """Test configuring tracing."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "enabled": True,
                "sample_rate": 0.05,
                "excluded_paths": ["/health"],
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.configure_tracing(
                "project123",
                "app1",
                {"enabled": True, "sample_rate": 0.05, "excluded_paths": ["/health"]},
            )

        assert result["sample_rate"] == 0.05
        assert "/health" in result["excluded_paths"]

    async def test_configure_logs(self, client):
        """Test configuring log collection."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "enabled": True,
                "level": "warn",
                "excluded_patterns": [".*debug.*"],
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.configure_logs(
                "project123",
                "app1",
                {"enabled": True, "level": "warn", "excluded_patterns": [".*debug.*"]},
            )

        assert result["level"] == "warn"
        assert ".*debug.*" in result["excluded_patterns"]


# ============================================================================
# Error Handling Tests
# ============================================================================


@pytest.mark.asyncio
class TestErrorHandling:
    """Test error handling across different scenarios."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return CorootClient(
            base_url="http://localhost:8080", username="admin", password="password"
        )

    async def test_api_error(self, client):
        """Test API error handling."""
        mock_response = AsyncMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_response.raise_for_status = Mock(side_effect=Exception("400 Error"))

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            with pytest.raises(CorootError, match="API request failed: 400"):
                await client.list_projects()

    async def test_network_error(self, client):
        """Test network error handling."""
        with patch(
            "httpx.AsyncClient.request",
            side_effect=ConnectionError("Network unreachable"),
        ):
            with pytest.raises(
                CorootError, match="API request failed: Network unreachable"
            ):
                await client.list_projects()
