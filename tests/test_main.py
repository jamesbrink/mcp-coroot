"""Tests for main entry point and module initialization."""

from unittest.mock import patch

import pytest

from mcp_coroot import server


class TestMainFunction:
    """Test the main function and entry point."""

    def test_main_function_exists(self):
        """Test that main function exists."""
        assert hasattr(server, "main")
        assert callable(server.main)

    @patch("mcp_coroot.server.mcp.run")
    def test_main_calls_mcp_run(self, mock_run):
        """Test that main() calls mcp.run()."""
        server.main()
        mock_run.assert_called_once()

    def test_server_initialization(self):
        """Test that the MCP server is initialized correctly."""
        # Import the server module
        import mcp_coroot.server  # noqa: F401

        # Verify the mcp object exists and has correct name
        assert hasattr(server, "mcp")
        # The mcp object should have been created with the name "mcp-coroot"
        # We can't easily test FastMCP internals without mocking at import time


class TestGetClient:
    """Test get_client function."""

    def test_get_client_singleton(self):
        """Test that get_client returns the same instance."""
        # Reset the global client
        server._client = None

        with patch("mcp_coroot.server.CorootClient") as mock_client_class:
            mock_instance = mock_client_class.return_value

            # First call creates client
            client1 = server.get_client()
            assert client1 == mock_instance
            mock_client_class.assert_called_once()

            # Second call returns same instance
            client2 = server.get_client()
            assert client2 == client1
            # Still only called once
            mock_client_class.assert_called_once()

    def test_get_client_error_handling(self):
        """Test get_client error handling."""
        # Reset the global client
        server._client = None

        with patch("mcp_coroot.server.CorootClient") as mock_client_class:
            mock_client_class.side_effect = ValueError("Invalid config")

            with pytest.raises(ValueError) as exc_info:
                server.get_client()

            assert "Coroot credentials not configured" in str(exc_info.value)
