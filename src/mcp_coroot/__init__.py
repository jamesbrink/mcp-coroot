"""MCP server for Coroot observability platform.

This package provides a Model Context Protocol (MCP) server that exposes
Coroot's observability APIs as tools for AI assistants like Claude.

The server enables:
- Application and infrastructure monitoring
- Performance profiling and distributed tracing
- Log analysis and incident management
- System configuration and integrations
- Cost tracking and risk assessment

Quick Start:
    ```bash
    # Install the package
    pip install mcp-coroot

    # Set environment variables
    export COROOT_BASE_URL="http://localhost:8080"
    export COROOT_USERNAME="admin"
    export COROOT_PASSWORD="your-password"

    # Run the server
    mcp-coroot
    ```

For more information, see: https://github.com/jamesbrink/mcp-coroot
"""

from .client import CorootClient, CorootError
from .server import mcp

__version__ = "0.1.0"
__all__ = ["CorootClient", "CorootError", "mcp", "__version__"]
