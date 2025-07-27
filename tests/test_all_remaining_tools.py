"""Tests for all remaining tool implementations."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from mcp_coroot.server import (
    create_api_key_impl,
    create_dashboard_impl,
    create_user_impl,
    delete_api_key_impl,
    delete_integration_impl,
    delete_project_impl,
    get_dashboard_impl,
    get_incident_impl,
    # Node & Incident Management
    get_node_impl,
    get_roles_impl,
    list_api_keys_impl,
    # Dashboard Management
    list_dashboards_impl,
    list_users_impl,
    # User & Role Management
    update_current_user_impl,
    update_dashboard_impl,
    # Advanced Project Management
    update_project_settings_impl,
)
from mcp_coroot.server import (
    # Integration Management
    test_integration_impl as check_integration_impl,  # Rename to avoid pytest detection
)


@pytest.mark.asyncio
class TestNodeIncidentManagement:
    """Test node and incident management tools."""

    @patch("mcp_coroot.server.get_client")
    async def test_get_node_success(self, mock_get_client: Mock) -> None:
        """Test successful node retrieval."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_response = {
            "id": "node1",
            "name": "worker-1",
            "cpu": {"usage": 0.45, "cores": 8},
            "memory": {"usage": 0.67, "total_gb": 32},
            "containers": [{"name": "app1", "status": "running"}],
        }
        mock_client.get_node.return_value = mock_response

        result = await get_node_impl("project123", "node1")

        assert result["success"] is True
        assert result["node"] == mock_response
        mock_client.get_node.assert_called_once_with("project123", "node1")

    @patch("mcp_coroot.server.get_client")
    async def test_get_incident_success(self, mock_get_client: Mock) -> None:
        """Test successful incident retrieval."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_response = {
            "id": "incident1",
            "title": "High CPU usage",
            "severity": "critical",
            "status": "resolved",
            "timeline": [{"event": "started", "timestamp": 1234567890}],
        }
        mock_client.get_incident.return_value = mock_response

        result = await get_incident_impl("project123", "incident1")

        assert result["success"] is True
        assert result["incident"] == mock_response
        mock_client.get_incident.assert_called_once_with("project123", "incident1")


@pytest.mark.asyncio
class TestDashboardManagement:
    """Test dashboard management tools."""

    @patch("mcp_coroot.server.get_client")
    async def test_list_dashboards_success(self, mock_get_client: Mock) -> None:
        """Test successful dashboard listing."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_response = {
            "dashboards": [
                {"id": "dash1", "name": "Service Overview"},
                {"id": "dash2", "name": "Performance Metrics"},
            ]
        }
        mock_client.list_dashboards.return_value = mock_response

        result = await list_dashboards_impl("project123")

        assert result["success"] is True
        assert result["dashboards"] == mock_response
        mock_client.list_dashboards.assert_called_once_with("project123")

    @patch("mcp_coroot.server.get_client")
    async def test_create_dashboard_success(self, mock_get_client: Mock) -> None:
        """Test successful dashboard creation."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        dashboard = {
            "name": "New Dashboard",
            "panels": [{"type": "graph", "query": "cpu_usage"}],
        }
        mock_response = {"id": "dash3", **dashboard}
        mock_client.create_dashboard.return_value = mock_response

        result = await create_dashboard_impl("project123", dashboard)

        assert result["success"] is True
        assert result["message"] == "Dashboard created successfully"
        assert result["dashboard"] == mock_response
        mock_client.create_dashboard.assert_called_once_with("project123", dashboard)

    @patch("mcp_coroot.server.get_client")
    async def test_get_dashboard_success(self, mock_get_client: Mock) -> None:
        """Test successful dashboard retrieval."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_response = {
            "id": "dash1",
            "name": "Service Overview",
            "panels": [{"type": "graph", "query": "service_latency"}],
        }
        mock_client.get_dashboard.return_value = mock_response

        result = await get_dashboard_impl("project123", "dash1")

        assert result["success"] is True
        assert result["dashboard"] == mock_response
        mock_client.get_dashboard.assert_called_once_with("project123", "dash1")

    @patch("mcp_coroot.server.get_client")
    async def test_update_dashboard_success(self, mock_get_client: Mock) -> None:
        """Test successful dashboard update."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        dashboard = {"name": "Updated Dashboard", "panels": []}
        mock_response = {"id": "dash1", **dashboard}
        mock_client.update_dashboard.return_value = mock_response

        result = await update_dashboard_impl("project123", "dash1", dashboard)

        assert result["success"] is True
        assert result["message"] == "Dashboard updated successfully"
        assert result["dashboard"] == mock_response
        mock_client.update_dashboard.assert_called_once_with(
            "project123", "dash1", dashboard
        )


@pytest.mark.asyncio
class TestIntegrationManagement:
    """Test integration management tools."""

    @patch("mcp_coroot.server.get_client")
    async def test_test_integration_success(self, mock_get_client: Mock) -> None:
        """Test successful integration test."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_response = {"status": "success", "message": "Connection successful"}
        mock_client.test_integration.return_value = mock_response

        result = await check_integration_impl("project123", "prometheus")

        assert result["success"] is True
        assert result["message"] == "prometheus integration test completed"
        assert result["result"] == mock_response
        mock_client.test_integration.assert_called_once_with("project123", "prometheus")

    @patch("mcp_coroot.server.get_client")
    async def test_delete_integration_success(self, mock_get_client: Mock) -> None:
        """Test successful integration deletion."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_response = {"status": "deleted"}
        mock_client.delete_integration.return_value = mock_response

        result = await delete_integration_impl("project123", "slack")

        assert result["success"] is True
        assert result["message"] == "slack integration deleted successfully"
        assert result["result"] == mock_response
        mock_client.delete_integration.assert_called_once_with("project123", "slack")


@pytest.mark.asyncio
class TestAdvancedProjectManagement:
    """Test advanced project management tools."""

    @patch("mcp_coroot.server.get_client")
    async def test_update_project_settings_success(self, mock_get_client: Mock) -> None:
        """Test successful project settings update."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        settings = {"retention": "90d", "alerting": {"enabled": True}}
        mock_response = {"id": "project123", "settings": settings}
        mock_client.update_project.return_value = mock_response

        result = await update_project_settings_impl("project123", settings)

        assert result["success"] is True
        assert result["message"] == "Project settings updated successfully"
        assert result["project"] == mock_response
        mock_client.update_project.assert_called_once_with("project123", settings)

    @patch("mcp_coroot.server.get_client")
    async def test_delete_project_success(self, mock_get_client: Mock) -> None:
        """Test successful project deletion."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_response = {"status": "deleted"}
        mock_client.delete_project.return_value = mock_response

        result = await delete_project_impl("project123")

        assert result["success"] is True
        assert result["message"] == "Project project123 deleted successfully"
        assert result["result"] == mock_response
        mock_client.delete_project.assert_called_once_with("project123")

    @patch("mcp_coroot.server.get_client")
    async def test_list_api_keys_success(self, mock_get_client: Mock) -> None:
        """Test successful API key listing."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_response = {
            "keys": [
                {"id": "key1", "name": "Metrics Ingestion", "created_at": 1234567890},
                {"id": "key2", "name": "Backup Agent", "created_at": 1234567891},
            ]
        }
        mock_client.list_api_keys.return_value = mock_response

        result = await list_api_keys_impl("project123")

        assert result["success"] is True
        assert result["api_keys"] == mock_response
        mock_client.list_api_keys.assert_called_once_with("project123")

    @patch("mcp_coroot.server.get_client")
    async def test_create_api_key_success(self, mock_get_client: Mock) -> None:
        """Test successful API key creation."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_response = {
            "id": "key3",
            "name": "New Key",
            "secret": "sk_live_abcd1234",
            "created_at": 1234567892,
        }
        mock_client.create_api_key.return_value = mock_response

        result = await create_api_key_impl("project123", "New Key", "Test key")

        assert result["success"] is True
        assert result["message"] == "API key created successfully"
        assert result["api_key"] == mock_response
        mock_client.create_api_key.assert_called_once_with(
            "project123", "New Key", "Test key"
        )

    @patch("mcp_coroot.server.get_client")
    async def test_delete_api_key_success(self, mock_get_client: Mock) -> None:
        """Test successful API key deletion."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        # Mock successful deletion (no return value)
        mock_client.delete_api_key.return_value = None

        result = await delete_api_key_impl("project123", "EMUHGTklu-miwJKD5IjO2Z4OSyO8Vrzn")

        assert result["success"] is True
        assert result["message"] == "API key deleted successfully"
        mock_client.delete_api_key.assert_called_once_with(
            "project123", "EMUHGTklu-miwJKD5IjO2Z4OSyO8Vrzn"
        )


