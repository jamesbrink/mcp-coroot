"""Tests for authentication error handling."""

from unittest.mock import Mock, patch

import pytest

from mcp_coroot.client import CorootError
from mcp_coroot.server import get_current_user_impl, list_projects_impl


@pytest.mark.asyncio
class TestAuthenticationErrorHandling:
    """Test authentication error handling in server implementation."""

    @patch("mcp_coroot.server.get_client")
    async def test_authentication_failed_error(self, mock_get_client: Mock) -> None:
        """Test handling of authentication failed errors."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client

        # Simulate authentication error
        mock_client.get_current_user.side_effect = CorootError(
            "Authentication failed: Invalid session cookie. "
            "Please check your credentials."
        )

        result = await get_current_user_impl()

        assert result["success"] is False
        assert "Authentication failed" in result["error"]
        assert result["error_type"] == "authentication"

    @patch("mcp_coroot.server.get_client")
    async def test_401_unauthorized_error(self, mock_get_client: Mock) -> None:
        """Test handling of 401 unauthorized errors."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client

        # Simulate 401 error
        mock_client.list_projects.side_effect = CorootError(
            "API request failed: 401 - Unauthorized"
        )

        result = await list_projects_impl()

        assert result["success"] is False
        assert (
            result["error"] == "Authentication required. Please check your credentials."
        )
        assert result["error_type"] == "authentication"

    @patch("mcp_coroot.server.get_client")
    async def test_other_api_error(self, mock_get_client: Mock) -> None:
        """Test handling of other API errors."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client

        # Simulate other API error
        mock_client.get_current_user.side_effect = CorootError(
            "API request failed: 500 - Internal Server Error"
        )

        result = await get_current_user_impl()

        assert result["success"] is False
        assert "500 - Internal Server Error" in result["error"]
        assert result["error_type"] == "api_error"

    @patch("mcp_coroot.server.get_client")
    async def test_validation_error(self, mock_get_client: Mock) -> None:
        """Test handling of validation errors."""
        # Simulate missing credentials
        mock_get_client.side_effect = ValueError(
            "Coroot credentials not configured. Please set COROOT_BASE_URL"
        )

        result = await get_current_user_impl()

        assert result["success"] is False
        assert "credentials not configured" in result["error"]
        assert result["error_type"] == "validation"

    @patch("mcp_coroot.server.get_client")
    async def test_unexpected_error(self, mock_get_client: Mock) -> None:
        """Test handling of unexpected errors."""
        mock_client = Mock()
        mock_get_client.return_value = mock_client

        # Simulate unexpected error
        mock_client.get_current_user.side_effect = RuntimeError("Something went wrong")

        result = await get_current_user_impl()

        assert result["success"] is False
        assert "Unexpected error: Something went wrong" in result["error"]
        assert result["error_type"] == "unknown"
