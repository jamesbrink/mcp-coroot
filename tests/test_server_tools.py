"""Tests for server tool implementations."""

from unittest.mock import AsyncMock, patch

import pytest

from mcp_coroot.client import CorootError
from mcp_coroot.server import (
    configure_integration_impl,
    create_project_impl,
    get_application_impl,
    get_application_logs_impl,
    get_application_traces_impl,
    get_applications_overview_impl,
    get_current_user_impl,
    get_deployments_overview_impl,
    get_nodes_overview_impl,
    get_project_impl,
    get_project_status_impl,
    get_traces_overview_impl,
    health_check_impl,
    list_integrations_impl,
    list_projects_impl,
)


class TestUserTools:
    """Test user-related tools."""

    @pytest.mark.asyncio
    async def test_get_current_user_success(self, mock_user):
        """Test successful get current user."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_current_user.return_value = mock_user
            mock_get_client.return_value = mock_client

            result = await get_current_user_impl()

            assert result["success"] is True
            assert result["user"] == mock_user

    @pytest.mark.asyncio
    async def test_get_current_user_error(self):
        """Test get current user with error."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_current_user.side_effect = CorootError("Auth error")
            mock_get_client.return_value = mock_client

            result = await get_current_user_impl()

            assert result["success"] is False
            assert "Auth error" in result["error"]


