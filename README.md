# MCP Server for Coroot

[![CI](https://github.com/jamesbrink/mcp-coroot/actions/workflows/ci.yml/badge.svg)](https://github.com/jamesbrink/mcp-coroot/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/jamesbrink/mcp-coroot/branch/main/graph/badge.svg)](https://codecov.io/gh/jamesbrink/mcp-coroot)
[![PyPI version](https://img.shields.io/pypi/v/mcp-coroot.svg)](https://pypi.org/project/mcp-coroot/)
[![Python versions](https://img.shields.io/pypi/pyversions/mcp-coroot.svg)](https://pypi.org/project/mcp-coroot/)

A Model Context Protocol (MCP) server that provides seamless integration with [Coroot](https://coroot.com) observability platform. This server enables MCP clients to monitor applications, analyze performance metrics, examine logs and traces, and manage infrastructure through Coroot's comprehensive API.

## Getting Started

Add this configuration to your MCP client settings:

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

**Using Docker:**
```json
{
  "mcpServers": {
    "coroot": {
      "command": "docker",
      "args": ["run", "--rm", "-i", 
              "-e", "COROOT_BASE_URL=http://localhost:8080",
              "-e", "COROOT_USERNAME=admin",
              "-e", "COROOT_PASSWORD=your-password",
              "jamesbrink/mcp-coroot:latest"]
    }
  }
}
```

**For SSO/MFA users**, use session cookie authentication instead:

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

### Environment Variables

- `COROOT_BASE_URL` - Your Coroot instance URL (required)
- `COROOT_USERNAME` - Username for basic authentication
- `COROOT_PASSWORD` - Password for basic authentication
- `COROOT_SESSION_COOKIE` - Session cookie for SSO/MFA users
- `COROOT_API_KEY` - API key (limited to data ingestion only)

That's it! Your MCP client can now interact with your Coroot instance.

## Features

### Core Capabilities
- **Application Monitoring** - Real-time metrics, health checks, and performance analysis
- **Log Analysis** - Search, filter, and analyze application logs with pattern detection
- **Distributed Tracing** - Trace requests across microservices and identify bottlenecks
- **Infrastructure Overview** - Monitor nodes, containers, and system resources
- **Incident Management** - Track and analyze incidents with root cause analysis
- **Performance Profiling** - CPU and memory profiling with flame graphs

### Management Features
- **Project Management** - Create, configure, and manage Coroot projects
- **Integration Configuration** - Set up Prometheus, Slack, PagerDuty, and more
- **Dashboard Customization** - Create and manage custom dashboards
- **Cost Tracking** - Monitor cloud costs with custom pricing rules
- **User & Access Control** - Manage users, roles, and permissions

### Advanced Features
- **AI-Powered RCA** - Automatic root cause analysis for application issues
- **Risk Assessment** - Identify and track infrastructure and application risks
- **Deployment Tracking** - Monitor deployments and their impact
- **SLO Management** - Configure and track Service Level Objectives
- **Database Instrumentation** - Specialized monitoring for databases

## Installation

### Using uvx (Recommended)
```bash
# Install and run directly
uvx mcp-coroot
```

### Using pip
```bash
pip install mcp-coroot
```

### Using Docker
```bash
docker run --rm -i \
  -e COROOT_BASE_URL="http://localhost:8080" \
  -e COROOT_USERNAME="admin" \
  -e COROOT_PASSWORD="your-password" \
  jamesbrink/mcp-coroot:latest
```

### From Source
```bash
git clone https://github.com/jamesbrink/mcp-coroot.git
cd mcp-coroot
uv sync --all-groups
uv run mcp-coroot
```

## Authentication Methods

### Username/Password
Best for users with basic authentication. The server automatically handles login and session management.

### Session Cookie (SSO/MFA)
Required for organizations using:
- Single Sign-On (SAML, OIDC)
- Multi-Factor Authentication (2FA/MFA)
- Advanced authentication workflows

To get your session cookie:
1. Login to Coroot through your browser
2. Open Developer Tools (F12)
3. Go to Application/Storage → Cookies
4. Copy the value of the `auth` cookie

### API Key
Only supports data ingestion endpoints (`/v1/*`). Cannot be used for management APIs.

## Available Tools

The server provides **61 tools** organized into functional categories:

### 🔐 Authentication & Users (5 tools)
- `get_current_user` - Get authenticated user information
- `update_current_user` - Update user profile
- `list_users` - List all users
- `create_user` - Create new users
- `get_roles` - View roles and permissions

### 📊 Project Management (9 tools)
- `list_projects` - List all accessible projects
- `get_project` - Get project details
- `create_project` - Create new project
- `get_project_status` - Check project health
- `update_project_settings` - Update project configuration
- `delete_project` - Delete project
- `list_api_keys` - View API keys
- `create_api_key` - Generate API keys
- `delete_api_key` - Delete API keys

### 🚀 Application Monitoring (3 tools)
- `get_application` - Comprehensive application metrics
- `get_application_logs` - Search and analyze logs
- `get_application_traces` - View distributed traces

### 🌐 Overview & Analysis (5 tools)
- `get_applications_overview` - All applications summary
- `get_nodes_overview` - Infrastructure overview
- `get_traces_overview` - Tracing summary
- `get_deployments_overview` - Deployment history
- `get_risks_overview` - Risk assessment

### 📈 Dashboard Management (5 tools)
- `list_dashboards` - View dashboards
- `create_dashboard` - Create dashboard
- `get_dashboard` - Get dashboard details
- `update_dashboard` - Update dashboard
- `delete_dashboard` - Remove dashboard

### 🔌 Integrations (4 tools)
- `list_integrations` - View integrations
- `configure_integration` - Configure integration
- `test_integration` - Test connectivity
- `delete_integration` - Remove integration

### ⚙️ Configuration (9 tools)
- `list_inspections` - View inspection types
- `get_inspection_config` - Get inspection settings
- `update_inspection_config` - Update inspections
- `get_application_categories` - View categories
- `create_application_category` - Create new category
- `update_application_category` - Update existing category
- `delete_application_category` - Delete category
- `get_custom_applications` - View custom apps
- `update_custom_applications` - Define custom apps

### 🔍 Advanced Features (15 tools)
Including RCA, profiling, cloud pricing, database instrumentation, SSO/AI configuration, and more.

## Example Usage

### Basic Monitoring
```
"Show me all applications in the production project"
"Check the health status of the API service"
"Are there any critical incidents right now?"
```

### Troubleshooting
```
"Search for error logs in the payment service from the last hour"
"Show me slow database queries"
"Analyze the root cause of high latency in the frontend"
```

### Configuration
```
"Set up Slack notifications for critical alerts"
"Create a dashboard for monitoring Redis performance"
"Configure SLO thresholds for the API service"
```

## Development

### Using Test PyPI Version

To use the pre-release version from Test PyPI:

```json
{
  "mcpServers": {
    "coroot": {
      "command": "uvx",
      "args": [
        "--index-url",
        "https://test.pypi.org/simple/",
        "--extra-index-url",
        "https://pypi.org/simple/",
        "mcp-coroot"
      ],
      "env": {
        "COROOT_BASE_URL": "http://localhost:8080",
        "COROOT_USERNAME": "admin",
        "COROOT_PASSWORD": "your-password"
      }
    }
  }
}
```

Note: The `--extra-index-url` is required because Test PyPI doesn't host all dependencies.

### Testing
```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov

# Run specific tests
uv run pytest tests/test_server.py -v
```

### Code Quality
```bash
# Type checking
uv run mypy src

# Linting
uv run ruff check src tests

# Formatting
uv run ruff format src tests
```

## API Compatibility

This MCP server is compatible with Coroot v1.0+ and implements the full management API surface. For data ingestion endpoints, use the Coroot API directly with your API key.

## Troubleshooting

### Connection Issues
- Verify Coroot is accessible at the configured URL
- Check firewall rules and network connectivity
- Ensure credentials are correct

### Authentication Errors
- Username/password authentication is recommended for automatic login
- Session cookies expire after 7 days of inactivity
- API keys only work for data ingestion, not management APIs

### Large Response Errors
Some endpoints return large datasets. Use time filters:
- `get_application_traces` - Use `from_timestamp` and `to_timestamp`
- `get_application_profiling` - Limit time range to reduce data size

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## License

MIT License - see LICENSE file for details.