@pytest.mark.asyncio
class TestUserRoleManagement:
    """Test user and role management tools."""

    @patch("mcp_coroot.server.get_client")
    async def test_update_current_user_success(self, mock_get_client: Mock) -> None:
        """Test successful current user update."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        user_data = {"name": "John Doe", "email": "john@example.com"}
        mock_response = {"id": "user1", **user_data}
        mock_client.update_current_user.return_value = mock_response

        result = await update_current_user_impl(user_data)

        assert result["success"] is True
        assert result["message"] == "User updated successfully"
        assert result["user"] == mock_response
        mock_client.update_current_user.assert_called_once_with(user_data)

    @patch("mcp_coroot.server.get_client")
    async def test_list_users_success(self, mock_get_client: Mock) -> None:
        """Test successful user listing."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_response = {
            "users": [
                {"id": "user1", "email": "admin@example.com", "role": "Admin"},
                {"id": "user2", "email": "viewer@example.com", "role": "Viewer"},
            ]
        }
        mock_client.list_users.return_value = mock_response

        result = await list_users_impl()

        assert result["success"] is True
        assert result["users"] == mock_response
        mock_client.list_users.assert_called_once()

    @patch("mcp_coroot.server.get_client")
    async def test_create_user_success(self, mock_get_client: Mock) -> None:
        """Test successful user creation."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        user_data = {
            "email": "newuser@example.com",
            "name": "New User",
            "role": "Editor",
        }
        mock_response = {"id": "user3", **user_data}
        mock_client.create_user.return_value = mock_response

        result = await create_user_impl(user_data)

        assert result["success"] is True
        assert result["message"] == "User created successfully"
        assert result["user"] == mock_response
        mock_client.create_user.assert_called_once_with(user_data)

    @patch("mcp_coroot.server.get_client")
    async def test_get_roles_success(self, mock_get_client: Mock) -> None:
        """Test successful role retrieval."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_response = {
            "roles": [
                {"name": "Admin", "permissions": ["all"]},
                {"name": "Editor", "permissions": ["read", "write"]},
                {"name": "Viewer", "permissions": ["read"]},
            ]
        }
        mock_client.get_roles.return_value = mock_response

        result = await get_roles_impl()

        assert result["success"] is True
        assert result["roles"] == mock_response
        mock_client.get_roles.assert_called_once()


@pytest.mark.asyncio
class TestErrorHandling:
    """Test error handling for all tools."""

    @patch("mcp_coroot.server.get_client")
    async def test_node_error(self, mock_get_client: Mock) -> None:
        """Test node retrieval error handling."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_client.get_node.side_effect = Exception("Node not found")

        result = await get_node_impl("project123", "node999")

        assert result["success"] is False
        assert "Unexpected error" in result["error"]

    @patch("mcp_coroot.server.get_client")
    async def test_dashboard_validation_error(self, mock_get_client: Mock) -> None:
        """Test dashboard creation validation error."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_client.create_dashboard.side_effect = ValueError(
            "Invalid dashboard format"
        )

        result = await create_dashboard_impl("project123", {"invalid": "data"})

        assert result["success"] is False
        assert result["error"] == "Invalid dashboard format"
