"""Tests for client API functionality."""

from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from mcp_coroot.client import CorootError


class TestProjectManagement:
    """Test project management API calls."""

    @pytest.mark.asyncio
    async def test_list_projects_success(self, client, mock_projects):
        """Test successful project listing."""
        # Mock user response that includes projects
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={"email": "admin@example.com", "projects": mock_projects}
        )
        mock_response.raise_for_status = AsyncMock()
        mock_response.headers = {"content-type": "application/json"}

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            projects = await client.list_projects()
            assert len(projects) == 2
            assert projects[0]["id"] == "project1"

    @pytest.mark.asyncio
    async def test_get_project(self, client):
        """Test getting a single project."""
        project_data = {
            "id": "project1",
            "name": "Project 1",
            "settings": {"retention": "30d"},
        }
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value=project_data)
        mock_response.raise_for_status = AsyncMock()
        mock_response.headers = {"content-type": "application/json"}

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            project = await client.get_project("project1")
            assert project["id"] == "project1"
            assert project["settings"]["retention"] == "30d"

    @pytest.mark.asyncio
    async def test_create_project_success(self, client):
        """Test successful project creation."""
        mock_response = AsyncMock()
        project_data = {"id": "new-project", "name": "new-project"}
        mock_response.json = Mock(return_value=project_data)
        mock_response.raise_for_status = AsyncMock()
        mock_response.headers = {"content-type": "application/json"}

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.create_project("new-project")
            assert result["id"] == "new-project"

    @pytest.mark.asyncio
    async def test_create_project_non_json_response(self, client):
        """Test create_project with non-JSON response."""
        mock_response = AsyncMock()
        mock_response.headers = {"content-type": "text/plain"}
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.create_project("test-project")
            assert result["id"] == "test-project"
            assert result["name"] == "test-project"

    @pytest.mark.asyncio
    async def test_create_project_json_parse_error(self, client):
        """Test create_project with JSON parsing error."""
        mock_response = AsyncMock()
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json = Mock(side_effect=ValueError("Invalid JSON"))
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.create_project("test-project")
            assert result["id"] == "test-project"
            assert result["name"] == "test-project"

    @pytest.mark.asyncio
    async def test_get_project_status(self, client):
        """Test getting project status."""
        status_data = {
            "status": "healthy",
            "prometheus": {"connected": True},
            "agents": {"deployed": 5},
        }
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value=status_data)
        mock_response.raise_for_status = AsyncMock()
        mock_response.headers = {"content-type": "application/json"}

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            status = await client.get_project_status("project1")
            assert status["status"] == "healthy"
            assert status["prometheus"]["connected"] is True


class TestApplicationMonitoring:
    """Test application monitoring API calls."""

    @pytest.mark.asyncio
    async def test_get_application_with_params(self, client, mock_application):
        """Test getting application with query parameters."""
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value=mock_application)
        mock_response.raise_for_status = AsyncMock()
        mock_response.headers = {"content-type": "application/json"}

        with patch(
            "httpx.AsyncClient.request", return_value=mock_response
        ) as mock_request:
            app = await client.get_application(
                "project1",
                "app1",
                from_timestamp=1000,
                to_timestamp=2000,
            )

            # Check that params were passed correctly
            call_args = mock_request.call_args
            assert call_args.kwargs["params"]["from"] == "1000"
            assert call_args.kwargs["params"]["to"] == "2000"
            assert app == mock_application

    @pytest.mark.asyncio
    async def test_get_application_logs(self, client):
        """Test getting application logs."""
        logs_data = {
            "logs": [
                {
                    "timestamp": 1234567890,
                    "message": "Error occurred",
                    "severity": "error",
                },
            ],
            "patterns": [{"pattern": "Error occurred", "count": 5}],
        }
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value=logs_data)
        mock_response.raise_for_status = AsyncMock()
        mock_response.headers = {"content-type": "application/json"}

        with patch(
            "httpx.AsyncClient.request", return_value=mock_response
        ) as mock_request:
            logs = await client.get_application_logs(
                "project1",
                "app1",
                from_timestamp=1000,
                to_timestamp=2000,
                query="error",
                severity="error",
            )

            # Check params
            call_args = mock_request.call_args
            params = call_args.kwargs["params"]
            assert params["from"] == "1000"
            assert params["to"] == "2000"
            assert params["query"] == "error"
            assert params["severity"] == "error"
            assert logs == logs_data

    @pytest.mark.asyncio
    async def test_get_application_traces(self, client):
        """Test getting application traces."""
        traces_data = {
            "traces": [
                {
                    "trace_id": "abc123",
                    "duration": 150,
                    "spans": 5,
                }
            ]
        }
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value=traces_data)
        mock_response.raise_for_status = AsyncMock()
        mock_response.headers = {"content-type": "application/json"}

        with patch(
            "httpx.AsyncClient.request", return_value=mock_response
        ) as mock_request:
            traces = await client.get_application_traces(
                "project1",
                "app1",
                from_timestamp=1000,
                to_timestamp=2000,
                trace_id="abc123",
                query="slow",
            )

            # Check params
            call_args = mock_request.call_args
            params = call_args.kwargs["params"]
            assert params["from"] == "1000"
            assert params["to"] == "2000"
            assert params["trace_id"] == "abc123"
            assert params["query"] == "slow"
            assert traces == traces_data


