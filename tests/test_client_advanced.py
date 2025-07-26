"""Tests for advanced application client functionality."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from mcp_coroot.client import CorootClient


@pytest.mark.asyncio
class TestAdvancedApplicationFeatures:
    """Test advanced application features in the client."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return CorootClient(
            base_url="http://localhost:8080",
            username="admin",
            password="password",
        )

    async def test_get_application_rca(self, client):
        """Test getting application RCA."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "analysis": {
                    "summary": "High memory usage detected",
                    "root_causes": [
                        {
                            "cause": "Memory leak in cache layer",
                            "confidence": 0.92,
                            "evidence": ["Cache size growing", "No eviction happening"],
                        }
                    ],
                    "recommendations": ["Clear cache", "Implement TTL"],
                },
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.get_application_rca(
                "project123", "namespace/deployment/app"
            )

        assert result["analysis"]["summary"] == "High memory usage detected"
        assert len(result["analysis"]["root_causes"]) == 1
        assert result["analysis"]["root_causes"][0]["confidence"] == 0.92

    async def test_get_application_profiling_with_params(self, client):
        """Test getting application profiling with parameters."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "cpu": {
                    "flame_graph": "svg_data",
                    "top_functions": [{"name": "handler.process", "cpu_percent": 55.0}],
                },
                "memory": {
                    "heap_profile": "profile_data",
                    "allocations": [{"type": "string", "size_mb": 200}],
                },
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch(
            "httpx.AsyncClient.request", return_value=mock_response
        ) as mock_request:
            result = await client.get_application_profiling(
                "project123",
                "namespace/deployment/app",
                from_timestamp=1000,
                to_timestamp=2000,
                query="handler",
            )

            # Check parameters were passed correctly
            call_args = mock_request.call_args
            params = call_args.kwargs["params"]
            assert params["from"] == "1000"
            assert params["to"] == "2000"
            assert params["query"] == "handler"
            assert result["cpu"]["top_functions"][0]["cpu_percent"] == 55.0

    async def test_get_application_profiling_no_params(self, client):
        """Test getting application profiling without parameters."""
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value={"cpu": {}, "memory": {}})
        mock_response.raise_for_status = AsyncMock()

        with patch(
            "httpx.AsyncClient.request", return_value=mock_response
        ) as mock_request:
            result = await client.get_application_profiling(
                "project123", "namespace/deployment/app"
            )

            # Check no params were passed
            call_args = mock_request.call_args
            params = call_args.kwargs.get("params", {})
            assert params == {}
            assert result == {"cpu": {}, "memory": {}}

    async def test_update_application_risks_json_response(self, client):
        """Test updating application risks with JSON response."""
        risks = {
            "cpu_threshold": 85,
            "memory_threshold": 95,
            "error_rate_threshold": 3,
        }
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "app_id": "namespace/deployment/app",
                "risks": risks,
                "updated_at": 1234567890,
            }
        )
        mock_response.raise_for_status = AsyncMock()
        mock_response.headers = {"content-type": "application/json"}

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.update_application_risks(
                "project123", "namespace/deployment/app", risks
            )

        assert result["app_id"] == "namespace/deployment/app"
        assert result["risks"]["cpu_threshold"] == 85

    async def test_update_application_risks_non_json_response(self, client):
        """Test updating application risks with non-JSON response."""
        risks = {"cpu_threshold": 80}
        mock_response = AsyncMock()
        mock_response.headers = {"content-type": "text/plain"}
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.update_application_risks(
                "project123", "namespace/deployment/app", risks
            )

        assert result["app_id"] == "namespace/deployment/app"
        assert result["risks"] == risks
        assert result["status"] == "updated"

    async def test_update_application_risks_json_parse_error(self, client):
        """Test updating application risks with JSON parse error."""
        risks = {"error_threshold": 5}
        mock_response = AsyncMock()
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json = Mock(side_effect=ValueError("Invalid JSON"))
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.update_application_risks(
                "project123", "namespace/deployment/app", risks
            )

        assert result["app_id"] == "namespace/deployment/app"
        assert result["status"] == "updated"

    async def test_get_rca_with_encoded_app_id(self, client):
        """Test RCA with app ID that needs encoding."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={"analysis": {"summary": "No issues found"}}
        )
        mock_response.raise_for_status = AsyncMock()

        with patch(
            "httpx.AsyncClient.request", return_value=mock_response
        ) as mock_request:
            result = await client.get_application_rca(
                "project123", "namespace/kind/app-name"
            )

            # Check URL encoding
            call_args = mock_request.call_args
            url = call_args.args[1]
            assert "namespace%2Fkind%2Fapp-name" in url
            assert result["analysis"]["summary"] == "No issues found"

    async def test_profiling_with_special_app_id(self, client):
        """Test profiling with special app ID format."""
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value={"cpu": {"usage": 0.5}})
        mock_response.raise_for_status = AsyncMock()

        with patch(
            "httpx.AsyncClient.request", return_value=mock_response
        ) as mock_request:
            result = await client.get_application_profiling(
                "project123", "_:Unknown:service"
            )

            # Check URL encoding for special format
            call_args = mock_request.call_args
            url = call_args.args[1]
            assert "_:Unknown:service" not in url  # Should be encoded
            assert result["cpu"]["usage"] == 0.5
