"""FastMCP server for Coroot observability platform.

This module provides a Model Context Protocol (MCP) server that exposes
Coroot's observability APIs as tools for AI assistants. It enables
monitoring, troubleshooting, and configuration of applications through
natural language interactions.

The server provides 58 tools across various categories:
- Authentication and user management
- Project and application monitoring
- Performance profiling and distributed tracing
- Log analysis and incident management
- Infrastructure configuration and integrations
- Cost tracking and risk assessment

Example:
    To run the server, ensure environment variables are set:

    ```bash
    export COROOT_BASE_URL="http://localhost:8080"
    export COROOT_USERNAME="admin"
    export COROOT_PASSWORD="your-password"
    uv run mcp-coroot
    ```
"""

import json
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar
from urllib.parse import quote

from fastmcp import FastMCP

from .client import CorootClient, CorootError

# Initialize FastMCP server
mcp = FastMCP("mcp-coroot")  # type: ignore[var-annotated]

# Type variable for decorator
T = TypeVar("T")


def handle_errors(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator to handle common errors in tool implementations."""

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return await func(*args, **kwargs)  # type: ignore[no-any-return]
        except ValueError as e:
            # Handle missing credentials or other validation errors
            return {
                "success": False,
                "error": str(e),
                "error_type": "validation",
            }
        except CorootError as e:
            # Handle Coroot API errors (including authentication)
            error_msg = str(e)
            if "Authentication failed" in error_msg:
                return {
                    "success": False,
                    "error": error_msg,
                    "error_type": "authentication",
                }
            elif "401" in error_msg or "Unauthorized" in error_msg:
                return {
                    "success": False,
                    "error": "Authentication required. Please check your credentials.",
                    "error_type": "authentication",
                }
            return {
                "success": False,
                "error": error_msg,
                "error_type": "api_error",
            }
        except Exception as e:
            # Handle unexpected errors
            return {
                "success": False,
                "error": f"Unexpected error: {str(e)}",
                "error_type": "unknown",
            }

    return wrapper


# Client instance (created lazily)
_client: CorootClient | None = None


def get_client() -> CorootClient:
    """Get or create the client instance.

    Raises:
        ValueError: If no credentials are configured.
    """
    global _client
    if _client is None:
        try:
            _client = CorootClient()
        except ValueError as e:
            # Re-raise with more context
            raise ValueError(
                "Coroot credentials not configured. "
                "Please set COROOT_BASE_URL and either:\n"
                "  - COROOT_USERNAME and COROOT_PASSWORD for automatic login\n"
                "  - COROOT_SESSION_COOKIE for direct authentication\n"
                "  - COROOT_API_KEY for data ingestion endpoints"
            ) from e
    return _client


# User Information Tools


@handle_errors
async def get_current_user_impl() -> dict[str, Any]:
    """Get current authenticated user information."""
    user = await get_client().get_current_user()
    return {
        "success": True,
        "user": user,
    }


@mcp.tool()
async def get_current_user() -> dict[str, Any]:
    """Get current authenticated user information.

    Returns information about the currently authenticated user including
    their email, name, roles, and accessible projects.
    """
    return await get_current_user_impl()  # type: ignore[no-any-return]


# Project Management Tools


@handle_errors
async def list_projects_impl() -> dict[str, Any]:
    """List all accessible projects."""
    projects = await get_client().list_projects()
    return {
        "success": True,
        "count": len(projects),
        "projects": projects,
    }


@mcp.tool()
async def list_projects() -> dict[str, Any]:
    """List all accessible projects.

    Returns a list of all projects that the authenticated user has access to.
    Each project includes its ID and name.
    """
    return await list_projects_impl()  # type: ignore[no-any-return]


@handle_errors
async def get_project_impl(project_id: str) -> dict[str, Any]:
    """Get project details."""
    project = await get_client().get_project(project_id)
    return {
        "success": True,
        "project": project,
    }


@mcp.tool()
async def get_project(project_id: str) -> dict[str, Any]:
    """Get project details and configuration.

    Retrieves comprehensive information about a project including
    its settings, integrations, and configuration.

    Args:
        project_id: Project ID
    """
    return await get_project_impl(project_id)  # type: ignore[no-any-return]


@handle_errors
async def create_project_impl(name: str) -> dict[str, Any]:
    """Create a new project."""
    project = await get_client().create_project(name)
    return {
        "success": True,
        "message": "Project created successfully",
        "project": project,
    }


@mcp.tool()
async def create_project(name: str) -> dict[str, Any]:
    """Create a new project.

    Creates a new Coroot project with the specified name.
    The name must contain only lowercase letters, numbers, and hyphens.

    Args:
        name: Project name (must match ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$)
    """
    return await create_project_impl(name)  # type: ignore[no-any-return]


@handle_errors
async def get_project_status_impl(project_id: str) -> dict[str, Any]:
    """Get project status."""
    status = await get_client().get_project_status(project_id)
    return {
        "success": True,
        "status": status,
    }


@mcp.tool()
async def get_project_status(project_id: str) -> dict[str, Any]:
    """Get project status including agent and integration health.

    Returns the current status of a project including:
    - Overall project health
    - Prometheus connection status
    - Node agent deployment status
    - Any error messages

    Args:
        project_id: Project ID
    """
    return await get_project_status_impl(project_id)  # type: ignore[no-any-return]


# Application Monitoring Tools


@handle_errors
async def get_application_impl(
    project_id: str,
    app_id: str,
    from_timestamp: int | None = None,
    to_timestamp: int | None = None,
) -> dict[str, Any]:
    """Get application details and metrics."""
    # URL encode the app_id since it contains slashes
    encoded_app_id = quote(app_id, safe="")

    app = await get_client().get_application(
        project_id, encoded_app_id, from_timestamp, to_timestamp
    )
    return {
        "success": True,
        "application": app,
    }


@mcp.tool()
async def get_application(
    project_id: str,
    app_id: str,
    from_timestamp: int | None = None,
    to_timestamp: int | None = None,
) -> dict[str, Any]:
    """Get application details and metrics.

    Retrieves comprehensive information about an application including:
    - Performance metrics (CPU, memory, network)
    - Health checks and SLOs
    - Recent incidents
    - Deployment history

    Args:
        project_id: Project ID
        app_id: Application ID (format: namespace/kind/name)
        from_timestamp: Start timestamp for metrics (optional)
        to_timestamp: End timestamp for metrics (optional)
    """
    return await get_application_impl(  # type: ignore[no-any-return]
        project_id, app_id, from_timestamp, to_timestamp
    )


@handle_errors
async def get_application_logs_impl(
    project_id: str,
    app_id: str,
    from_timestamp: int | None = None,
    to_timestamp: int | None = None,
    query: str | None = None,
    severity: str | None = None,
) -> dict[str, Any]:
    """Get application logs."""
    # URL encode the app_id since it contains slashes
    encoded_app_id = quote(app_id, safe="")

    logs = await get_client().get_application_logs(
        project_id, encoded_app_id, from_timestamp, to_timestamp, query, severity
    )
    return {
        "success": True,
        "logs": logs,
    }


@mcp.tool()
async def get_application_logs(
    project_id: str,
    app_id: str,
    from_timestamp: int | None = None,
    to_timestamp: int | None = None,
    query: str | None = None,
    severity: str | None = None,
) -> dict[str, Any]:
    """Get application logs with pattern analysis.

    Retrieves application logs with automatic pattern detection
    and grouping. Supports filtering by time range, search query,
    and severity level.

    Args:
        project_id: Project ID
        app_id: Application ID (format: namespace/kind/name)
        from_timestamp: Start timestamp (optional)
        to_timestamp: End timestamp (optional)
        query: Log search query (optional)
        severity: Filter by severity level (optional)
    """
    return await get_application_logs_impl(  # type: ignore[no-any-return]
        project_id, app_id, from_timestamp, to_timestamp, query, severity
    )


@handle_errors
async def get_application_traces_impl(
    project_id: str,
    app_id: str,
    from_timestamp: int | None = None,
    to_timestamp: int | None = None,
    trace_id: str | None = None,
    query: str | None = None,
) -> dict[str, Any]:
    """Get application traces."""
    # URL encode the app_id since it contains slashes
    encoded_app_id = quote(app_id, safe="")

    traces = await get_client().get_application_traces(
        project_id, encoded_app_id, from_timestamp, to_timestamp, trace_id, query
    )
    return {
        "success": True,
        "traces": traces,
    }


@mcp.tool()
async def get_application_traces(
    project_id: str,
    app_id: str,
    from_timestamp: int | None = None,
    to_timestamp: int | None = None,
    trace_id: str | None = None,
    query: str | None = None,
) -> dict[str, Any]:
    """Get distributed traces for an application.

    Retrieves distributed tracing data showing request flow
    through the application and its dependencies.

    ⚠️ WARNING: This endpoint can return very large responses (100k+ tokens)
    when retrieving many traces. Consider using time filters or trace_id
    to limit the response size.

    Args:
        project_id: Project ID
        app_id: Application ID (format: namespace/kind/name)
        from_timestamp: Start timestamp (optional, recommended to limit data)
        to_timestamp: End timestamp (optional, recommended to limit data)
        trace_id: Specific trace ID to retrieve (optional, returns single trace)
        query: Search query (optional)
    """
    return await get_application_traces_impl(  # type: ignore[no-any-return]
        project_id, app_id, from_timestamp, to_timestamp, trace_id, query
    )


# Overview Tools


@handle_errors
async def get_applications_overview_impl(
    project_id: str,
    query: str | None = None,
) -> dict[str, Any]:
    """Get applications overview."""
    overview = await get_client().get_applications_overview(project_id, query)
    return {
        "success": True,
        "overview": overview,
    }


@mcp.tool()
async def get_applications_overview(
    project_id: str,
    query: str | None = None,
) -> dict[str, Any]:
    """Get overview of all applications in a project.

    Returns a high-level view of all applications including:
    - Application health status
    - Key performance indicators
    - Resource usage
    - Recent incidents

    Args:
        project_id: Project ID
        query: Search/filter query (optional)
    """
    return await get_applications_overview_impl(project_id, query)  # type: ignore[no-any-return]


@handle_errors
async def get_nodes_overview_impl(
    project_id: str,
    query: str | None = None,
) -> dict[str, Any]:
    """Get nodes overview."""
    overview = await get_client().get_nodes_overview(project_id, query)
    return {
        "success": True,
        "overview": overview,
    }


@mcp.tool()
async def get_nodes_overview(
    project_id: str,
    query: str | None = None,
) -> dict[str, Any]:
    """Get overview of infrastructure nodes.

    Returns information about all nodes in the infrastructure:
    - Node health and status
    - Resource utilization
    - Running containers
    - System metrics

    Args:
        project_id: Project ID
        query: Search/filter query (optional)
    """
    return await get_nodes_overview_impl(project_id, query)  # type: ignore[no-any-return]


@handle_errors
async def get_traces_overview_impl(
    project_id: str,
    query: str | None = None,
) -> dict[str, Any]:
    """Get traces overview."""
    overview = await get_client().get_traces_overview(project_id, query)
    return {
        "success": True,
        "overview": overview,
    }


@mcp.tool()
async def get_traces_overview(
    project_id: str,
    query: str | None = None,
) -> dict[str, Any]:
    """Get distributed tracing overview.

    Returns a summary of distributed traces across all applications:
    - Trace volume and trends
    - Error rates
    - Latency percentiles
    - Service dependencies

    Args:
        project_id: Project ID
        query: Search/filter query (optional)
    """
    return await get_traces_overview_impl(project_id, query)  # type: ignore[no-any-return]


@handle_errors
async def get_deployments_overview_impl(
    project_id: str,
    query: str | None = None,
) -> dict[str, Any]:
    """Get deployments overview."""
    overview = await get_client().get_deployments_overview(project_id, query)
    return {
        "success": True,
        "overview": overview,
    }


@mcp.tool()
async def get_deployments_overview(
    project_id: str,
    query: str | None = None,
) -> dict[str, Any]:
    """Get deployment tracking overview.

    Returns information about recent deployments:
    - Deployment timeline
    - Success/failure rates
    - Rollback history
    - Impact on application performance

    Args:
        project_id: Project ID
        query: Search/filter query (optional)
    """
    return await get_deployments_overview_impl(project_id, query)  # type: ignore[no-any-return]


@handle_errors
async def get_risks_overview_impl(
    project_id: str,
    query: str | None = None,
) -> dict[str, Any]:
    """Get risks overview."""
    overview = await get_client().get_risks_overview(project_id, query)
    return {
        "success": True,
        "overview": overview,
    }


@mcp.tool()
async def get_risks_overview(
    project_id: str,
    query: str | None = None,
) -> dict[str, Any]:
    """Get risk assessment overview.

    Returns comprehensive risk analysis across all applications:
    - High-risk applications
    - Risk trends over time
    - Critical issues requiring attention
    - Compliance and security risks

    Args:
        project_id: Project ID
        query: Search/filter query (optional)
    """
    return await get_risks_overview_impl(project_id, query)  # type: ignore[no-any-return]


# Integration Tools


@handle_errors
async def list_integrations_impl(project_id: str) -> dict[str, Any]:
    """List all integrations."""
    integrations = await get_client().list_integrations(project_id)
    return {
        "success": True,
        "integrations": integrations,
    }


@mcp.tool()
async def list_integrations(project_id: str) -> dict[str, Any]:
    """List all configured integrations for a project.

    Returns the configuration status of all available integrations:
    - Prometheus
    - ClickHouse
    - AWS
    - Slack
    - Microsoft Teams
    - PagerDuty
    - Opsgenie
    - Webhooks

    Args:
        project_id: Project ID
    """
    return await list_integrations_impl(project_id)  # type: ignore[no-any-return]


@handle_errors
async def configure_integration_impl(
    project_id: str,
    integration_type: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Configure an integration."""
    # Fix webhook configuration to include required templates
    if integration_type == "webhook":
        # Ensure required fields are present
        if "incidents" not in config:
            config["incidents"] = True
        if "deployments" not in config:
            config["deployments"] = False

        # Add default templates if missing
        if config.get("incidents") and "incident_template" not in config:
            config["incident_template"] = (
                "Incident: {{.Title}}\n"
                "Status: {{.Status}}\n"
                "Applications: {{range .Applications}}{{.Id}} {{end}}\n"
                "Link: {{.Link}}"
            )
        if config.get("deployments") and "deployment_template" not in config:
            config["deployment_template"] = (
                "Deployment: {{.Application}}\n"
                "Version: {{.Version}}\n"
                "Status: {{.Status}}"
            )

    result = await get_client().configure_integration(
        project_id, integration_type, config
    )
    return {
        "success": True,
        "message": f"{integration_type} integration configured successfully",
        "integration": result,
    }


@mcp.tool()
async def configure_integration(
    project_id: str,
    integration_type: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Configure an integration for a project.

    Sets up or updates an integration configuration. Each integration
    type has specific configuration requirements.

    Integration types:
    - prometheus: Metrics data source
    - clickhouse: Long-term storage
    - aws: AWS services integration
    - slack: Slack notifications
    - teams: Microsoft Teams notifications
    - pagerduty: PagerDuty alerts
    - opsgenie: Opsgenie alerts
    - webhook: Custom webhooks

    Args:
        project_id: Project ID
        integration_type: Type of integration
        config: Integration-specific configuration dictionary
    """
    return await configure_integration_impl(  # type: ignore[no-any-return]
        project_id, integration_type, config
    )


# Configuration Management Tools


@handle_errors
async def list_inspections_impl(project_id: str) -> dict[str, Any]:
    """List all available inspections."""
    inspections = await get_client().list_inspections(project_id)
    return {
        "success": True,
        "inspections": inspections,
    }


@mcp.tool()
async def list_inspections(project_id: str) -> dict[str, Any]:
    """List all available inspections for a project.

    Returns a list of all inspection types and their configurations
    including CPU, memory, SLO, and other health checks.

    Args:
        project_id: Project ID
    """
    return await list_inspections_impl(project_id)  # type: ignore[no-any-return]


@handle_errors
async def get_inspection_config_impl(
    project_id: str,
    app_id: str,
    inspection_type: str,
) -> dict[str, Any]:
    """Get inspection configuration."""
    config = await get_client().get_inspection_config(
        project_id, app_id, inspection_type
    )
    return {
        "success": True,
        "config": config,
    }


@mcp.tool()
async def get_inspection_config(
    project_id: str,
    app_id: str,
    inspection_type: str,
) -> dict[str, Any]:
    """Get inspection configuration for an application.

    Retrieves the current configuration for a specific inspection type
    (e.g., cpu, memory, slo_availability, slo_latency) for an application.

    Args:
        project_id: Project ID
        app_id: Application ID (format: namespace/kind/name)
        inspection_type: Type of inspection (cpu, memory, slo, etc)
    """
    return await get_inspection_config_impl(  # type: ignore[no-any-return]
        project_id, app_id, inspection_type
    )


@handle_errors
async def update_inspection_config_impl(
    project_id: str,
    app_id: str,
    inspection_type: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Update inspection configuration."""
    result = await get_client().update_inspection_config(
        project_id, app_id, inspection_type, config
    )
    return {
        "success": True,
        "message": f"{inspection_type} inspection configured successfully",
        "config": result,
    }


@mcp.tool()
async def update_inspection_config(
    project_id: str,
    app_id: str,
    inspection_type: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    """Update inspection configuration for an application.

    Updates the configuration for a specific inspection type.
    Configuration format depends on the inspection type.

    Args:
        project_id: Project ID
        app_id: Application ID (format: namespace/kind/name)
        inspection_type: Type of inspection (cpu, memory, slo, etc)
        config: New configuration (format varies by type)
    """
    return await update_inspection_config_impl(  # type: ignore[no-any-return]
        project_id, app_id, inspection_type, config
    )


@handle_errors
async def get_application_categories_impl(project_id: str) -> dict[str, Any]:
    """Get application categories."""
    categories = await get_client().get_application_categories(project_id)
    return {
        "success": True,
        "categories": categories,
    }


@mcp.tool()
async def get_application_categories(project_id: str) -> dict[str, Any]:
    """Get application categories configuration.

    Returns the current application categorization rules that determine
    how applications are grouped (e.g., monitoring, control-plane, etc).

    Args:
        project_id: Project ID
    """
    return await get_application_categories_impl(project_id)  # type: ignore[no-any-return]


@handle_errors
async def create_application_category_impl(
    project_id: str,
    name: str,
    custom_patterns: str,
    notify_incidents: bool = True,
    notify_deployments: bool = False,
    slack_channel: str | None = None,
) -> dict[str, Any]:
    """Create a new application category."""
    category: dict[str, Any] = {
        "name": name,
        "builtin": False,
        "default": False,
        "builtin_patterns": "",
        "custom_patterns": custom_patterns,
        "notification_settings": {
            "incidents": {
                "enabled": notify_incidents,
            },
            "deployments": {
                "enabled": notify_deployments,
            },
        },
    }

    # Add Slack channel if specified
    if slack_channel:
        notifications = category["notification_settings"]
        notifications["incidents"]["slack"] = {
            "enabled": True,
            "channel": slack_channel,
        }
        notifications["deployments"]["slack"] = {
            "enabled": notify_deployments,
            "channel": slack_channel,
        }

    await get_client().create_application_category(project_id, category)
    return {
        "success": True,
        "message": f"Application category '{name}' created successfully",
    }


@mcp.tool()
async def create_application_category(
    project_id: str,
    name: str,
    custom_patterns: str,
    notify_incidents: bool = True,
    notify_deployments: bool = False,
    slack_channel: str | None = None,
) -> dict[str, Any]:
    """Create a new application category.

    Creates a category for grouping applications based on namespace/name patterns.
    Patterns must be space-separated and in format namespace/name
    (e.g., "test/* demo/*").
    Each pattern must contain exactly one '/' and cannot start with '/'.

    Args:
        project_id: Project ID
        name: Category name (lowercase letters, numbers, hyphens,
            underscores; min 3 chars)
        custom_patterns: Space-separated glob patterns (e.g., "test/* demo/*")
        notify_incidents: Whether to notify about incidents (default: True)
        notify_deployments: Whether to notify about deployments (default: False)
        slack_channel: Slack channel for notifications (optional)
    """
    return await create_application_category_impl(  # type: ignore[no-any-return]
        project_id,
        name,
        custom_patterns,
        notify_incidents,
        notify_deployments,
        slack_channel,
    )


@handle_errors
async def update_application_category_impl(
    project_id: str,
    name: str,
    custom_patterns: str | None = None,
    notify_incidents: bool | None = None,
    notify_deployments: bool | None = None,
    slack_channel: str | None = None,
) -> dict[str, Any]:
    """Update an existing application category."""
    # First get the existing category
    categories = await get_client().get_application_categories(project_id)
    existing: dict[str, Any] | None = None
    for cat in categories:
        if isinstance(cat, dict) and cat.get("name") == name:
            existing = cat
            break

    if not existing:
        raise ValueError(f"Category '{name}' not found")

    # Update only specified fields
    if custom_patterns is not None:
        existing["custom_patterns"] = custom_patterns

    if notify_incidents is not None:
        existing["notification_settings"]["incidents"]["enabled"] = notify_incidents

    if notify_deployments is not None:
        existing["notification_settings"]["deployments"]["enabled"] = notify_deployments

    if slack_channel is not None:
        if "slack" not in existing["notification_settings"]["incidents"]:
            existing["notification_settings"]["incidents"]["slack"] = {}
        slack = existing["notification_settings"]["incidents"]["slack"]
        slack["channel"] = slack_channel
        slack["enabled"] = True

        if "slack" not in existing["notification_settings"]["deployments"]:
            existing["notification_settings"]["deployments"]["slack"] = {}
        slack = existing["notification_settings"]["deployments"]["slack"]
        slack["channel"] = slack_channel

    await get_client().update_application_category(project_id, name, existing)
    return {
        "success": True,
        "message": f"Application category '{name}' updated successfully",
    }


@mcp.tool()
async def update_application_category(
    project_id: str,
    name: str,
    custom_patterns: str | None = None,
    notify_incidents: bool | None = None,
    notify_deployments: bool | None = None,
    slack_channel: str | None = None,
) -> dict[str, Any]:
    """Update an existing application category.

    Updates specific fields of an application category.
    Only provided fields are updated.

    Args:
        project_id: Project ID
        name: Category name to update
        custom_patterns: New space-separated glob patterns (optional)
        notify_incidents: Whether to notify about incidents (optional)
        notify_deployments: Whether to notify about deployments (optional)
        slack_channel: Slack channel for notifications (optional)
    """
    return await update_application_category_impl(  # type: ignore[no-any-return]
        project_id,
        name,
        custom_patterns,
        notify_incidents,
        notify_deployments,
        slack_channel,
    )


@handle_errors
async def delete_application_category_impl(
    project_id: str,
    name: str,
) -> dict[str, Any]:
    """Delete an application category."""
    await get_client().delete_application_category(project_id, name)
    return {
        "success": True,
        "message": f"Application category '{name}' deleted successfully",
    }


@mcp.tool()
async def delete_application_category(
    project_id: str,
    name: str,
) -> dict[str, Any]:
    """Delete an application category.

    Removes a custom application category. Built-in categories cannot be deleted.

    Args:
        project_id: Project ID
        name: Category name to delete
    """
    return await delete_application_category_impl(project_id, name)  # type: ignore[no-any-return]


@handle_errors
async def get_custom_applications_impl(project_id: str) -> dict[str, Any]:
    """Get custom applications."""
    applications = await get_client().get_custom_applications(project_id)
    return {
        "success": True,
        "applications": applications,
    }


@mcp.tool()
async def get_custom_applications(project_id: str) -> dict[str, Any]:
    """Get custom applications configuration.

    Returns the list of custom application definitions that group
    instances by patterns.

    Args:
        project_id: Project ID
    """
    return await get_custom_applications_impl(project_id)  # type: ignore[no-any-return]


@handle_errors
async def update_custom_applications_impl(
    project_id: str,
    applications: dict[str, Any],
) -> dict[str, Any]:
    """Update custom applications."""
    result = await get_client().update_custom_applications(project_id, applications)
    return {
        "success": True,
        "message": "Custom applications updated successfully",
        "applications": result,
    }


@mcp.tool()
async def update_custom_applications(
    project_id: str,
    applications: dict[str, Any],
) -> dict[str, Any]:
    """Update custom applications configuration.

    Updates the list of custom application definitions. Custom applications
    allow grouping instances by container name patterns.

    Args:
        project_id: Project ID
        applications: New custom applications list with instance patterns
    """
    return await update_custom_applications_impl(  # type: ignore[no-any-return]
        project_id, applications
    )


# Advanced Application Features


@handle_errors
async def get_application_rca_impl(
    project_id: str,
    app_id: str,
) -> dict[str, Any]:
    """Get root cause analysis for an application."""
    rca = await get_client().get_application_rca(project_id, app_id)
    return {
        "success": True,
        "rca": rca,
    }


@mcp.tool()
async def get_application_rca(
    project_id: str,
    app_id: str,
) -> dict[str, Any]:
    """Get AI-powered root cause analysis for application issues.

    Analyzes application problems and provides insights into the root
    causes of incidents, performance degradation, or failures.

    Args:
        project_id: Project ID
        app_id: Application ID (format: namespace/kind/name)
    """
    return await get_application_rca_impl(project_id, app_id)  # type: ignore[no-any-return]


@handle_errors
async def get_application_profiling_impl(
    project_id: str,
    app_id: str,
    from_timestamp: int | None = None,
    to_timestamp: int | None = None,
    query: str | None = None,
) -> dict[str, Any]:
    """Get profiling data for an application."""
    profiling = await get_client().get_application_profiling(
        project_id, app_id, from_timestamp, to_timestamp, query
    )
    return {
        "success": True,
        "profiling": profiling,
    }


@mcp.tool()
async def get_application_profiling(
    project_id: str,
    app_id: str,
    from_timestamp: int | None = None,
    to_timestamp: int | None = None,
    query: str | None = None,
) -> dict[str, Any]:
    """Get CPU and memory profiling data for an application.

    Retrieves profiling data including flame graphs for CPU usage
    and memory allocation patterns to help identify performance
    bottlenecks and optimization opportunities.

    ⚠️ WARNING: This endpoint can return extremely large responses (180k+ tokens)
    for applications with extensive profiling data. Consider using time filters
    to limit the response size to specific time windows.

    Args:
        project_id: Project ID
        app_id: Application ID (format: namespace/kind/name)
        from_timestamp: Start timestamp (optional, strongly recommended)
        to_timestamp: End timestamp (optional, strongly recommended)
        query: Search query (optional)
    """
    return await get_application_profiling_impl(  # type: ignore[no-any-return]
        project_id, app_id, from_timestamp, to_timestamp, query
    )


@handle_errors
async def update_application_risks_impl(
    project_id: str,
    app_id: str,
    risks: dict[str, Any],
) -> dict[str, Any]:
    """Update application risk assessment."""
    result = await get_client().update_application_risks(project_id, app_id, risks)
    return {
        "success": True,
        "message": "Application risks updated successfully",
        "risks": result,
    }


@mcp.tool()
async def update_application_risks(
    project_id: str,
    app_id: str,
    risks: dict[str, Any],
) -> dict[str, Any]:
    """Update risk assessment configuration for an application.

    Configures risk thresholds and monitoring parameters to better
    identify potential issues before they impact users.

    Args:
        project_id: Project ID
        app_id: Application ID (format: namespace/kind/name)
        risks: Risk assessment configuration
    """
    return await update_application_risks_impl(  # type: ignore[no-any-return]
        project_id, app_id, risks
    )


# Database Instrumentation


@handle_errors
async def get_db_instrumentation_impl(
    project_id: str, app_id: str, db_type: str
) -> dict[str, Any]:
    """Get database instrumentation config."""
    client = get_client()
    config = await client.get_db_instrumentation(project_id, app_id, db_type)
    return {
        "success": True,
        "config": config,
    }


@mcp.tool()
async def get_db_instrumentation(
    project_id: str, app_id: str, db_type: str
) -> dict[str, Any]:
    """Get database instrumentation configuration.

    Retrieves instrumentation settings for a specific database type.

    Args:
        project_id: Project ID
        app_id: Application ID (format: namespace/kind/name)
        db_type: Database type (mysql, postgres, redis, mongodb, memcached)
    """
    return await get_db_instrumentation_impl(project_id, app_id, db_type)  # type: ignore[no-any-return]


@handle_errors
async def update_db_instrumentation_impl(
    project_id: str, app_id: str, db_type: str, config: dict[str, Any]
) -> dict[str, Any]:
    """Update database instrumentation config."""
    client = get_client()
    result = await client.update_db_instrumentation(project_id, app_id, db_type, config)
    return {
        "success": True,
        "message": f"{db_type} instrumentation updated successfully",
        "config": result,
    }


@mcp.tool()
async def update_db_instrumentation(
    project_id: str, app_id: str, db_type: str, config: dict[str, Any]
) -> dict[str, Any]:
    """Update database instrumentation configuration.

    Configures how Coroot instruments and monitors a specific database.

    Args:
        project_id: Project ID
        app_id: Application ID (format: namespace/kind/name)
        db_type: Database type (mysql, postgres, redis, mongodb, memcached)
        config: Instrumentation configuration
    """
    return await update_db_instrumentation_impl(  # type: ignore[no-any-return]
        project_id, app_id, db_type, config
    )


# Node & Incident Management


@handle_errors
async def get_node_impl(project_id: str, node_id: str) -> dict[str, Any]:
    """Get node details."""
    node = await get_client().get_node(project_id, node_id)
    return {
        "success": True,
        "node": node,
    }


@mcp.tool()
async def get_node(project_id: str, node_id: str) -> dict[str, Any]:
    """Get detailed information about a specific infrastructure node.

    Retrieves comprehensive metrics and information about a node including:
    - Resource usage (CPU, memory, disk, network)
    - Running containers
    - System information
    - Health status

    Args:
        project_id: Project ID
        node_id: Node ID
    """
    return await get_node_impl(project_id, node_id)  # type: ignore[no-any-return]


@handle_errors
async def get_incident_impl(project_id: str, incident_id: str) -> dict[str, Any]:
    """Get incident details."""
    incident = await get_client().get_incident(project_id, incident_id)
    return {
        "success": True,
        "incident": incident,
    }


@mcp.tool()
async def get_incident(project_id: str, incident_id: str) -> dict[str, Any]:
    """Get detailed information about a specific incident.

    Retrieves comprehensive incident information including:
    - Timeline of events
    - Affected applications
    - Impact assessment
    - Resolution status

    Args:
        project_id: Project ID
        incident_id: Incident ID
    """
    return await get_incident_impl(project_id, incident_id)  # type: ignore[no-any-return]


# Dashboard Management


@handle_errors
async def list_dashboards_impl(project_id: str) -> dict[str, Any]:
    """List all dashboards."""
    dashboards = await get_client().list_dashboards(project_id)
    return {
        "success": True,
        "dashboards": dashboards,
    }


@mcp.tool()
async def list_dashboards(project_id: str) -> dict[str, Any]:
    """List all custom dashboards for a project.

    Returns all user-created dashboards with their configurations.

    Args:
        project_id: Project ID
    """
    return await list_dashboards_impl(project_id)  # type: ignore[no-any-return]


@handle_errors
async def create_dashboard_impl(
    project_id: str, dashboard: dict[str, Any]
) -> dict[str, Any]:
    """Create a new dashboard."""
    result = await get_client().create_dashboard(project_id, dashboard)
    return {
        "success": True,
        "message": "Dashboard created successfully",
        "dashboard": result,
    }


@mcp.tool()
async def create_dashboard(
    project_id: str, dashboard: dict[str, Any]
) -> dict[str, Any]:
    """Create a new custom dashboard.

    Creates a dashboard with custom panels and queries for monitoring
    specific aspects of your infrastructure.

    Args:
        project_id: Project ID
        dashboard: Dashboard configuration with panels and layout
    """
    return await create_dashboard_impl(project_id, dashboard)  # type: ignore[no-any-return]


@handle_errors
async def get_dashboard_impl(project_id: str, dashboard_id: str) -> dict[str, Any]:
    """Get dashboard details."""
    dashboard = await get_client().get_dashboard(project_id, dashboard_id)
    return {
        "success": True,
        "dashboard": dashboard,
    }


@mcp.tool()
async def get_dashboard(project_id: str, dashboard_id: str) -> dict[str, Any]:
    """Get a specific dashboard configuration.

    Retrieves the full configuration of a dashboard including all panels.

    Args:
        project_id: Project ID
        dashboard_id: Dashboard ID
    """
    return await get_dashboard_impl(project_id, dashboard_id)  # type: ignore[no-any-return]


@handle_errors
async def update_dashboard_impl(
    project_id: str, dashboard_id: str, dashboard: dict[str, Any]
) -> dict[str, Any]:
    """Update a dashboard."""
    result = await get_client().update_dashboard(project_id, dashboard_id, dashboard)
    return {
        "success": True,
        "message": "Dashboard updated successfully",
        "dashboard": result,
    }


@mcp.tool()
async def update_dashboard(
    project_id: str, dashboard_id: str, dashboard: dict[str, Any]
) -> dict[str, Any]:
    """Update an existing dashboard configuration.

    Updates dashboard panels, layout, or other settings.

    Args:
        project_id: Project ID
        dashboard_id: Dashboard ID
        dashboard: Updated dashboard configuration
    """
    return await update_dashboard_impl(  # type: ignore[no-any-return]
        project_id, dashboard_id, dashboard
    )


@handle_errors
async def delete_dashboard_impl(project_id: str, dashboard_id: str) -> dict[str, Any]:
    """Delete a dashboard."""
    client = get_client()
    result = await client.delete_dashboard(project_id, dashboard_id)
    return {
        "success": True,
        "message": "Dashboard deleted successfully",
        "result": result,
    }


@mcp.tool()
async def delete_dashboard(project_id: str, dashboard_id: str) -> dict[str, Any]:
    """Delete a custom dashboard.

    Permanently removes a dashboard from the project.

    Args:
        project_id: Project ID
        dashboard_id: Dashboard ID
    """
    return await delete_dashboard_impl(project_id, dashboard_id)  # type: ignore[no-any-return]


# Integration Management


@handle_errors
async def test_integration_impl(
    project_id: str, integration_type: str
) -> dict[str, Any]:
    """Test an integration."""
    result = await get_client().test_integration(project_id, integration_type)
    return {
        "success": True,
        "message": f"{integration_type} integration test completed",
        "result": result,
    }


@mcp.tool()
async def test_integration(project_id: str, integration_type: str) -> dict[str, Any]:
    """Test an integration configuration.

    Verifies that an integration is properly configured and can connect.

    Args:
        project_id: Project ID
        integration_type: Type of integration (prometheus, slack, etc)
    """
    return await test_integration_impl(project_id, integration_type)  # type: ignore[no-any-return]


@handle_errors
async def delete_integration_impl(
    project_id: str, integration_type: str
) -> dict[str, Any]:
    """Delete an integration."""
    result = await get_client().delete_integration(project_id, integration_type)
    return {
        "success": True,
        "message": f"{integration_type} integration deleted successfully",
        "result": result,
    }


@mcp.tool()
async def delete_integration(project_id: str, integration_type: str) -> dict[str, Any]:
    """Delete an integration configuration.

    Removes an integration from the project.

    Args:
        project_id: Project ID
        integration_type: Type of integration to delete
    """
    return await delete_integration_impl(project_id, integration_type)  # type: ignore[no-any-return]


# Advanced Project Management


@handle_errors
async def update_project_settings_impl(
    project_id: str, settings: dict[str, Any]
) -> dict[str, Any]:
    """Update project settings."""
    result = await get_client().update_project(project_id, settings)
    return {
        "success": True,
        "message": "Project settings updated successfully",
        "project": result,
    }


@mcp.tool()
async def update_project_settings(
    project_id: str, settings: dict[str, Any]
) -> dict[str, Any]:
    """Update project settings and configuration.

    Updates project-level settings such as retention, alerting, etc.

    Args:
        project_id: Project ID
        settings: Updated project settings
    """
    return await update_project_settings_impl(project_id, settings)  # type: ignore[no-any-return]


@handle_errors
async def delete_project_impl(project_id: str) -> dict[str, Any]:
    """Delete a project."""
    result = await get_client().delete_project(project_id)
    return {
        "success": True,
        "message": f"Project {project_id} deleted successfully",
        "result": result,
    }


@mcp.tool()
async def delete_project(project_id: str) -> dict[str, Any]:
    """Delete a project and all associated data.

    WARNING: This action is irreversible and will delete all project data.

    Args:
        project_id: Project ID
    """
    return await delete_project_impl(project_id)  # type: ignore[no-any-return]


@handle_errors
async def list_api_keys_impl(project_id: str) -> dict[str, Any]:
    """List API keys."""
    keys = await get_client().list_api_keys(project_id)
    return {
        "success": True,
        "api_keys": keys,
    }


@mcp.tool()
async def list_api_keys(project_id: str) -> dict[str, Any]:
    """List all API keys for a project.

    Returns all API keys with their metadata (but not the secret values).

    Args:
        project_id: Project ID
    """
    return await list_api_keys_impl(project_id)  # type: ignore[no-any-return]


@handle_errors
async def create_api_key_impl(
    project_id: str, name: str, description: str | None = None
) -> dict[str, Any]:
    """Create an API key."""
    result = await get_client().create_api_key(project_id, name, description)
    return {
        "success": True,
        "message": "API key created successfully",
        "api_key": result,
    }


@mcp.tool()
async def create_api_key(
    project_id: str, name: str, description: str | None = None
) -> dict[str, Any]:
    """Create a new API key for data ingestion.

    Creates an API key that can be used for sending metrics and data.
    The key secret is only returned once during creation.

    Args:
        project_id: Project ID
        name: API key name
        description: Optional description
    """
    return await create_api_key_impl(project_id, name, description)  # type: ignore[no-any-return]


@handle_errors
async def delete_api_key_impl(project_id: str, key: str) -> dict[str, Any]:
    """Delete an API key."""
    await get_client().delete_api_key(project_id, key)
    return {
        "success": True,
        "message": "API key deleted successfully",
    }


@mcp.tool()
async def delete_api_key(project_id: str, key: str) -> dict[str, Any]:
    """Delete an API key.

    Removes an API key from the project. This action cannot be undone.

    Args:
        project_id: Project ID
        key: The API key to delete (the actual key string)
    """
    return await delete_api_key_impl(project_id, key)  # type: ignore[no-any-return]


# User & Role Management


@handle_errors
async def update_current_user_impl(user_data: dict[str, Any]) -> dict[str, Any]:
    """Update current user."""
    result = await get_client().update_current_user(user_data)
    return {
        "success": True,
        "message": "User updated successfully",
        "user": result,
    }


@mcp.tool()
async def update_current_user(user_data: dict[str, Any]) -> dict[str, Any]:
    """Update current user information.

    Updates the profile of the currently authenticated user.

    Args:
        user_data: Updated user information
    """
    return await update_current_user_impl(user_data)  # type: ignore[no-any-return]


@handle_errors
async def list_users_impl() -> dict[str, Any]:
    """List all users."""
    users = await get_client().list_users()
    return {
        "success": True,
        "users": users,
    }


@mcp.tool()
async def list_users() -> dict[str, Any]:
    """List all users in the system (admin only).

    Returns all users with their roles and permissions.
    Requires admin privileges.
    """
    return await list_users_impl()  # type: ignore[no-any-return]


@handle_errors
async def create_user_impl(user_data: dict[str, Any]) -> dict[str, Any]:
    """Create a new user."""
    result = await get_client().create_user(user_data)
    return {
        "success": True,
        "message": "User created successfully",
        "user": result,
    }


@mcp.tool()
async def create_user(user_data: dict[str, Any]) -> dict[str, Any]:
    """Create a new user (admin only).

    Creates a new user account with specified role and permissions.
    Requires admin privileges.

    Args:
        user_data: New user information including email, name, role
    """
    return await create_user_impl(user_data)  # type: ignore[no-any-return]


@handle_errors
async def get_roles_impl() -> dict[str, Any]:
    """Get available roles."""
    roles = await get_client().get_roles()
    return {
        "success": True,
        "roles": roles,
    }


@mcp.tool()
async def get_roles() -> dict[str, Any]:
    """Get available user roles.

    Returns all available roles that can be assigned to users
    (e.g., Viewer, Editor, Admin).
    """
    return await get_roles_impl()  # type: ignore[no-any-return]


# Custom Cloud Pricing


@handle_errors
async def get_custom_cloud_pricing_impl(project_id: str) -> dict[str, Any]:
    """Get custom cloud pricing."""
    client = get_client()
    pricing = await client.get_custom_cloud_pricing(project_id)
    return {
        "success": True,
        "pricing": pricing,
    }


@mcp.tool()
async def get_custom_cloud_pricing(project_id: str) -> dict[str, Any]:
    """Get custom cloud pricing configuration.

    Retrieves any custom cloud pricing overrides for cost calculations.

    Args:
        project_id: Project ID
    """
    return await get_custom_cloud_pricing_impl(project_id)  # type: ignore[no-any-return]


@handle_errors
async def update_custom_cloud_pricing_impl(
    project_id: str, pricing: dict[str, Any]
) -> dict[str, Any]:
    """Update custom cloud pricing."""
    client = get_client()
    result = await client.update_custom_cloud_pricing(project_id, pricing)
    return {
        "success": True,
        "message": "Custom cloud pricing updated successfully",
        "pricing": result,
    }


@mcp.tool()
async def update_custom_cloud_pricing(
    project_id: str, pricing: dict[str, Any]
) -> dict[str, Any]:
    """Update custom cloud pricing configuration.

    Sets custom pricing for cloud resources to override default pricing.

    Args:
        project_id: Project ID
        pricing: Custom pricing configuration
    """
    return await update_custom_cloud_pricing_impl(project_id, pricing)  # type: ignore[no-any-return]


@handle_errors
async def delete_custom_cloud_pricing_impl(project_id: str) -> dict[str, Any]:
    """Delete custom cloud pricing."""
    client = get_client()
    result = await client.delete_custom_cloud_pricing(project_id)
    return {
        "success": True,
        "message": "Custom cloud pricing deleted successfully",
        "result": result,
    }


@mcp.tool()
async def delete_custom_cloud_pricing(project_id: str) -> dict[str, Any]:
    """Delete custom cloud pricing configuration.

    Removes custom pricing overrides and reverts to default pricing.

    Args:
        project_id: Project ID
    """
    return await delete_custom_cloud_pricing_impl(project_id)  # type: ignore[no-any-return]


# Health Check Tool


@handle_errors
async def health_check_impl() -> dict[str, Any]:
    """Check Coroot server health."""
    is_healthy = await get_client().health_check()
    return {
        "success": True,
        "healthy": is_healthy,
        "message": "Coroot server is healthy"
        if is_healthy
        else "Coroot server is not responding",
    }


@mcp.tool()
async def health_check() -> dict[str, Any]:
    """Check if Coroot server is healthy.

    Performs a simple health check to verify that the Coroot
    server is running and accessible.
    """
    return await health_check_impl()  # type: ignore[no-any-return]


# SSO Configuration


@handle_errors
async def get_sso_config_impl() -> dict[str, Any]:
    """Get SSO configuration."""
    client = get_client()
    config = await client.get_sso_config()
    return {
        "success": True,
        "config": config,
    }


@mcp.tool()
async def get_sso_config() -> dict[str, Any]:
    """Get SSO configuration.

    Retrieves Single Sign-On (SSO) configuration and available roles.
    """
    return await get_sso_config_impl()  # type: ignore[no-any-return]


@handle_errors
async def update_sso_config_impl(config: dict[str, Any]) -> dict[str, Any]:
    """Update SSO configuration."""
    client = get_client()
    result = await client.update_sso_config(config)
    return {
        "success": True,
        "message": "SSO configuration updated successfully",
        "config": result,
    }


@mcp.tool()
async def update_sso_config(config: dict[str, Any]) -> dict[str, Any]:
    """Update SSO configuration.

    Configures Single Sign-On settings for the Coroot instance.

    Args:
        config: SSO configuration settings
    """
    return await update_sso_config_impl(config)  # type: ignore[no-any-return]


# AI Configuration


@handle_errors
async def get_ai_config_impl() -> dict[str, Any]:
    """Get AI configuration."""
    client = get_client()
    config = await client.get_ai_config()
    return {
        "success": True,
        "config": config,
    }


@mcp.tool()
async def get_ai_config() -> dict[str, Any]:
    """Get AI provider configuration.

    Retrieves AI provider settings used for root cause analysis.
    """
    return await get_ai_config_impl()  # type: ignore[no-any-return]


@handle_errors
async def update_ai_config_impl(config: dict[str, Any]) -> dict[str, Any]:
    """Update AI configuration."""
    client = get_client()
    result = await client.update_ai_config(config)
    return {
        "success": True,
        "message": "AI configuration updated successfully",
        "config": result,
    }


@mcp.tool()
async def update_ai_config(config: dict[str, Any]) -> dict[str, Any]:
    """Update AI provider configuration.

    Configures AI provider settings for enhanced root cause analysis.

    Args:
        config: AI provider settings (API keys, model selection, etc.)
    """
    return await update_ai_config_impl(config)  # type: ignore[no-any-return]


# Panel Data Tool


async def get_panel_data_impl(
    project_id: str,
    dashboard_id: str,
    panel_id: str,
    from_time: str | None = None,
    to_time: str | None = None,
) -> dict[str, Any]:
    """Implementation for get_panel_data tool."""
    try:
        client = get_client()
        params = {}
        if from_time:
            params["from"] = from_time
        if to_time:
            params["to"] = to_time
        data = await client.get_panel_data(project_id, dashboard_id, panel_id, params)
        return {"success": True, "data": data}
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Unexpected error: {str(e)}"}


@mcp.tool()
async def get_panel_data(
    project_id: str,
    dashboard_id: str,
    panel_id: str,
    from_time: str | None = None,
    to_time: str | None = None,
) -> dict[str, Any]:
    """
    Get data for a specific dashboard panel.

    Retrieves the data that powers a specific panel in a custom dashboard,
    including metrics, time series data, or aggregated values.

    Args:
        project_id: The project ID
        dashboard_id: The dashboard ID
        panel_id: The panel ID within the dashboard
        from_time: Optional start time (ISO format or relative like '-1h')
        to_time: Optional end time (ISO format or 'now')
    """
    return await get_panel_data_impl(
        project_id, dashboard_id, panel_id, from_time, to_time
    )


# Individual Integration Tool


async def get_integration_impl(
    project_id: str, integration_type: str
) -> dict[str, Any]:
    """Implementation for get_integration tool."""
    try:
        client = get_client()
        config = await client.get_integration(project_id, integration_type)
        return {"success": True, "config": config}
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Unexpected error: {str(e)}"}


@mcp.tool()
async def get_integration(project_id: str, integration_type: str) -> dict[str, Any]:
    """
    Get specific integration configuration details.

    Retrieves the current configuration for a specific integration type,
    including connection details, settings, and status.

    Args:
        project_id: The project ID
        integration_type: Type of integration (prometheus, cloudwatch, etc.)
    """
    return await get_integration_impl(project_id, integration_type)


# Advanced Configuration Tools


async def configure_profiling_impl(
    project_id: str, app_id: str, enabled: bool, sample_rate: Any = None
) -> dict[str, Any]:
    """Implementation for configure_profiling tool."""
    try:
        client = get_client()
        config = {"enabled": enabled}

        # Handle FastMCP type conversion issue
        if sample_rate is not None:
            if isinstance(sample_rate, str):
                try:
                    sample_rate = float(sample_rate)
                except ValueError:
                    return {
                        "success": False,
                        "error": f"Invalid sample_rate: {sample_rate}",
                    }
            config["sample_rate"] = sample_rate

        result = await client.configure_profiling(project_id, app_id, config)
        return {
            "success": True,
            "message": "Profiling configuration updated successfully",
            "config": result,
        }
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Unexpected error: {str(e)}"}


@mcp.tool()
async def configure_profiling(
    project_id: str, app_id: str, enabled: bool, sample_rate: Any = None
) -> dict[str, Any]:
    """
    Configure CPU and memory profiling for an application.

    Enables or disables continuous profiling and sets the sampling rate
    for collecting CPU and memory profiles.

    Args:
        project_id: The project ID
        app_id: The application ID
        enabled: Whether to enable profiling
        sample_rate: Optional sampling rate (0.0-1.0)
    """
    return await configure_profiling_impl(project_id, app_id, enabled, sample_rate)


async def configure_tracing_impl(
    project_id: str,
    app_id: str,
    enabled: bool,
    sample_rate: Any = None,
    excluded_paths: Any = None,
) -> dict[str, Any]:
    """Implementation for configure_tracing tool."""
    try:
        client = get_client()
        config = {"enabled": enabled}

        # Handle FastMCP type conversion issue for sample_rate
        if sample_rate is not None:
            if isinstance(sample_rate, str):
                try:
                    sample_rate = float(sample_rate)
                except ValueError:
                    return {
                        "success": False,
                        "error": f"Invalid sample_rate: {sample_rate}",
                    }
            config["sample_rate"] = sample_rate

        # Handle FastMCP type conversion issue for excluded_paths
        if excluded_paths:
            if isinstance(excluded_paths, str):
                try:
                    excluded_paths = json.loads(excluded_paths)
                    if not isinstance(excluded_paths, list):
                        return {
                            "success": False,
                            "error": (
                                f"excluded_paths must be a list, "
                                f"got {type(excluded_paths).__name__}"
                            ),
                        }
                except json.JSONDecodeError:
                    return {
                        "success": False,
                        "error": f"Invalid JSON for excluded_paths: {excluded_paths}",
                    }
            config["excluded_paths"] = excluded_paths

        result = await client.configure_tracing(project_id, app_id, config)
        return {
            "success": True,
            "message": "Tracing configuration updated successfully",
            "config": result,
        }
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Unexpected error: {str(e)}"}


@mcp.tool()
async def configure_tracing(
    project_id: str,
    app_id: str,
    enabled: bool,
    sample_rate: Any = None,
    excluded_paths: Any = None,
) -> dict[str, Any]:
    """
    Configure distributed tracing for an application.

    Controls trace collection settings including sampling rate and
    paths to exclude from tracing.

    Args:
        project_id: The project ID
        app_id: The application ID
        enabled: Whether to enable tracing
        sample_rate: Optional trace sampling rate (0.0-1.0)
        excluded_paths: Optional list of URL paths to exclude
    """
    return await configure_tracing_impl(
        project_id, app_id, enabled, sample_rate, excluded_paths
    )


async def configure_logs_impl(
    project_id: str,
    app_id: str,
    enabled: bool,
    level: str | None = None,
    excluded_patterns: list[str] | None = None,
) -> dict[str, Any]:
    """Implementation for configure_logs tool."""
    try:
        client = get_client()
        config: dict[str, Any] = {"enabled": enabled}
        if level:
            config["level"] = level
        if excluded_patterns:
            config["excluded_patterns"] = excluded_patterns
        result = await client.configure_logs(project_id, app_id, config)
        return {
            "success": True,
            "message": "Log collection configuration updated successfully",
            "config": result,
        }
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Unexpected error: {str(e)}"}


@mcp.tool()
async def configure_logs(
    project_id: str,
    app_id: str,
    enabled: bool,
    level: str | None = None,
    excluded_patterns: list[str] | None = None,
) -> dict[str, Any]:
    """
    Configure log collection settings for an application.

    Controls which logs are collected and processed, including
    log level filtering and pattern exclusions.

    Args:
        project_id: The project ID
        app_id: The application ID
        enabled: Whether to enable log collection
        level: Optional minimum log level (debug, info, warn, error)
        excluded_patterns: Optional regex patterns to exclude
    """
    return await configure_logs_impl(
        project_id, app_id, enabled, level, excluded_patterns
    )


# Role Management Tool


async def create_or_update_role_impl(
    name: str, permissions: list[str], description: str | None = None
) -> dict[str, Any]:
    """Implementation for create_or_update_role tool."""
    try:
        client = get_client()
        role_data = {"name": name, "permissions": permissions}
        if description:
            role_data["description"] = description
        result = await client.create_or_update_role(role_data)
        return {
            "success": True,
            "message": "Role created/updated successfully",
            "role": result,
        }
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Unexpected error: {str(e)}"}


@mcp.tool()
async def create_or_update_role(
    name: str, permissions: list[str], description: str | None = None
) -> dict[str, Any]:
    """
    Create or update a user role (admin only).

    Defines custom roles with specific permissions for fine-grained
    access control.

    Args:
        name: Role name
        permissions: List of permission strings
        description: Optional role description
    """
    return await create_or_update_role_impl(name, permissions, description)


def main() -> None:
    """Run the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