class TestOverviewEndpoints:
    """Test overview API endpoints."""

    @pytest.mark.asyncio
    async def test_get_applications_overview(self, client):
        """Test getting applications overview."""
        overview_data = {
            "applications": [
                {"name": "app1", "status": "healthy"},
                {"name": "app2", "status": "warning"},
            ],
            "total": 2,
        }
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value=overview_data)
        mock_response.raise_for_status = AsyncMock()
        mock_response.headers = {"content-type": "application/json"}

        with patch(
            "httpx.AsyncClient.request", return_value=mock_response
        ) as mock_request:
            overview = await client.get_applications_overview("project1", query="app")

            call_args = mock_request.call_args
            assert call_args.kwargs["params"]["query"] == "app"
            assert overview == overview_data

    @pytest.mark.asyncio
    async def test_get_applications_overview_no_query(self, client):
        """Test getting applications overview without query."""
        overview_data = {"applications": [], "total": 0}
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value=overview_data)
        mock_response.raise_for_status = AsyncMock()
        mock_response.headers = {"content-type": "application/json"}

        with patch(
            "httpx.AsyncClient.request", return_value=mock_response
        ) as mock_request:
            overview = await client.get_applications_overview("project1")

            call_args = mock_request.call_args
            # params should not contain query key when not provided
            assert "query" not in call_args.kwargs.get("params", {})
            assert overview == overview_data

    @pytest.mark.asyncio
    async def test_get_nodes_overview(self, client):
        """Test getting nodes overview."""
        nodes_data = {
            "nodes": [
                {"name": "node1", "cpu": 0.5, "memory": 0.7},
            ]
        }
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value=nodes_data)
        mock_response.raise_for_status = AsyncMock()
        mock_response.headers = {"content-type": "application/json"}

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            nodes = await client.get_nodes_overview("project1")
            assert nodes == nodes_data

    @pytest.mark.asyncio
    async def test_get_traces_overview(self, client):
        """Test getting traces overview."""
        traces_data = {"total_traces": 1000, "error_rate": 0.02}
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value=traces_data)
        mock_response.raise_for_status = AsyncMock()
        mock_response.headers = {"content-type": "application/json"}

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            traces = await client.get_traces_overview("project1")
            assert traces == traces_data

    @pytest.mark.asyncio
    async def test_get_deployments_overview(self, client):
        """Test getting deployments overview."""
        deployments_data = {
            "deployments": [
                {"app": "app1", "version": "v1.2.3", "timestamp": 1234567890},
            ]
        }
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value=deployments_data)
        mock_response.raise_for_status = AsyncMock()
        mock_response.headers = {"content-type": "application/json"}

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            deployments = await client.get_deployments_overview("project1")
            assert deployments == deployments_data


class TestIntegrations:
    """Test integration management."""

    @pytest.mark.asyncio
    async def test_list_integrations(self, client):
        """Test listing integrations."""
        integrations_data = {
            "prometheus": {"configured": True},
            "slack": {"configured": False},
        }
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value=integrations_data)
        mock_response.raise_for_status = AsyncMock()
        mock_response.headers = {"content-type": "application/json"}

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            integrations = await client.list_integrations("project1")
            assert integrations == integrations_data

    @pytest.mark.asyncio
    async def test_configure_integration_success(self, client):
        """Test configuring an integration."""
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value={"status": "configured"})
        mock_response.raise_for_status = AsyncMock()
        mock_response.headers = {"content-type": "application/json"}

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.configure_integration(
                "project1",
                "slack",
                {"webhook_url": "https://hooks.slack.com/..."},
            )
            assert result["status"] == "configured"

    @pytest.mark.asyncio
    async def test_configure_integration_non_json_response(self, client):
        """Test configure_integration with non-JSON response."""
        mock_response = AsyncMock()
        mock_response.headers = {"content-type": "text/html"}
        mock_response.raise_for_status = AsyncMock()

        config = {"webhook_url": "https://example.com/webhook"}
        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.configure_integration("project1", "webhook", config)
            assert result["type"] == "webhook"
            assert result["config"] == config
            assert result["status"] == "configured"

    @pytest.mark.asyncio
    async def test_configure_integration_json_parse_error(self, client):
        """Test configure_integration with JSON parsing error."""
        mock_response = AsyncMock()
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json = Mock(side_effect=ValueError("Invalid JSON"))
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.configure_integration("project1", "webhook", {})
            assert result["type"] == "webhook"
            assert result["status"] == "configured"


