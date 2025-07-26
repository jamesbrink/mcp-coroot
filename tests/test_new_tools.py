"""Tests for newly added tools."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from mcp_coroot.server import (
    delete_custom_cloud_pricing_impl,
    get_ai_config_impl,
    # Custom Cloud Pricing
    get_custom_cloud_pricing_impl,
    # Database Instrumentation
    get_db_instrumentation_impl,
    # Risk Overview
    get_risks_overview_impl,
    # SSO/AI Configuration
    get_sso_config_impl,
    update_ai_config_impl,
    update_custom_cloud_pricing_impl,
    update_db_instrumentation_impl,
    update_sso_config_impl,
)


@pytest.mark.asyncio
class TestCustomCloudPricing:
    """Test custom cloud pricing tools."""

    @patch("mcp_coroot.server.get_client")
    async def test_get_custom_cloud_pricing_success(
        self, mock_get_client: Mock
    ) -> None:
        """Test successful custom cloud pricing retrieval."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_response = {
            "cpu_hourly_cost": 0.05,
            "memory_gb_hourly_cost": 0.01,
        }
        mock_client.get_custom_cloud_pricing.return_value = mock_response

        result = await get_custom_cloud_pricing_impl("project123")

        assert result["success"] is True
        assert result["pricing"] == mock_response
        mock_client.get_custom_cloud_pricing.assert_called_once_with("project123")

    @patch("mcp_coroot.server.get_client")
    async def test_update_custom_cloud_pricing_success(
        self, mock_get_client: Mock
    ) -> None:
        """Test successful custom cloud pricing update."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        pricing = {"cpu_hourly_cost": 0.06}
        mock_client.update_custom_cloud_pricing.return_value = pricing

        result = await update_custom_cloud_pricing_impl("project123", pricing)

        assert result["success"] is True
        assert result["message"] == "Custom cloud pricing updated successfully"
        mock_client.update_custom_cloud_pricing.assert_called_once_with(
            "project123", pricing
        )

    @patch("mcp_coroot.server.get_client")
    async def test_delete_custom_cloud_pricing_success(
        self, mock_get_client: Mock
    ) -> None:
        """Test successful custom cloud pricing deletion."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_client.delete_custom_cloud_pricing.return_value = {"status": "deleted"}

        result = await delete_custom_cloud_pricing_impl("project123")

        assert result["success"] is True
        assert result["message"] == "Custom cloud pricing deleted successfully"


@pytest.mark.asyncio
class TestSSOAIConfiguration:
    """Test SSO and AI configuration tools."""

    @patch("mcp_coroot.server.get_client")
    async def test_get_sso_config_success(self, mock_get_client: Mock) -> None:
        """Test successful SSO config retrieval."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_response = {
            "enabled": True,
            "provider": "okta",
            "roles": ["Admin", "Editor", "Viewer"],
        }
        mock_client.get_sso_config.return_value = mock_response

        result = await get_sso_config_impl()

        assert result["success"] is True
        assert result["config"] == mock_response

    @patch("mcp_coroot.server.get_client")
    async def test_update_sso_config_success(self, mock_get_client: Mock) -> None:
        """Test successful SSO config update."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        config = {"enabled": True, "provider": "saml"}
        mock_client.update_sso_config.return_value = config

        result = await update_sso_config_impl(config)

        assert result["success"] is True
        assert result["message"] == "SSO configuration updated successfully"

    @patch("mcp_coroot.server.get_client")
    async def test_get_ai_config_success(self, mock_get_client: Mock) -> None:
        """Test successful AI config retrieval."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_response = {
            "provider": "openai",
            "model": "gpt-4",
            "enabled": True,
        }
        mock_client.get_ai_config.return_value = mock_response

        result = await get_ai_config_impl()

        assert result["success"] is True
        assert result["config"] == mock_response

    @patch("mcp_coroot.server.get_client")
    async def test_update_ai_config_success(self, mock_get_client: Mock) -> None:
        """Test successful AI config update."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        config = {"provider": "anthropic", "model": "claude-3"}
        mock_client.update_ai_config.return_value = config

        result = await update_ai_config_impl(config)

        assert result["success"] is True
        assert result["message"] == "AI configuration updated successfully"


@pytest.mark.asyncio
class TestDatabaseInstrumentation:
    """Test database instrumentation tools."""

    @patch("mcp_coroot.server.get_client")
    async def test_get_db_instrumentation_success(self, mock_get_client: Mock) -> None:
        """Test successful DB instrumentation config retrieval."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_response = {
            "enabled": True,
            "sample_rate": 0.1,
            "slow_query_threshold_ms": 100,
        }
        mock_client.get_db_instrumentation.return_value = mock_response

        result = await get_db_instrumentation_impl(
            "project123", "namespace/deployment/app", "mysql"
        )

        assert result["success"] is True
        assert result["config"] == mock_response

    @patch("mcp_coroot.server.get_client")
    async def test_update_db_instrumentation_success(
        self, mock_get_client: Mock
    ) -> None:
        """Test successful DB instrumentation config update."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        config = {"enabled": True, "sample_rate": 0.2}
        mock_client.update_db_instrumentation.return_value = config

        result = await update_db_instrumentation_impl(
            "project123", "namespace/deployment/app", "postgres", config
        )

        assert result["success"] is True
        assert result["message"] == "postgres instrumentation updated successfully"
        assert result["config"] == config


@pytest.mark.asyncio
class TestRiskOverview:
    """Test risk overview tool."""

    @patch("mcp_coroot.server.get_client")
    async def test_get_risks_overview_success(self, mock_get_client: Mock) -> None:
        """Test successful risks overview retrieval."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_response = {
            "high_risk_apps": ["app1", "app2"],
            "total_risks": 5,
            "critical_issues": 2,
        }
        mock_client.get_risks_overview.return_value = mock_response

        result = await get_risks_overview_impl("project123", "critical")

        assert result["success"] is True
        assert result["overview"] == mock_response
        mock_client.get_risks_overview.assert_called_once_with("project123", "critical")


@pytest.mark.asyncio
class TestErrorHandling:
    """Test error handling for new tools."""

    @patch("mcp_coroot.server.get_client")
    async def test_cloud_pricing_error(self, mock_get_client: Mock) -> None:
        """Test cloud pricing error handling."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_client.get_custom_cloud_pricing.side_effect = Exception("API error")

        result = await get_custom_cloud_pricing_impl("project123")

        assert result["success"] is False
        assert "Unexpected error" in result["error"]

    @patch("mcp_coroot.server.get_client")
    async def test_sso_config_validation_error(self, mock_get_client: Mock) -> None:
        """Test SSO config validation error."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_client.update_sso_config.side_effect = ValueError("Invalid provider")

        result = await update_sso_config_impl({"provider": "invalid"})

        assert result["success"] is False
        assert result["error"] == "Invalid provider"
