"""Coroot API client implementation.

This module provides an async HTTP client for interacting with the Coroot
observability platform API. It handles authentication, session management,
and all API endpoints for monitoring applications, infrastructure, and
performance metrics.

The client supports multiple authentication methods:
- Username/password with automatic login
- Session cookie for direct authentication
- API key for data ingestion endpoints

Features:
- Automatic session management and re-authentication
- Comprehensive error handling with custom exceptions
- Full coverage of Coroot API endpoints
- Type-safe request/response handling

Example:
    ```python
    from mcp_coroot.client import CorootClient

    # Create client with auto-login
    client = CorootClient(
        base_url="http://localhost:8080",
        username="admin",
        password="password"
    )

    # List all projects
    projects = await client.list_projects()

    # Get application details
    app = await client.get_application("project-1", "frontend")
    ```
"""

import os
from typing import Any
from urllib.parse import quote, urljoin

import httpx
from dotenv import load_dotenv

load_dotenv()


class CorootError(Exception):
    """Base exception for Coroot API errors."""

    pass


class CorootClient:
    """Async client for Coroot API."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        session_cookie: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ):
        """Initialize the client with authentication.

        Args:
            base_url: Coroot API base URL. If not provided, will attempt
                     to load from COROOT_BASE_URL environment variable.
            api_key: Coroot API key for data ingestion endpoints.
                    If not provided, will attempt to load from
                    COROOT_API_KEY environment variable.
            session_cookie: Session cookie for management API endpoints.
                          If not provided, will attempt to load from
                          COROOT_SESSION_COOKIE environment variable.
            username: Username for automatic login. If not provided,
                     will attempt to load from COROOT_USERNAME.
            password: Password for automatic login. If not provided,
                     will attempt to load from COROOT_PASSWORD.

        Raises:
            ValueError: If no base URL is provided or found in environment.
        """
        self.base_url = base_url or os.getenv(
            "COROOT_BASE_URL", "http://localhost:8080"
        )
        if not self.base_url:
            raise ValueError(
                "Base URL must be provided or set in "
                "COROOT_BASE_URL environment variable"
            )

        # Ensure base URL ends without trailing slash
        self.base_url = self.base_url.rstrip("/")

        self.api_key = api_key or os.getenv("COROOT_API_KEY")
        self.session_cookie = session_cookie or os.getenv("COROOT_SESSION_COOKIE")
        self.username = username or os.getenv("COROOT_USERNAME")
        self.password = password or os.getenv("COROOT_PASSWORD")

        # Will be set after automatic login
        self._auto_login_attempted = False

        self.headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _get_auth_headers(self, use_api_key: bool = False) -> dict[str, str]:
        """Get authentication headers based on endpoint type.

        Args:
            use_api_key: If True, use API key authentication.
                        Otherwise, use session cookie.

        Returns:
            Dictionary of authentication headers.
        """
        headers = self.headers.copy()

        if use_api_key and self.api_key:
            headers["X-API-Key"] = self.api_key

        return headers

    def _get_cookies(self) -> dict[str, str]:
        """Get cookies for session-based authentication.

        Returns:
            Dictionary of cookies.
        """
        cookies = {}
        if self.session_cookie:
            cookies["coroot_session"] = self.session_cookie
        return cookies

    async def _ensure_authenticated(self) -> None:
        """Ensure we have valid authentication, attempting login if needed."""
        # If we have a session cookie, assume it's valid
        if self.session_cookie:
            return

        # If we have username/password and haven't tried login yet
        if self.username and self.password and not self._auto_login_attempted:
            self._auto_login_attempted = True
            try:
                # Attempt automatic login
                self.session_cookie = await self.login(self.username, self.password)
            except Exception:
                # Login failed, but we'll let the actual request fail with auth error
                pass

    async def _request(
        self,
        method: str,
        path: str,
        use_api_key: bool = False,
        skip_auto_login: bool = False,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make an authenticated request to the Coroot API.

        Args:
            method: HTTP method.
            path: API path (relative to base URL).
            use_api_key: If True, use API key authentication.
            skip_auto_login: If True, skip automatic login attempt.
            **kwargs: Additional arguments for httpx request.

        Returns:
            HTTP response.

        Raises:
            CorootError: If the API request fails.
        """
        if not self.base_url:
            raise CorootError("Base URL not configured")

        # Attempt automatic login if needed (skip for login endpoint itself)
        if not skip_auto_login and not use_api_key:
            await self._ensure_authenticated()

        url = urljoin(self.base_url, path)
        headers = kwargs.pop("headers", {})
        headers.update(self._get_auth_headers(use_api_key))

        cookies = kwargs.pop("cookies", {})
        if not use_api_key:
            cookies.update(self._get_cookies())

        async with httpx.AsyncClient() as client:
            try:
                response = await client.request(
                    method,
                    url,
                    headers=headers,
                    cookies=cookies,
                    **kwargs,
                )
                response.raise_for_status()
                return response
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    auth_method = "API key" if use_api_key else "session cookie"
                    raise CorootError(
                        f"Authentication failed: Invalid {auth_method}. "
                        f"Please check your credentials."
                    ) from e
                raise CorootError(
                    f"API request failed: {e.response.status_code} - {e.response.text}"
                ) from e
            except Exception as e:
                raise CorootError(f"API request failed: {str(e)}") from e

    def _parse_json_response(self, response: httpx.Response) -> dict[str, Any]:
        """Parse JSON response, handling empty bodies gracefully.

        Args:
            response: HTTP response object.

        Returns:
            Parsed JSON data or default response for empty bodies.
        """
        # Handle 204 No Content
        if response.status_code == 204:
            return {"status": "success"}

        # Try to parse JSON
        try:
            content = response.text.strip()
            if not content:
                # Empty response body with 2xx status
                return {"status": "success"}
            data: dict[str, Any] = response.json()
            return data
        except Exception:
            # If parsing fails but status is 2xx, assume success
            if 200 <= response.status_code < 300:
                return {"status": "success"}
            raise

    # Authentication & User Management

    async def login(self, email: str, password: str) -> str:
        """Login to Coroot and get session cookie.

        Args:
            email: User email.
            password: User password.

        Returns:
            Session cookie value.

        Raises:
            CorootError: If login fails.
        """
        data = {
            "email": email,
            "password": password,
            "action": "login",
        }

        response = await self._request(
            "POST", "/api/login", skip_auto_login=True, json=data
        )

        # Extract session cookie from response
        cookie = response.cookies.get("coroot_session")
        if not cookie:
            raise CorootError("Login successful but no session cookie received")

        return str(cookie)

    async def logout(self) -> None:
        """Logout and clear session."""
        await self._request("POST", "/api/logout")

    async def get_current_user(self) -> dict[str, Any]:
        """Get current authenticated user information.

        Returns:
            User information dictionary.
        """
        response = await self._request("GET", "/api/user")
        data: dict[str, Any] = response.json()
        return data

    # Project Management

    async def list_projects(self) -> list[dict[str, Any]]:
        """List all accessible projects.

        Returns:
            List of project dictionaries.
        """
        # Get user info which includes projects list
        user_response = await self._request("GET", "/api/user")
        user_data: dict[str, Any] = user_response.json()
        projects: list[dict[str, Any]] = user_data.get("projects", [])
        return projects

    async def get_project(self, project_id: str) -> dict[str, Any]:
        """Get project details.

        Args:
            project_id: Project ID.

        Returns:
            Project configuration dictionary.
        """
        response = await self._request("GET", f"/api/project/{project_id}")
        data: dict[str, Any] = response.json()
        return data

    async def create_project(self, name: str) -> dict[str, Any]:
        """Create a new project.

        Args:
            name: Project name (must match ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$).

        Returns:
            Created project information.
        """
        data = {"name": name}
        response = await self._request("POST", "/api/project/", json=data)

        # Handle different response types
        try:
            if response.headers.get("content-type", "").startswith("application/json"):
                result: dict[str, Any] = response.json()
                return result
            else:
                # If not JSON, return a success indicator with the name
                return {"id": name, "name": name}
        except Exception:
            # If parsing fails, return minimal success response
            return {"id": name, "name": name}

    async def get_project_status(self, project_id: str) -> dict[str, Any]:
        """Get project status including Prometheus and agent status.

        Args:
            project_id: Project ID.

        Returns:
            Project status dictionary.
        """
        response = await self._request("GET", f"/api/project/{project_id}/status")
        data: dict[str, Any] = response.json()
        return data

    # Application Monitoring

    async def get_application(
        self,
        project_id: str,
        app_id: str,
        from_timestamp: int | None = None,
        to_timestamp: int | None = None,
    ) -> dict[str, Any]:
        """Get application details and metrics.

        Args:
            project_id: Project ID.
            app_id: Application ID (format: namespace/kind/name).
            from_timestamp: Start timestamp for metrics.
            to_timestamp: End timestamp for metrics.

        Returns:
            Application metrics and information.
        """
        params = {}
        if from_timestamp:
            params["from"] = str(from_timestamp)
        if to_timestamp:
            params["to"] = str(to_timestamp)

        response = await self._request(
            "GET",
            f"/api/project/{project_id}/app/{app_id}",
            params=params,
        )
        data: dict[str, Any] = response.json()
        return data

    async def get_application_logs(
        self,
        project_id: str,
        app_id: str,
        from_timestamp: int | None = None,
        to_timestamp: int | None = None,
        query: str | None = None,
        severity: str | None = None,
    ) -> dict[str, Any]:
        """Get application logs.

        Args:
            project_id: Project ID.
            app_id: Application ID.
            from_timestamp: Start timestamp.
            to_timestamp: End timestamp.
            query: Log search query.
            severity: Filter by severity level.

        Returns:
            Application logs and patterns.
        """
        params = {}
        if from_timestamp:
            params["from"] = str(from_timestamp)
        if to_timestamp:
            params["to"] = str(to_timestamp)
        if query:
            params["query"] = query
        if severity:
            params["severity"] = severity

        response = await self._request(
            "GET",
            f"/api/project/{project_id}/app/{app_id}/logs",
            params=params,
        )
        data: dict[str, Any] = response.json()
        return data

    async def get_application_traces(
        self,
        project_id: str,
        app_id: str,
        from_timestamp: int | None = None,
        to_timestamp: int | None = None,
        trace_id: str | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Get application distributed traces.

        Args:
            project_id: Project ID.
            app_id: Application ID.
            from_timestamp: Start timestamp.
            to_timestamp: End timestamp.
            trace_id: Specific trace ID.
            query: Search query.

        Returns:
            Distributed traces data.
        """
        params = {}
        if from_timestamp:
            params["from"] = str(from_timestamp)
        if to_timestamp:
            params["to"] = str(to_timestamp)
        if trace_id:
            params["trace_id"] = trace_id
        if query:
            params["query"] = query

        response = await self._request(
            "GET",
            f"/api/project/{project_id}/app/{app_id}/tracing",
            params=params,
        )
        data: dict[str, Any] = response.json()
        return data

    # Overview endpoints

    async def get_applications_overview(
        self,
        project_id: str,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Get applications overview.

        Args:
            project_id: Project ID.
            query: Search/filter query.

        Returns:
            Applications overview data.
        """
        params = {}
        if query:
            params["query"] = query

        response = await self._request(
            "GET",
            f"/api/project/{project_id}/overview/applications",
            params=params,
        )
        data: dict[str, Any] = response.json()
        return data

    async def get_nodes_overview(
        self,
        project_id: str,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Get infrastructure nodes overview.

        Args:
            project_id: Project ID.
            query: Search/filter query.

        Returns:
            Nodes overview data.
        """
        params = {}
        if query:
            params["query"] = query

        response = await self._request(
            "GET",
            f"/api/project/{project_id}/overview/nodes",
            params=params,
        )
        data: dict[str, Any] = response.json()
        return data

    async def get_traces_overview(
        self,
        project_id: str,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Get distributed tracing overview.

        Args:
            project_id: Project ID.
            query: Search/filter query.

        Returns:
            Traces overview data.
        """
        params = {}
        if query:
            params["query"] = query

        response = await self._request(
            "GET",
            f"/api/project/{project_id}/overview/traces",
            params=params,
        )
        data: dict[str, Any] = response.json()
        return data

    async def get_deployments_overview(
        self,
        project_id: str,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Get deployments overview.

        Args:
            project_id: Project ID.
            query: Search/filter query.

        Returns:
            Deployments overview data.
        """
        params = {}
        if query:
            params["query"] = query

        response = await self._request(
            "GET",
            f"/api/project/{project_id}/overview/deployments",
            params=params,
        )
        data: dict[str, Any] = response.json()
        return data

    async def get_risks_overview(
        self,
        project_id: str,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Get risk assessment overview.

        Args:
            project_id: Project ID.
            query: Search/filter query.

        Returns:
            Risk assessment overview data.
        """
        params = {}
        if query:
            params["query"] = query

        response = await self._request(
            "GET",
            f"/api/project/{project_id}/overview/risks",
            params=params,
        )
        data: dict[str, Any] = response.json()
        return data

    # Integrations

    async def list_integrations(self, project_id: str) -> dict[str, Any]:
        """List all configured integrations for a project.

        Args:
            project_id: Project ID.

        Returns:
            Dictionary of integration configurations.
        """
        response = await self._request("GET", f"/api/project/{project_id}/integrations")
        data: dict[str, Any] = response.json()
        return data

    async def configure_integration(
        self,
        project_id: str,
        integration_type: str,
        config: dict[str, Any],
    ) -> dict[str, Any]:
        """Configure an integration.

        Args:
            project_id: Project ID.
            integration_type: Type of integration (prometheus, slack, etc.).
            config: Integration-specific configuration.

        Returns:
            Updated integration configuration.
        """
        response = await self._request(
            "PUT",
            f"/api/project/{project_id}/integrations/{integration_type}",
            json=config,
        )

        # Handle different response types
        try:
            if response.headers.get("content-type", "").startswith("application/json"):
                data: dict[str, Any] = response.json()
                return data
            else:
                # If not JSON, return success with the provided config
                return {
                    "type": integration_type,
                    "config": config,
                    "status": "configured",
                }
        except Exception:
            # If parsing fails, return minimal success response
            return {"type": integration_type, "status": "configured"}

    # Configuration Management

    async def list_inspections(self, project_id: str) -> dict[str, Any]:
        """List all available inspections for a project.

        Args:
            project_id: Project ID.

        Returns:
            Dictionary of inspection configurations.
        """
        response = await self._request("GET", f"/api/project/{project_id}/inspections")
        data: dict[str, Any] = response.json()
        return data

    async def get_inspection_config(
        self, project_id: str, app_id: str, inspection_type: str
    ) -> dict[str, Any]:
        """Get inspection configuration for an application.

        Args:
            project_id: Project ID.
            app_id: Application ID.
            inspection_type: Type of inspection (cpu, memory, slo, etc).

        Returns:
            Inspection configuration.
        """
        # URL encode the app_id since it contains slashes
        from urllib.parse import quote

        encoded_app_id = quote(app_id, safe="")

        response = await self._request(
            "GET",
            f"/api/project/{project_id}/app/{encoded_app_id}/inspection/{inspection_type}/config",
        )
        data: dict[str, Any] = response.json()
        return data

    async def update_inspection_config(
        self, project_id: str, app_id: str, inspection_type: str, config: dict[str, Any]
    ) -> dict[str, Any]:
        """Update inspection configuration for an application.

        Args:
            project_id: Project ID.
            app_id: Application ID.
            inspection_type: Type of inspection (cpu, memory, slo, etc).
            config: New configuration.

        Returns:
            Updated configuration.
        """
        # URL encode the app_id since it contains slashes
        from urllib.parse import quote

        encoded_app_id = quote(app_id, safe="")

        response = await self._request(
            "POST",
            f"/api/project/{project_id}/app/{encoded_app_id}/inspection/{inspection_type}/config",
            json=config,
        )
        return self._parse_json_response(response)

    async def get_application_categories(self, project_id: str) -> dict[str, Any]:
        """Get application categories configuration.

        Args:
            project_id: Project ID.

        Returns:
            Application categories.
        """
        response = await self._request(
            "GET", f"/api/project/{project_id}/application_categories"
        )
        data: dict[str, Any] = response.json()
        return data

    async def update_application_categories(
        self, project_id: str, categories: dict[str, Any]
    ) -> dict[str, Any]:
        """Update application categories configuration.

        Args:
            project_id: Project ID.
            categories: New categories configuration.

        Returns:
            Updated categories.
        """
        response = await self._request(
            "POST", f"/api/project/{project_id}/application_categories", json=categories
        )
        data: dict[str, Any] = response.json()
        return data

    async def get_custom_applications(self, project_id: str) -> dict[str, Any]:
        """Get custom applications configuration.

        Args:
            project_id: Project ID.

        Returns:
            Custom applications.
        """
        response = await self._request(
            "GET", f"/api/project/{project_id}/custom_applications"
        )
        data: dict[str, Any] = response.json()
        return data

    async def update_custom_applications(
        self, project_id: str, applications: dict[str, Any]
    ) -> dict[str, Any]:
        """Update custom applications configuration.

        Args:
            project_id: Project ID.
            applications: New custom applications configuration.

        Returns:
            Updated applications.
        """
        response = await self._request(
            "POST", f"/api/project/{project_id}/custom_applications", json=applications
        )
        data: dict[str, Any] = response.json()
        return data

    # Advanced Application Features

    async def get_application_rca(self, project_id: str, app_id: str) -> dict[str, Any]:
        """Get root cause analysis for an application.

        Args:
            project_id: Project ID.
            app_id: Application ID (format: namespace/kind/name).

        Returns:
            Root cause analysis results.
        """
        # URL encode the app_id since it contains slashes
        from urllib.parse import quote

        encoded_app_id = quote(app_id, safe="")

        response = await self._request(
            "GET", f"/api/project/{project_id}/app/{encoded_app_id}/rca"
        )
        data: dict[str, Any] = response.json()
        return data

    async def get_application_profiling(
        self,
        project_id: str,
        app_id: str,
        from_timestamp: int | None = None,
        to_timestamp: int | None = None,
        query: str | None = None,
    ) -> dict[str, Any]:
        """Get profiling data for an application.

        Args:
            project_id: Project ID.
            app_id: Application ID (format: namespace/kind/name).
            from_timestamp: Start timestamp.
            to_timestamp: End timestamp.
            query: Search query.

        Returns:
            Profiling data and flame graphs.
        """
        # URL encode the app_id since it contains slashes
        from urllib.parse import quote

        encoded_app_id = quote(app_id, safe="")

        params = {}
        if from_timestamp:
            params["from"] = str(from_timestamp)
        if to_timestamp:
            params["to"] = str(to_timestamp)
        if query:
            params["query"] = query

        response = await self._request(
            "GET",
            f"/api/project/{project_id}/app/{encoded_app_id}/profiling",
            params=params,
        )
        data: dict[str, Any] = response.json()
        return data

    async def update_application_risks(
        self, project_id: str, app_id: str, risks: dict[str, Any]
    ) -> dict[str, Any]:
        """Update application risk assessment.

        Args:
            project_id: Project ID.
            app_id: Application ID (format: namespace/kind/name).
            risks: Risk assessment updates.

        Returns:
            Updated risk configuration.
        """
        # URL encode the app_id since it contains slashes
        from urllib.parse import quote

        encoded_app_id = quote(app_id, safe="")

        response = await self._request(
            "POST",
            f"/api/project/{project_id}/app/{encoded_app_id}/risks",
            json=risks,
        )

        # Handle different response types
        try:
            if response.headers.get("content-type", "").startswith("application/json"):
                data: dict[str, Any] = response.json()
                return data
            else:
                # If not JSON, return success with the provided risks
                return {
                    "app_id": app_id,
                    "risks": risks,
                    "status": "updated",
                }
        except Exception:
            # If parsing fails, return minimal success response
            return {"app_id": app_id, "status": "updated"}

    # Node & Incident Management

    async def get_node(self, project_id: str, node_id: str) -> dict[str, Any]:
        """Get detailed information about a specific node.

        Args:
            project_id: Project ID.
            node_id: Node ID.

        Returns:
            Node details including metrics and containers.
        """
        response = await self._request(
            "GET", f"/api/project/{project_id}/node/{node_id}"
        )
        data: dict[str, Any] = response.json()
        return data

    async def get_incident(self, project_id: str, incident_id: str) -> dict[str, Any]:
        """Get detailed information about a specific incident.

        Args:
            project_id: Project ID.
            incident_id: Incident ID.

        Returns:
            Incident details including timeline and impact.
        """
        response = await self._request(
            "GET", f"/api/project/{project_id}/incident/{incident_id}"
        )
        data: dict[str, Any] = response.json()
        return data

    # Dashboard Management

    async def list_dashboards(self, project_id: str) -> dict[str, Any]:
        """List all custom dashboards for a project.

        Args:
            project_id: Project ID.

        Returns:
            List of dashboards.
        """
        response = await self._request("GET", f"/api/project/{project_id}/dashboards")
        return self._parse_json_response(response)

    async def create_dashboard(
        self, project_id: str, dashboard: dict[str, Any]
    ) -> dict[str, Any]:
        """Create a new custom dashboard.

        Args:
            project_id: Project ID.
            dashboard: Dashboard configuration.

        Returns:
            Created dashboard.
        """
        response = await self._request(
            "POST",
            f"/api/project/{project_id}/dashboards",
            json=dashboard,
        )
        return self._parse_json_response(response)

    async def get_dashboard(self, project_id: str, dashboard_id: str) -> dict[str, Any]:
        """Get a specific dashboard.

        Args:
            project_id: Project ID.
            dashboard_id: Dashboard ID.

        Returns:
            Dashboard configuration.
        """
        response = await self._request(
            "GET", f"/api/project/{project_id}/dashboards/{dashboard_id}"
        )
        data: dict[str, Any] = response.json()
        return data

    async def update_dashboard(
        self, project_id: str, dashboard_id: str, dashboard: dict[str, Any]
    ) -> dict[str, Any]:
        """Update an existing dashboard.

        Args:
            project_id: Project ID.
            dashboard_id: Dashboard ID.
            dashboard: Updated dashboard configuration.

        Returns:
            Updated dashboard.
        """
        response = await self._request(
            "POST",
            f"/api/project/{project_id}/dashboards/{dashboard_id}",
            json=dashboard,
        )
        data: dict[str, Any] = response.json()
        return data

    # Integration Management

    async def test_integration(
        self, project_id: str, integration_type: str
    ) -> dict[str, Any]:
        """Test an integration configuration.

        Args:
            project_id: Project ID.
            integration_type: Type of integration to test.

        Returns:
            Test results.
        """
        # First get the current config
        integrations = await self.list_integrations(project_id)
        current_config = integrations.get(integration_type, {})

        # Send POST with current config to test it
        response = await self._request(
            "POST",
            f"/api/project/{project_id}/integrations/{integration_type}",
            json=current_config,
        )
        data: dict[str, Any] = response.json()
        return data

    async def delete_integration(
        self, project_id: str, integration_type: str
    ) -> dict[str, Any]:
        """Delete an integration configuration.

        Args:
            project_id: Project ID.
            integration_type: Type of integration to delete.

        Returns:
            Deletion status.
        """
        response = await self._request(
            "DELETE", f"/api/project/{project_id}/integrations/{integration_type}"
        )

        # Handle empty response (204 or empty body)
        if response.status_code == 204:
            return {"status": "deleted"}

        # Try to parse JSON response
        try:
            content = response.text.strip()
            if not content:
                # Empty response body with 200 status
                return {"status": "deleted"}
            data: dict[str, Any] = response.json()
            return data
        except Exception:
            # If parsing fails, assume success if status code is 2xx
            if 200 <= response.status_code < 300:
                return {"status": "deleted"}
            raise

    # Advanced Project Management

    async def update_project(
        self, project_id: str, settings: dict[str, Any]
    ) -> dict[str, Any]:
        """Update project settings.

        Args:
            project_id: Project ID.
            settings: Updated project settings.
                     Only 'name' field is supported.
                     Name must match pattern: ^[-_0-9a-z]{3,}$

        Returns:
            Updated project.
        """
        # Validate project name if provided
        if "name" in settings:
            import re

            if not re.match(r"^[-_0-9a-z]{3,}$", settings["name"]):
                raise ValueError(
                    "Project name must contain only lowercase letters, "
                    "numbers, hyphens, and underscores (min 3 chars)"
                )

        response = await self._request(
            "POST",
            f"/api/project/{project_id}",
            json=settings,
        )
        data: dict[str, Any] = response.json()
        return data

    async def delete_project(self, project_id: str) -> dict[str, Any]:
        """Delete a project.

        Args:
            project_id: Project ID.

        Returns:
            Deletion status.
        """
        response = await self._request("DELETE", f"/api/project/{project_id}")

        # Handle empty response (204 or empty body)
        if response.status_code == 204:
            return {"status": "deleted"}

        # Try to parse JSON response
        try:
            content = response.text.strip()
            if not content:
                # Empty response body with 200 status
                return {"status": "deleted"}
            data: dict[str, Any] = response.json()
            return data
        except Exception:
            # If parsing fails, assume success if status code is 2xx
            if 200 <= response.status_code < 300:
                return {"status": "deleted"}
            raise

    async def list_api_keys(self, project_id: str) -> dict[str, Any]:
        """List API keys for a project.

        Args:
            project_id: Project ID.

        Returns:
            List of API keys.
        """
        response = await self._request("GET", f"/api/project/{project_id}/api_keys")
        data: dict[str, Any] = response.json()
        return data

    async def create_api_key(
        self, project_id: str, name: str, description: str | None = None
    ) -> dict[str, Any]:
        """Create a new API key.

        Args:
            project_id: Project ID.
            name: API key name (used as description in Coroot).
            description: Optional description (not used by Coroot).

        Returns:
            Created API key with secret.
        """
        # Coroot expects 'action' and 'description' fields
        data = {
            "action": "generate",
            "description": name,  # Coroot uses 'description' not 'name'
        }

        response = await self._request(
            "POST",
            f"/api/project/{project_id}/api_keys",
            json=data,
        )
        return self._parse_json_response(response)

    async def delete_api_key(self, project_id: str, key: str) -> dict[str, Any]:
        """Delete an API key.

        Args:
            project_id: Project ID.
            key: The API key to delete.

        Returns:
            Success status.
        """
        data = {"action": "delete", "key": key}
        response = await self._request(
            "POST",
            f"/api/project/{project_id}/api_keys",
            json=data,
        )
        return self._parse_json_response(response)

    async def delete_dashboard(
        self, project_id: str, dashboard_id: str
    ) -> dict[str, Any]:
        """Delete a dashboard.

        Args:
            project_id: Project ID.
            dashboard_id: Dashboard ID.

        Returns:
            Deletion status.
        """
        request_data = {"action": "delete"}

        response = await self._request(
            "POST",
            f"/api/project/{project_id}/dashboards/{dashboard_id}",
            json=request_data,
        )

        # Handle empty response (204 or empty body)
        if response.status_code == 204:
            return {"status": "deleted"}

        # Try to parse JSON response
        try:
            content = response.text.strip()
            if not content:
                # Empty response body with 200 status
                return {"status": "deleted"}
            data: dict[str, Any] = response.json()
            return data
        except Exception:
            # If parsing fails, assume success if status code is 2xx
            if 200 <= response.status_code < 300:
                return {"status": "deleted"}
            raise

    # User & Role Management

    async def update_current_user(self, user_data: dict[str, Any]) -> dict[str, Any]:
        """Update current user information.

        Args:
            user_data: User data to update. For password change:
                      {"old_password": "current", "new_password": "new"}

        Returns:
            Updated user information.
        """
        response = await self._request(
            "POST",
            "/api/user",
            json=user_data,
        )
        data: dict[str, Any] = response.json()
        return data

    async def list_users(self) -> dict[str, Any]:
        """List all users (admin only).

        Returns:
            List of all users.
        """
        response = await self._request("GET", "/api/users")
        data: dict[str, Any] = response.json()
        return data

    async def create_user(self, user_data: dict[str, Any]) -> dict[str, Any]:
        """Create a new user (admin only).

        Args:
            user_data: New user data with fields:
                      - email: User email
                      - name: Display name
                      - role: Admin|Editor|Viewer
                      - password: Initial password

        Returns:
            Created user.
        """
        # Add action field required by Coroot
        request_data = {"action": "create", **user_data}

        response = await self._request(
            "POST",
            "/api/users",
            json=request_data,
        )
        data: dict[str, Any] = response.json()
        return data

    # Custom Cloud Pricing

    async def get_custom_cloud_pricing(self, project_id: str) -> dict[str, Any]:
        """Get custom cloud pricing configuration.

        Args:
            project_id: Project ID.

        Returns:
            Custom pricing configuration.
        """
        response = await self._request(
            "GET", f"/api/project/{project_id}/custom_cloud_pricing"
        )
        data: dict[str, Any] = response.json()
        return data

    async def update_custom_cloud_pricing(
        self, project_id: str, pricing: dict[str, Any]
    ) -> dict[str, Any]:
        """Update custom cloud pricing configuration.

        Args:
            project_id: Project ID.
            pricing: Custom pricing configuration.

        Returns:
            Updated pricing configuration.
        """
        response = await self._request(
            "POST", f"/api/project/{project_id}/custom_cloud_pricing", json=pricing
        )
        return self._parse_json_response(response)

    async def delete_custom_cloud_pricing(self, project_id: str) -> dict[str, Any]:
        """Delete custom cloud pricing configuration.

        Args:
            project_id: Project ID.

        Returns:
            Deletion status.
        """
        response = await self._request(
            "DELETE", f"/api/project/{project_id}/custom_cloud_pricing"
        )

        # Handle empty response (204 or empty body)
        if response.status_code == 204:
            return {"status": "deleted"}

        # Try to parse JSON response
        try:
            content = response.text.strip()
            if not content:
                # Empty response body with 200 status
                return {"status": "deleted"}
            data: dict[str, Any] = response.json()
            return data
        except Exception:
            # If parsing fails, assume success if status code is 2xx
            if 200 <= response.status_code < 300:
                return {"status": "deleted"}
            raise

    async def get_roles(self) -> dict[str, Any]:
        """Get available roles.

        Returns:
            List of available roles.
        """
        response = await self._request("GET", "/api/roles")
        data: dict[str, Any] = response.json()
        return data

    # Database Instrumentation

    async def get_db_instrumentation(
        self, project_id: str, app_id: str, db_type: str
    ) -> dict[str, Any]:
        """Get database instrumentation configuration.

        Args:
            project_id: Project ID.
            app_id: Application ID.
            db_type: Database type (mysql, postgres, redis, mongodb, memcached).

        Returns:
            Database instrumentation configuration.
        """
        # URL encode the app_id since it contains slashes
        from urllib.parse import quote

        encoded_app_id = quote(app_id, safe="")

        response = await self._request(
            "GET",
            f"/api/project/{project_id}/app/{encoded_app_id}/instrumentation/{db_type}",
        )
        data: dict[str, Any] = response.json()
        return data

    async def update_db_instrumentation(
        self, project_id: str, app_id: str, db_type: str, config: dict[str, Any]
    ) -> dict[str, Any]:
        """Update database instrumentation configuration.

        Args:
            project_id: Project ID.
            app_id: Application ID.
            db_type: Database type (mysql, postgres, redis, mongodb, memcached).
            config: Instrumentation configuration.

        Returns:
            Updated instrumentation configuration.
        """
        # URL encode the app_id since it contains slashes
        from urllib.parse import quote

        encoded_app_id = quote(app_id, safe="")

        response = await self._request(
            "POST",
            f"/api/project/{project_id}/app/{encoded_app_id}/instrumentation/{db_type}",
            json=config,
        )
        data: dict[str, Any] = response.json()
        return data

    # SSO Configuration

    async def get_sso_config(self) -> dict[str, Any]:
        """Get SSO configuration.

        Returns:
            SSO configuration and available roles.
        """
        response = await self._request("GET", "/api/sso")
        data: dict[str, Any] = response.json()
        return data

    async def update_sso_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Update SSO configuration.

        Args:
            config: SSO configuration settings.

        Returns:
            Updated SSO configuration.
        """
        response = await self._request("POST", "/api/sso", json=config)
        data: dict[str, Any] = response.json()
        return data

    # AI Configuration

    async def get_ai_config(self) -> dict[str, Any]:
        """Get AI provider configuration.

        Returns:
            AI provider configuration.
        """
        response = await self._request("GET", "/api/ai")
        data: dict[str, Any] = response.json()
        return data

    async def update_ai_config(self, config: dict[str, Any]) -> dict[str, Any]:
        """Update AI provider configuration.

        Args:
            config: AI provider settings.

        Returns:
            Updated AI configuration.
        """
        response = await self._request("POST", "/api/ai", json=config)
        data: dict[str, Any] = response.json()
        return data

    # Health check

    async def health_check(self) -> bool:
        """Check if Coroot server is healthy.

        Returns:
            True if healthy, False otherwise.
        """
        try:
            response = await self._request("GET", "/health")
            return response.status_code == 200
        except Exception:
            return False

    # Panel Data

    async def get_panel_data(
        self,
        project_id: str,
        dashboard_id: str,
        panel_id: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Get data for a specific dashboard panel.

        Args:
            project_id: The project ID
            dashboard_id: The dashboard ID
            panel_id: The panel ID
            params: Optional query parameters (time range, etc.)

        Returns:
            Dict containing panel data
        """
        query_params = params or {}
        query_params.update({"dashboard": dashboard_id, "panel": panel_id})
        response = await self._request(
            "GET", f"/api/project/{project_id}/panel/data", params=query_params
        )
        data: dict[str, Any] = response.json()
        return data

    # Individual Integration

    async def get_integration(
        self, project_id: str, integration_type: str
    ) -> dict[str, Any]:
        """Get specific integration configuration.

        Args:
            project_id: The project ID
            integration_type: The integration type

        Returns:
            Dict containing integration configuration
        """
        response = await self._request(
            "GET", f"/api/project/{project_id}/integrations/{integration_type}"
        )
        data: dict[str, Any] = response.json()
        return data

    # Advanced Configuration

    async def configure_profiling(
        self, project_id: str, app_id: str, config: dict[str, Any]
    ) -> dict[str, Any]:
        """Configure profiling for an application.

        Args:
            project_id: The project ID
            app_id: The application ID
            config: Profiling configuration

        Returns:
            Dict containing updated configuration
        """
        # URL encode the app_id in case it contains slashes
        encoded_app_id = quote(app_id, safe="")
        response = await self._request(
            "POST",
            f"/api/project/{project_id}/app/{encoded_app_id}/profiling",
            json=config,
        )
        data: dict[str, Any] = response.json()
        return data

    async def configure_tracing(
        self, project_id: str, app_id: str, config: dict[str, Any]
    ) -> dict[str, Any]:
        """Configure tracing for an application.

        Args:
            project_id: The project ID
            app_id: The application ID
            config: Tracing configuration

        Returns:
            Dict containing updated configuration
        """
        # URL encode the app_id in case it contains slashes
        encoded_app_id = quote(app_id, safe="")
        response = await self._request(
            "POST",
            f"/api/project/{project_id}/app/{encoded_app_id}/tracing",
            json=config,
        )
        data: dict[str, Any] = response.json()
        return data

    async def configure_logs(
        self, project_id: str, app_id: str, config: dict[str, Any]
    ) -> dict[str, Any]:
        """Configure log collection for an application.

        Args:
            project_id: The project ID
            app_id: The application ID
            config: Log collection configuration

        Returns:
            Dict containing updated configuration
        """
        # URL encode the app_id in case it contains slashes
        encoded_app_id = quote(app_id, safe="")
        response = await self._request(
            "POST", f"/api/project/{project_id}/app/{encoded_app_id}/logs", json=config
        )
        return self._parse_json_response(response)

    async def create_or_update_role(self, role_data: dict[str, Any]) -> dict[str, Any]:
        """Create or update a role.

        Args:
            role_data: Role configuration

        Returns:
            Dict containing created/updated role
        """
        response = await self._request("POST", "/api/roles", json=role_data)
        data: dict[str, Any] = response.json()
        return data
