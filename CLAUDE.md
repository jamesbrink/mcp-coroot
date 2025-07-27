# Claude Desktop Configuration for MCP Coroot

**IMPORTANT DOCUMENTATION POLICY**: This project maintains only two documentation files:
- `README.md` - Public-facing project documentation
- `CLAUDE.md` - Internal instructions and configuration details
- (Exception: `LICENSE` and `CHANGELOG` files are also allowed)

Please DO NOT create any other markdown documentation files. All documentation should be consolidated into these two files.

**IMPORTANT TESTING STANDARDS**: 
This project follows professional Python testing standards:
- Test files must follow Python naming conventions: `test_*.py`
- Test files should be organized by the module they test (e.g., `test_client.py` for client functionality, `test_server.py` for server functionality)
- DO NOT use unprofessional suffixes like `test_final_*.py`, `test_new_*.py`, `test_all_remaining_*.py`, etc.
- Consolidate related tests into appropriately named test files rather than creating multiple files with incremental names
- All tests must maintain their original functionality when moved between files

---

This file contains instructions for configuring the MCP Coroot server with Claude Desktop.

## Overview

The MCP Coroot server provides 61 tools for interacting with Coroot observability platform:
- Authentication and user management (5 tools)
- Project creation and management (9 tools)
- Application monitoring and troubleshooting (3 tools)
- Infrastructure overview and incidents (2 tools)
- Deployment and system overviews (5 tools)
- Dashboard management (5 tools)
- Integration configuration (4 tools)
- Configuration management (9 tools)
- Advanced troubleshooting (3 tools)
- Custom cloud pricing (3 tools)
- Database instrumentation (2 tools)
- System configuration (4 tools)
- Risk overview (1 tool)
- Health checks (1 tool)
- Panel data and advanced configuration (6 tools)

Test coverage: 87% (197 tests passing)

## Quick Setup

### Using Published Package (Recommended)

Edit your Claude Desktop configuration:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`  
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "coroot": {
      "command": "uvx",
      "args": ["mcp-coroot"],
      "env": {
        "COROOT_BASE_URL": "http://localhost:8080",
        "COROOT_USERNAME": "admin",
        "COROOT_PASSWORD": "your-password"
      }
    }
  }
}
```

### For SSO/MFA Users

If your organization uses SSO or MFA, use session cookie authentication:

```json
{
  "mcpServers": {
    "coroot": {
      "command": "uvx",
      "args": ["mcp-coroot"],
      "env": {
        "COROOT_BASE_URL": "http://localhost:8080",
        "COROOT_SESSION_COOKIE": "your-auth-cookie-value"
      }
    }
  }
}
```

To get your session cookie:
1. Login to Coroot through your browser
2. Open Developer Tools (F12)
3. Go to Application/Storage → Cookies
4. Copy the value of the `auth` cookie

### For Local Development

If you're developing or testing locally:

**macOS**:
```json
{
  "mcpServers": {
    "coroot": {
      "command": "uv",
      "args": ["run", "mcp-coroot"],
      "cwd": "/path/to/mcp-coroot",
      "env": {
        "COROOT_BASE_URL": "http://localhost:8080",
        "COROOT_USERNAME": "admin",
        "COROOT_PASSWORD": "your-password"
      }
    }
  }
}
```

**Windows**:
```json
{
  "mcpServers": {
    "coroot": {
      "command": "uv",
      "args": ["run", "mcp-coroot"],
      "cwd": "C:\\path\\to\\mcp-coroot",
      "env": {
        "COROOT_BASE_URL": "http://localhost:8080",
        "COROOT_USERNAME": "admin",
        "COROOT_PASSWORD": "your-password"
      }
    }
  }
}
```

## Authentication Methods

The server supports three authentication methods:

1. **Username/Password** (Recommended) - Automatic login and session management
2. **Session Cookie** - Required for SSO/MFA environments
3. **API Key** - Limited to data ingestion endpoints only

## Available Commands

Once configured, you can ask Claude to:

### Monitoring & Analysis
- "Show me all Coroot projects"
- "Check the health of all applications in production"
- "Show me error logs for the API service in the last hour"
- "Find slow traces in the payment service"
- "Analyze why the frontend has high latency"
- "Show CPU profiling data for the backend service"

### Infrastructure Management
- "List all nodes in the production project"
- "Show me the resource usage of server01"
- "Check for any incidents in the last 24 hours"
- "Display the deployment history"
- "Show me the risk assessment for our infrastructure"

### Configuration & Integration
- "Set up Slack notifications for critical alerts"
- "Configure Prometheus integration"
- "Update SLO thresholds for the API service"
- "Show me the application categorization rules"
- "Create a new application category for microservices"
- "Update the database category to include new patterns"
- "Delete the test category we no longer need"
- "Create a custom dashboard for Redis monitoring"

### Advanced Features
- "Perform root cause analysis on the payment service failures"
- "Show database instrumentation settings for PostgreSQL"
- "Configure custom cloud pricing for our AWS instances"
- "Update the AI configuration for RCA"
- "List all API keys for the production project"

## Known Limitations

Some Coroot API endpoints have limitations:

### Large Response Warnings
- **Traces**: Can return 100k+ tokens. Use time filters to limit data.
- **Profiling**: Can return 180k+ tokens. Always specify time ranges.

### Empty Response Handling
Some endpoints return empty bodies on success. The MCP server handles these gracefully.

### Not Yet Implemented
- Dashboard CRUD operations (limited functionality)
- RCA feature (returns "not implemented yet")
- Role creation/update (405 Method Not Allowed)

### FastMCP Type Conversion Workaround
Due to a known issue in FastMCP v2.10.6, the following tools have workarounds for parameter type conversion:
- `configure_profiling`: The `sample_rate` parameter accepts strings (e.g., "0.1") and converts to float
- `configure_tracing`: The `sample_rate` accepts strings, and `excluded_paths` accepts JSON strings (e.g., '["/health", "/metrics"]')

This workaround ensures compatibility with MCP clients that pass all parameters as strings. The implementation handles both string and native types transparently.

## Troubleshooting

### Connection Issues
- Verify COROOT_BASE_URL is correct and accessible
- Check if Coroot is running: `curl http://localhost:8080/health`
- Ensure no firewall is blocking the connection

### Authentication Errors
- For basic auth: Verify username and password are correct
- For SSO/MFA: Ensure session cookie is valid and not expired
- Session cookies expire after 7 days of inactivity

### Tool Errors
- "Tool not found": Restart Claude Desktop after configuration changes
- Large responses: Use time filters to reduce data size
- Empty responses: Normal for some operations (deletes, updates)

## Development

To run the server manually for testing:

```bash
# Clone and install
git clone https://github.com/jamesbrink/mcp-coroot.git
cd mcp-coroot
uv sync --all-groups

# Run with environment variables
COROOT_BASE_URL=http://localhost:8080 \
COROOT_USERNAME=admin \
COROOT_PASSWORD=your-password \
uv run mcp-coroot
```

### Running Tests
```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov

# Run specific test
uv run pytest tests/test_server.py -v
```

## Support

For issues or questions:
- GitHub Issues: https://github.com/jamesbrink/mcp-coroot/issues
- Coroot Documentation: https://coroot.com/docs