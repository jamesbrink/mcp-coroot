"""Tests for advanced application feature tools."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from mcp_coroot.server import (
    get_application_profiling_impl,
    get_application_rca_impl,
    update_application_risks_impl,
)


@pytest.mark.asyncio
class TestAdvancedApplicationTools:
    """Test advanced application feature tools."""

    @patch("mcp_coroot.server.get_client")
    async def test_get_application_rca_success(self, mock_get_client: Mock) -> None:
        """Test successful RCA retrieval."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_response = {
            "analysis": {
                "summary": "High CPU usage detected",
                "root_causes": [
                    {
                        "cause": "Memory leak in service X",
                        "confidence": 0.85,
                        "evidence": ["Memory usage increasing", "GC pressure high"],
                    }
                ],
                "recommendations": ["Restart service", "Update to version 2.0"],
            },
            "timestamp": 1234567890,
        }
        mock_client.get_application_rca.return_value = mock_response

        result = await get_application_rca_impl(
            "project123", "namespace/deployment/app"
        )

        assert result["success"] is True
        assert result["rca"] == mock_response
        assert result["rca"]["analysis"]["summary"] == "High CPU usage detected"
        mock_client.get_application_rca.assert_called_once_with(
            "project123", "namespace/deployment/app"
        )

    @patch("mcp_coroot.server.get_client")
    async def test_get_application_profiling_success(
        self, mock_get_client: Mock
    ) -> None:
        """Test successful profiling data retrieval."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_response = {
            "cpu": {
                "flame_graph": "data:image/svg+xml;base64,...",
                "top_functions": [
                    {"name": "main.processRequest", "cpu_percent": 45.2},
                    {"name": "db.query", "cpu_percent": 23.1},
                ],
            },
            "memory": {
                "heap_profile": "data:image/svg+xml;base64,...",
                "allocations": [
                    {"type": "[]byte", "size_mb": 124.5},
                    {"type": "map[string]interface{}", "size_mb": 67.3},
                ],
            },
        }
        mock_client.get_application_profiling.return_value = mock_response

        result = await get_application_profiling_impl(
            "project123",
            "namespace/deployment/app",
            from_timestamp=1000,
            to_timestamp=2000,
            query="cpu",
        )

        assert result["success"] is True
        assert result["profiling"] == mock_response
        assert result["profiling"]["cpu"]["top_functions"][0]["cpu_percent"] == 45.2
        mock_client.get_application_profiling.assert_called_once_with(
            "project123", "namespace/deployment/app", 1000, 2000, "cpu"
        )

    @patch("mcp_coroot.server.get_client")
    async def test_get_application_profiling_no_params(
        self, mock_get_client: Mock
    ) -> None:
        """Test profiling retrieval without optional parameters."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_response = {"cpu": {}, "memory": {}}
        mock_client.get_application_profiling.return_value = mock_response

        result = await get_application_profiling_impl(
            "project123", "namespace/deployment/app"
        )

        assert result["success"] is True
        assert result["profiling"] == mock_response
        mock_client.get_application_profiling.assert_called_once_with(
            "project123", "namespace/deployment/app", None, None, None
        )

    @patch("mcp_coroot.server.get_client")
    async def test_update_application_risks_success(
        self, mock_get_client: Mock
    ) -> None:
        """Test successful risk configuration update."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        risks = {
            "cpu_threshold": 80,
            "memory_threshold": 90,
            "error_rate_threshold": 5,
            "latency_threshold_ms": 1000,
            "enabled_checks": ["cpu", "memory", "errors", "latency"],
        }
        mock_response = {
            "app_id": "namespace/deployment/app",
            "risks": risks,
            "status": "updated",
        }
        mock_client.update_application_risks.return_value = mock_response

        result = await update_application_risks_impl(
            "project123", "namespace/deployment/app", risks
        )

        assert result["success"] is True
        assert result["message"] == "Application risks updated successfully"
        assert result["risks"] == mock_response
        mock_client.update_application_risks.assert_called_once_with(
            "project123", "namespace/deployment/app", risks
        )

    @patch("mcp_coroot.server.get_client")
    async def test_get_application_rca_with_special_app_id(
        self, mock_get_client: Mock
    ) -> None:
        """Test RCA with special app ID format."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_response = {
            "analysis": {
                "summary": "No recent issues detected",
                "root_causes": [],
                "recommendations": [],
            }
        }
        mock_client.get_application_rca.return_value = mock_response

        result = await get_application_rca_impl("project123", "_:Unknown:loki")

        assert result["success"] is True
        assert result["rca"] == mock_response
        mock_client.get_application_rca.assert_called_once_with(
            "project123", "_:Unknown:loki"
        )

    @patch("mcp_coroot.server.get_client")
    async def test_get_application_rca_error(self, mock_get_client: Mock) -> None:
        """Test RCA retrieval with error."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_client.get_application_rca.side_effect = Exception(
            "RCA service unavailable"
        )

        result = await get_application_rca_impl(
            "project123", "namespace/deployment/app"
        )

        assert result["success"] is False
        assert "Unexpected error" in result["error"]

    @patch("mcp_coroot.server.get_client")
    async def test_update_risks_validation_error(self, mock_get_client: Mock) -> None:
        """Test risk update with validation error."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_client.update_application_risks.side_effect = ValueError(
            "Invalid threshold values"
        )

        result = await update_application_risks_impl(
            "project123", "namespace/deployment/app", {"invalid": "data"}
        )

        assert result["success"] is False
        assert result["error"] == "Invalid threshold values"

    @patch("mcp_coroot.server.get_client")
    async def test_profiling_with_empty_response(self, mock_get_client: Mock) -> None:
        """Test profiling with empty response."""
        mock_client = AsyncMock()
        mock_get_client.return_value = mock_client

        mock_response = {}
        mock_client.get_application_profiling.return_value = mock_response

        result = await get_application_profiling_impl(
            "project123", "namespace/deployment/app"
        )

        assert result["success"] is True
        assert result["profiling"] == mock_response
        assert result["profiling"] == {}
