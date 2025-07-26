"""Tests for final remaining tools."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from mcp_coroot.server import (
    configure_logs_impl,
    # Advanced Configuration
    configure_profiling_impl,
    configure_tracing_impl,
    # Role Management
    create_or_update_role_impl,
    # Individual Integration
    get_integration_impl,
    # Panel Data
    get_panel_data_impl,
)


@pytest.mark.asyncio
class TestPanelData:
    """Test panel data tool."""

    @patch("mcp_coroot.server.get_client")
    async def test_get_panel_data_success(self, mock_get_client: Mock) -> None:
        """Test successful panel data retrieval."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client

        mock_response = {
            "metrics": [{"timestamp": 1234567890, "value": 42.5}],
            "title": "CPU Usage",
        }
        mock_client.get_panel_data = AsyncMock(return_value=mock_response)

        result = await get_panel_data_impl(
            "project123", "dashboard1", "panel1", "-1h", "now"
        )

        assert result["success"] is True
        assert result["data"] == mock_response
        mock_client.get_panel_data.assert_called_once_with(
            "project123",
            "dashboard1",
            "panel1",
            {"from": "-1h", "to": "now"},
        )

    @patch("mcp_coroot.server.get_client")
    async def test_get_panel_data_no_time_params(self, mock_get_client: Mock) -> None:
        """Test panel data retrieval without time parameters."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client

        mock_response = {"metrics": [], "title": "Memory Usage"}
        mock_client.get_panel_data = AsyncMock(return_value=mock_response)

        result = await get_panel_data_impl("project123", "dashboard1", "panel1")

        assert result["success"] is True
        mock_client.get_panel_data.assert_called_once_with(
            "project123", "dashboard1", "panel1", {}
        )


@pytest.mark.asyncio
class TestIndividualIntegration:
    """Test individual integration tool."""

    @patch("mcp_coroot.server.get_client")
    async def test_get_integration_success(self, mock_get_client: Mock) -> None:
        """Test successful integration config retrieval."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client

        mock_response = {
            "type": "prometheus",
            "url": "http://prometheus:9090",
            "enabled": True,
        }
        mock_client.get_integration = AsyncMock(return_value=mock_response)

        result = await get_integration_impl("project123", "prometheus")

        assert result["success"] is True
        assert result["config"] == mock_response
        mock_client.get_integration.assert_called_once_with("project123", "prometheus")


@pytest.mark.asyncio
class TestAdvancedConfiguration:
    """Test advanced configuration tools."""

    @patch("mcp_coroot.server.get_client")
    async def test_configure_profiling_success(self, mock_get_client: Mock) -> None:
        """Test successful profiling configuration."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client

        mock_response = {"enabled": True, "sample_rate": 0.1}
        mock_client.configure_profiling = AsyncMock(return_value=mock_response)

        result = await configure_profiling_impl(
            "project123", "app/deployment", True, 0.1
        )

        assert result["success"] is True
        assert result["message"] == "Profiling configuration updated successfully"
        assert result["config"] == mock_response

    @patch("mcp_coroot.server.get_client")
    async def test_configure_profiling_no_sample_rate(
        self, mock_get_client: Mock
    ) -> None:
        """Test profiling configuration without sample rate."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client

        mock_response = {"enabled": False}
        mock_client.configure_profiling = AsyncMock(return_value=mock_response)

        result = await configure_profiling_impl("project123", "app/deployment", False)

        assert result["success"] is True
        mock_client.configure_profiling.assert_called_once_with(
            "project123", "app/deployment", {"enabled": False}
        )

    @patch("mcp_coroot.server.get_client")
    async def test_configure_tracing_success(self, mock_get_client: Mock) -> None:
        """Test successful tracing configuration."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client

        mock_response = {
            "enabled": True,
            "sample_rate": 0.05,
            "excluded_paths": ["/health", "/metrics"],
        }
        mock_client.configure_tracing = AsyncMock(return_value=mock_response)

        result = await configure_tracing_impl(
            "project123", "app/deployment", True, 0.05, ["/health", "/metrics"]
        )

        assert result["success"] is True
        assert result["message"] == "Tracing configuration updated successfully"
        assert result["config"] == mock_response

    @patch("mcp_coroot.server.get_client")
    async def test_configure_logs_success(self, mock_get_client: Mock) -> None:
        """Test successful log configuration."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client

        mock_response = {
            "enabled": True,
            "level": "warn",
            "excluded_patterns": [".*debug.*", ".*trace.*"],
        }
        mock_client.configure_logs = AsyncMock(return_value=mock_response)

        result = await configure_logs_impl(
            "project123", "app/deployment", True, "warn", [".*debug.*", ".*trace.*"]
        )

        assert result["success"] is True
        assert result["message"] == "Log collection configuration updated successfully"
        assert result["config"] == mock_response


@pytest.mark.asyncio
class TestRoleManagement:
    """Test role management tool."""

    @patch("mcp_coroot.server.get_client")
    async def test_create_or_update_role_success(self, mock_get_client: Mock) -> None:
        """Test successful role creation/update."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client

        mock_response = {
            "name": "CustomRole",
            "permissions": ["read", "write"],
            "description": "Custom role for testing",
        }
        mock_client.create_or_update_role = AsyncMock(return_value=mock_response)

        result = await create_or_update_role_impl(
            "CustomRole", ["read", "write"], "Custom role for testing"
        )

        assert result["success"] is True
        assert result["message"] == "Role created/updated successfully"
        assert result["role"] == mock_response

    @patch("mcp_coroot.server.get_client")
    async def test_create_role_no_description(self, mock_get_client: Mock) -> None:
        """Test role creation without description."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client

        mock_response = {"name": "BasicRole", "permissions": ["read"]}
        mock_client.create_or_update_role = AsyncMock(return_value=mock_response)

        result = await create_or_update_role_impl("BasicRole", ["read"])

        assert result["success"] is True
        mock_client.create_or_update_role.assert_called_once_with(
            {"name": "BasicRole", "permissions": ["read"]}
        )


@pytest.mark.asyncio
class TestErrorHandling:
    """Test error handling for final tools."""

    @patch("mcp_coroot.server.get_client")
    async def test_panel_data_error(self, mock_get_client: Mock) -> None:
        """Test panel data error handling."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client

        mock_client.get_panel_data = AsyncMock(side_effect=Exception("Panel not found"))

        result = await get_panel_data_impl("project123", "dashboard1", "panel1")

        assert result["success"] is False
        assert "Unexpected error" in result["error"]

    @patch("mcp_coroot.server.get_client")
    async def test_configure_profiling_validation_error(
        self, mock_get_client: Mock
    ) -> None:
        """Test profiling validation error."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client

        mock_client.configure_profiling = AsyncMock(
            side_effect=ValueError("Invalid sample rate")
        )

        result = await configure_profiling_impl(
            "project123", "app/deployment", True, 2.0
        )

        assert result["success"] is False
        assert result["error"] == "Invalid sample rate"