class TestProjectTools:
    """Test project management tools."""

    @pytest.mark.asyncio
    async def test_list_projects_success(self, mock_projects):
        """Test successful project listing."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.list_projects.return_value = mock_projects
            mock_get_client.return_value = mock_client

            result = await list_projects_impl()

            assert result["success"] is True
            assert result["count"] == 2
            assert result["projects"] == mock_projects

    @pytest.mark.asyncio
    async def test_get_project_success(self):
        """Test successful project retrieval."""
        project_data = {"id": "project1", "name": "Project 1", "settings": {}}
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_project.return_value = project_data
            mock_get_client.return_value = mock_client

            result = await get_project_impl("project1")

            assert result["success"] is True
            assert result["project"] == project_data

    @pytest.mark.asyncio
    async def test_create_project_success(self):
        """Test successful project creation."""
        new_project = {"id": "new-project", "name": "new-project"}
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.create_project.return_value = new_project
            mock_get_client.return_value = mock_client

            result = await create_project_impl("new-project")

            assert result["success"] is True
            assert result["message"] == "Project created successfully"
            assert result["project"] == new_project

    @pytest.mark.asyncio
    async def test_get_project_status_success(self):
        """Test successful project status retrieval."""
        status_data = {"status": "healthy", "prometheus": {"connected": True}}
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_project_status.return_value = status_data
            mock_get_client.return_value = mock_client

            result = await get_project_status_impl("project1")

            assert result["success"] is True
            assert result["status"] == status_data


class TestApplicationTools:
    """Test application monitoring tools."""

    @pytest.mark.asyncio
    async def test_get_application_success(self, mock_application):
        """Test successful application retrieval."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_application.return_value = mock_application
            mock_get_client.return_value = mock_client

            result = await get_application_impl(
                "project1", "default/deployment/frontend"
            )

            assert result["success"] is True
            assert result["application"] == mock_application

            # Verify URL encoding was applied
            mock_client.get_application.assert_called_once_with(
                "project1",
                "default%2Fdeployment%2Ffrontend",
                None,
                None,
            )

    @pytest.mark.asyncio
    async def test_get_application_with_timestamps(self, mock_application):
        """Test getting application with timestamp parameters."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_application.return_value = mock_application
            mock_get_client.return_value = mock_client

            result = await get_application_impl(
                "project1", "app1", from_timestamp=1000, to_timestamp=2000
            )

            assert result["success"] is True
            mock_client.get_application.assert_called_once_with(
                "project1", "app1", 1000, 2000
            )

    @pytest.mark.asyncio
    async def test_get_application_logs_success(self):
        """Test successful application logs retrieval."""
        logs_data = {"logs": [{"message": "Error", "severity": "error"}]}
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_application_logs.return_value = logs_data
            mock_get_client.return_value = mock_client

            result = await get_application_logs_impl(
                "project1",
                "app1",
                from_timestamp=1000,
                to_timestamp=2000,
                query="error",
                severity="error",
            )

            assert result["success"] is True
            assert result["logs"] == logs_data

            # Verify URL encoding was applied
            mock_client.get_application_logs.assert_called_once_with(
                "project1", "app1", 1000, 2000, "error", "error"
            )

    @pytest.mark.asyncio
    async def test_get_application_traces_success(self):
        """Test successful application traces retrieval."""
        traces_data = {"traces": [{"trace_id": "abc123", "duration": 150}]}
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_application_traces.return_value = traces_data
            mock_get_client.return_value = mock_client

            result = await get_application_traces_impl(
                "project1",
                "app1",
                from_timestamp=1000,
                to_timestamp=2000,
                trace_id="abc123",
                query="slow",
            )

            assert result["success"] is True
            assert result["traces"] == traces_data


class TestOverviewTools:
    """Test overview tools."""

    @pytest.mark.asyncio
    async def test_get_applications_overview_success(self):
        """Test successful applications overview."""
        overview_data = {"applications": [{"name": "app1", "status": "healthy"}]}
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_applications_overview.return_value = overview_data
            mock_get_client.return_value = mock_client

            result = await get_applications_overview_impl("project1", query="app")

            assert result["success"] is True
            assert result["overview"] == overview_data

    @pytest.mark.asyncio
    async def test_get_nodes_overview_success(self):
        """Test successful nodes overview."""
        nodes_data = {"nodes": [{"name": "node1", "cpu": 0.5}]}
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_nodes_overview.return_value = nodes_data
            mock_get_client.return_value = mock_client

            result = await get_nodes_overview_impl("project1")

            assert result["success"] is True
            assert result["overview"] == nodes_data

    @pytest.mark.asyncio
    async def test_get_traces_overview_success(self):
        """Test successful traces overview."""
        traces_data = {"total_traces": 1000, "error_rate": 0.02}
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_traces_overview.return_value = traces_data
            mock_get_client.return_value = mock_client

            result = await get_traces_overview_impl("project1")

            assert result["success"] is True
            assert result["overview"] == traces_data

    @pytest.mark.asyncio
    async def test_get_deployments_overview_success(self):
        """Test successful deployments overview."""
        deployments_data = {"deployments": [{"app": "app1", "version": "v1.2.3"}]}
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_deployments_overview.return_value = deployments_data
            mock_get_client.return_value = mock_client

            result = await get_deployments_overview_impl("project1")

            assert result["success"] is True
            assert result["overview"] == deployments_data


class TestIntegrationTools:
    """Test integration management tools."""

    @pytest.mark.asyncio
    async def test_list_integrations_success(self):
        """Test successful integrations listing."""
        integrations_data = {"prometheus": {"configured": True}}
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.list_integrations.return_value = integrations_data
            mock_get_client.return_value = mock_client

            result = await list_integrations_impl("project1")

            assert result["success"] is True
            assert result["integrations"] == integrations_data

    @pytest.mark.asyncio
    async def test_configure_integration_success(self):
        """Test successful integration configuration."""
        config_result = {"status": "configured"}
        config = {"webhook_url": "https://example.com"}
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.configure_integration.return_value = config_result
            mock_get_client.return_value = mock_client

            result = await configure_integration_impl("project1", "webhook", config)

            assert result["success"] is True
            assert result["message"] == "webhook integration configured successfully"
            assert result["integration"] == config_result


class TestHealthCheck:
    """Test health check tool."""

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """Test successful health check."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.health_check.return_value = True
            mock_get_client.return_value = mock_client

            result = await health_check_impl()

            assert result["success"] is True
            assert result["healthy"] is True
            assert "healthy" in result["message"]

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        """Test failed health check."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.health_check.return_value = False
            mock_get_client.return_value = mock_client

            result = await health_check_impl()

            assert result["success"] is True
            assert result["healthy"] is False
            assert "not responding" in result["message"]


class TestErrorHandling:
    """Test error handling in server tools."""

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test error handling in tools."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.list_projects.side_effect = CorootError("API error")
            mock_get_client.return_value = mock_client

            result = await list_projects_impl()

            assert result["success"] is False
            assert "API error" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        """Test handling of missing credentials."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_get_client.side_effect = ValueError("No credentials")

            result = await list_projects_impl()

            assert result["success"] is False
            assert "No credentials" in result["error"]

    @pytest.mark.asyncio
    async def test_unexpected_error(self):
        """Test handling of unexpected errors."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.list_projects.side_effect = RuntimeError("Unexpected")
            mock_get_client.return_value = mock_client

            result = await list_projects_impl()

            assert result["success"] is False
            assert "Unexpected error" in result["error"]
