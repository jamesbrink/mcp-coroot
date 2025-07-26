"""Tests for configuration management tools."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from mcp_coroot.server import (
    get_application_categories_impl,
    get_custom_applications_impl,
    get_inspection_config_impl,
    list_inspections_impl,
    update_application_categories_impl,
    update_custom_applications_impl,
    update_inspection_config_impl,
)


@pytest.mark.asyncio
class TestConfigurationTools:
    """Test configuration management tools."""

    @patch("mcp_coroot.server.get_client")
    async def test_list_inspections_success(self, mock_get_client: Mock) -> None:
        """Test successful list inspections."""
        # Setup mock client
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_response = {
            "checks": [
                {
                    "id": "SLOAvailability",
                    "title": "SLO / Availability",
                    "status": "unknown",
                    "threshold": 0,
                    "unit": "percent",
                },
                {
                    "id": "SLOLatency",
                    "title": "SLO / Latency",
                    "status": "unknown",
                    "threshold": 0,
                    "unit": "seconds",
                },
            ]
        }
        mock_client.list_inspections.return_value = mock_response

        result = await list_inspections_impl("project123")

        assert result["success"] is True
        assert result["inspections"] == mock_response
        mock_client.list_inspections.assert_called_once_with("project123")

    @patch("mcp_coroot.server.get_client")
    async def test_get_inspection_config_success(self, mock_get_client: Mock) -> None:
        """Test successful get inspection config."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_response = {
            "form": {
                "configs": [
                    {
                        "custom": False,
                        "total_requests_query": "",
                        "failed_requests_query": "",
                        "objective_percentage": 99,
                    }
                ],
                "default": True,
            },
            "integrations": [{"name": "Pagerduty", "details": ""}],
        }
        mock_client.get_inspection_config.return_value = mock_response

        result = await get_inspection_config_impl(
            "project123", "namespace/deployment/app1", "SLOAvailability"
        )

        assert result["success"] is True
        assert result["config"] == mock_response
        mock_client.get_inspection_config.assert_called_once_with(
            "project123", "namespace/deployment/app1", "SLOAvailability"
        )

    @patch("mcp_coroot.server.get_client")
    async def test_update_inspection_config_success(
        self, mock_get_client: Mock
    ) -> None:
        """Test successful update inspection config."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        config = {
            "form": {
                "configs": [
                    {
                        "custom": False,
                        "objective_percentage": 95,
                    }
                ],
                "default": False,
            }
        }
        mock_response = config
        mock_client.update_inspection_config.return_value = mock_response

        result = await update_inspection_config_impl(
            "project123", "namespace/deployment/app1", "SLOAvailability", config
        )

        assert result["success"] is True
        assert result["message"] == "SLOAvailability inspection configured successfully"
        assert result["config"] == mock_response
        mock_client.update_inspection_config.assert_called_once_with(
            "project123", "namespace/deployment/app1", "SLOAvailability", config
        )

    @patch("mcp_coroot.server.get_client")
    async def test_get_application_categories_success(
        self, mock_get_client: Mock
    ) -> None:
        """Test successful get application categories."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_response = [
            {
                "name": "application",
                "builtin": True,
                "default": True,
                "builtin_patterns": "",
                "custom_patterns": "",
                "notification_settings": {
                    "incidents": {"enabled": True, "pagerduty": {"enabled": True}},
                    "deployments": {"enabled": False},
                },
            },
            {
                "name": "control-plane",
                "builtin": True,
                "default": False,
                "builtin_patterns": "kube-system/*",
                "custom_patterns": "",
            },
        ]
        mock_client.get_application_categories.return_value = mock_response

        result = await get_application_categories_impl("project123")

        assert result["success"] is True
        assert result["categories"] == mock_response
        mock_client.get_application_categories.assert_called_once_with("project123")

    @patch("mcp_coroot.server.get_client")
    async def test_update_application_categories_success(
        self, mock_get_client: Mock
    ) -> None:
        """Test successful update application categories."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        categories = [
            {
                "name": "custom-category",
                "builtin": False,
                "custom_patterns": "custom-ns/*",
            }
        ]
        mock_response = categories
        mock_client.update_application_categories.return_value = mock_response

        result = await update_application_categories_impl("project123", categories)

        assert result["success"] is True
        assert result["message"] == "Application categories updated successfully"
        assert result["categories"] == mock_response
        mock_client.update_application_categories.assert_called_once_with(
            "project123", categories
        )

    @patch("mcp_coroot.server.get_client")
    async def test_get_custom_applications_success(self, mock_get_client: Mock) -> None:
        """Test successful get custom applications."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_response = {
            "custom_applications": [
                {
                    "name": "my-app",
                    "instance_patterns": ["container_name:my-app-*"],
                }
            ]
        }
        mock_client.get_custom_applications.return_value = mock_response

        result = await get_custom_applications_impl("project123")

        assert result["success"] is True
        assert result["applications"] == mock_response
        mock_client.get_custom_applications.assert_called_once_with("project123")

    @patch("mcp_coroot.server.get_client")
    async def test_update_custom_applications_success(
        self, mock_get_client: Mock
    ) -> None:
        """Test successful update custom applications."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        applications = {
            "custom_applications": [
                {
                    "name": "new-app",
                    "instance_patterns": ["container_name:new-app-*"],
                }
            ]
        }
        mock_response = applications
        mock_client.update_custom_applications.return_value = mock_response

        result = await update_custom_applications_impl("project123", applications)

        assert result["success"] is True
        assert result["message"] == "Custom applications updated successfully"
        assert result["applications"] == mock_response
        mock_client.update_custom_applications.assert_called_once_with(
            "project123", applications
        )

    @patch("mcp_coroot.server.get_client")
    async def test_get_inspection_config_with_special_app_id(
        self, mock_get_client: Mock
    ) -> None:
        """Test get inspection config with special app ID format."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_response = {"form": {"configs": [{"threshold": 0}]}}
        mock_client.get_inspection_config.return_value = mock_response

        # Test with non-Kubernetes app ID format
        result = await get_inspection_config_impl("project123", "_:Unknown:loki", "CPU")

        assert result["success"] is True
        assert result["config"] == mock_response
        mock_client.get_inspection_config.assert_called_once_with(
            "project123", "_:Unknown:loki", "CPU"
        )

    @patch("mcp_coroot.server.get_client")
    async def test_empty_custom_applications(self, mock_get_client: Mock) -> None:
        """Test get custom applications when none are configured."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_response = {"custom_applications": None}
        mock_client.get_custom_applications.return_value = mock_response

        result = await get_custom_applications_impl("project123")

        assert result["success"] is True
        assert result["applications"] == mock_response
        assert result["applications"]["custom_applications"] is None

    @patch("mcp_coroot.server.get_client")
    async def test_list_inspections_error(self, mock_get_client: Mock) -> None:
        """Test list inspections with error."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_client.list_inspections.side_effect = Exception("API error")

        result = await list_inspections_impl("project123")

        assert result["success"] is False
        assert "Unexpected error" in result["error"]

    @patch("mcp_coroot.server.get_client")
    async def test_update_categories_validation_error(
        self, mock_get_client: Mock
    ) -> None:
        """Test update categories with validation error."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_client.update_application_categories.side_effect = ValueError(
            "Invalid category format"
        )

        result = await update_application_categories_impl("project123", {})

        assert result["success"] is False
        assert result["error"] == "Invalid category format"