class TestHealthCheck:
    """Test health check functionality."""

    @pytest.mark.asyncio
    async def test_health_check_success(self, client):
        """Test successful health check."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.health_check()
            assert result is True

    @pytest.mark.asyncio
    async def test_health_check_failure(self, client):
        """Test failed health check."""
        with patch(
            "httpx.AsyncClient.request", side_effect=Exception("Connection error")
        ):
            result = await client.health_check()
            assert result is False


class TestConfigurationManagement:
    """Test configuration management API calls."""

    @pytest.mark.asyncio
    async def test_list_inspections(self, client):
        """Test list inspections."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "checks": [
                    {"id": "SLOAvailability", "title": "SLO / Availability"},
                    {"id": "CPU", "title": "CPU"},
                ]
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.list_inspections("project123")

        assert result == mock_response.json.return_value
        assert result["checks"][0]["id"] == "SLOAvailability"

    @pytest.mark.asyncio
    async def test_get_inspection_config(self, client):
        """Test get inspection config."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "form": {"configs": [{"objective_percentage": 99}]},
                "integrations": [{"name": "Pagerduty"}],
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.get_inspection_config(
                "project123", "namespace/deployment/app", "SLOAvailability"
            )

        assert result == mock_response.json.return_value
        assert result["form"]["configs"][0]["objective_percentage"] == 99

    @pytest.mark.asyncio
    async def test_update_inspection_config(self, client):
        """Test update inspection config."""
        config = {"form": {"configs": [{"objective_percentage": 95}]}}
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value=config)
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.update_inspection_config(
                "project123", "namespace/deployment/app", "SLOAvailability", config
            )

        assert result == mock_response.json.return_value

    @pytest.mark.asyncio
    async def test_get_application_categories(self, client):
        """Test get application categories."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value=[
                {"name": "application", "builtin": True, "default": True},
                {"name": "control-plane", "builtin": True, "default": False},
            ]
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.get_application_categories("project123")

        assert result == mock_response.json.return_value
        assert len(result) == 2
        assert result[0]["name"] == "application"

    @pytest.mark.asyncio
    async def test_update_application_categories(self, client):
        """Test update application categories."""
        categories = [{"name": "custom", "custom_patterns": "custom/*"}]
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value=categories)
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.update_application_categories(
                "project123", categories
            )

        assert result == mock_response.json.return_value

    @pytest.mark.asyncio
    async def test_get_custom_applications(self, client):
        """Test get custom applications."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "custom_applications": [
                    {"name": "my-app", "instance_patterns": ["container_name:my-app-*"]}
                ]
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.get_custom_applications("project123")

        assert result == mock_response.json.return_value
        assert result["custom_applications"][0]["name"] == "my-app"

    @pytest.mark.asyncio
    async def test_update_custom_applications(self, client):
        """Test update custom applications."""
        applications = {
            "custom_applications": [
                {"name": "new-app", "instance_patterns": ["container_name:new-*"]}
            ]
        }
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value=applications)
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.update_custom_applications("project123", applications)

        assert result == mock_response.json.return_value


class TestErrorHandling:
    """Test error handling across API calls."""

    @pytest.mark.asyncio
    async def test_api_error(self, client):
        """Test handling of API errors."""
        mock_response = AsyncMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"

        error = httpx.HTTPStatusError(
            "500 Server Error",
            request=AsyncMock(),
            response=mock_response,
        )

        with patch("httpx.AsyncClient.request", side_effect=error):
            with pytest.raises(CorootError, match="API request failed: 500"):
                await client.list_projects()

    @pytest.mark.asyncio
    async def test_network_error(self, client):
        """Test handling of network errors."""
        with patch(
            "httpx.AsyncClient.request",
            side_effect=httpx.ConnectError("Connection failed"),
        ):
            with pytest.raises(CorootError, match="Connection failed"):
                await client.list_projects()
