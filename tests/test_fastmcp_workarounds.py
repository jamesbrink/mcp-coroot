"""Tests for FastMCP type conversion workarounds."""

from unittest.mock import AsyncMock, Mock, patch

from mcp_coroot.server import configure_profiling_impl, configure_tracing_impl


class TestFastMCPWorkarounds:
    """Test FastMCP type conversion workarounds."""

    @patch("mcp_coroot.server.get_client")
    async def test_configure_profiling_string_conversion(
        self, mock_get_client: Mock
    ) -> None:
        """Test that string sample_rate is converted to float."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client

        mock_response = {"enabled": True, "sample_rate": 0.1}
        mock_client.configure_profiling = AsyncMock(return_value=mock_response)

        # Pass sample_rate as string (simulating FastMCP behavior)
        result = await configure_profiling_impl(
            "project123", "app/deployment", True, "0.1"
        )

        assert result["success"] is True
        assert result["message"] == "Profiling configuration updated successfully"

        # Verify the client was called with float value
        mock_client.configure_profiling.assert_called_once_with(
            "project123", "app/deployment", {"enabled": True, "sample_rate": 0.1}
        )

    @patch("mcp_coroot.server.get_client")
    async def test_configure_profiling_invalid_string(
        self, mock_get_client: Mock
    ) -> None:
        """Test that invalid string sample_rate returns error."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client

        # Pass invalid sample_rate string
        result = await configure_profiling_impl(
            "project123", "app/deployment", True, "not-a-number"
        )

        assert result["success"] is False
        assert "Invalid sample_rate: not-a-number" in result["error"]

        # Verify client was not called
        mock_client.configure_profiling.assert_not_called()

    @patch("mcp_coroot.server.get_client")
    async def test_configure_tracing_string_conversions(
        self, mock_get_client: Mock
    ) -> None:
        """Test that string parameters are converted properly."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client

        mock_response = {
            "enabled": True,
            "sample_rate": 0.05,
            "excluded_paths": ["/health", "/metrics"],
        }
        mock_client.configure_tracing = AsyncMock(return_value=mock_response)

        # Pass parameters as strings (simulating FastMCP behavior)
        result = await configure_tracing_impl(
            "project123",
            "app/deployment",
            True,
            "0.05",  # String sample_rate
            '["/health", "/metrics"]',  # JSON string excluded_paths
        )

        assert result["success"] is True
        assert result["message"] == "Tracing configuration updated successfully"

        # Verify the client was called with proper types
        mock_client.configure_tracing.assert_called_once_with(
            "project123",
            "app/deployment",
            {
                "enabled": True,
                "sample_rate": 0.05,
                "excluded_paths": ["/health", "/metrics"],
            },
        )

    @patch("mcp_coroot.server.get_client")
    async def test_configure_tracing_invalid_json(self, mock_get_client: Mock) -> None:
        """Test that invalid JSON for excluded_paths returns error."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client

        # Pass invalid JSON string
        result = await configure_tracing_impl(
            "project123",
            "app/deployment",
            True,
            None,
            "[invalid json",  # Missing closing bracket
        )

        assert result["success"] is False
        assert "Invalid JSON for excluded_paths" in result["error"]

        # Verify client was not called
        mock_client.configure_tracing.assert_not_called()

    @patch("mcp_coroot.server.get_client")
    async def test_configure_tracing_non_list_json(self, mock_get_client: Mock) -> None:
        """Test that non-list JSON for excluded_paths returns error."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client

        # Pass valid JSON but not a list
        result = await configure_tracing_impl(
            "project123",
            "app/deployment",
            True,
            None,
            '{"not": "a list"}',  # Valid JSON but not a list
        )

        assert result["success"] is False
        assert "excluded_paths must be a list, got dict" in result["error"]

        # Verify client was not called
        mock_client.configure_tracing.assert_not_called()

    @patch("mcp_coroot.server.get_client")
    async def test_configure_profiling_native_float(
        self, mock_get_client: Mock
    ) -> None:
        """Test that native float values still work."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client

        mock_response = {"enabled": True, "sample_rate": 0.2}
        mock_client.configure_profiling = AsyncMock(return_value=mock_response)

        # Pass sample_rate as native float
        result = await configure_profiling_impl(
            "project123", "app/deployment", True, 0.2
        )

        assert result["success"] is True

        # Verify the client was called with float value
        mock_client.configure_profiling.assert_called_once_with(
            "project123", "app/deployment", {"enabled": True, "sample_rate": 0.2}
        )

    @patch("mcp_coroot.server.get_client")
    async def test_configure_tracing_native_types(self, mock_get_client: Mock) -> None:
        """Test that native types still work."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client

        mock_response = {
            "enabled": True,
            "sample_rate": 0.1,
            "excluded_paths": ["/status", "/ping"],
        }
        mock_client.configure_tracing = AsyncMock(return_value=mock_response)

        # Pass parameters as native types
        result = await configure_tracing_impl(
            "project123",
            "app/deployment",
            True,
            0.1,  # Native float
            ["/status", "/ping"],  # Native list
        )

        assert result["success"] is True

        # Verify the client was called with native types
        mock_client.configure_tracing.assert_called_once_with(
            "project123",
            "app/deployment",
            {
                "enabled": True,
                "sample_rate": 0.1,
                "excluded_paths": ["/status", "/ping"],
            },
        )
