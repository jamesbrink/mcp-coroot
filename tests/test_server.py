"""Tests for the Coroot MCP server and all tool implementations."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from mcp_coroot.client import CorootError
from mcp_coroot.server import (
    configure_integration_impl,
    configure_logs_impl,
    # Advanced Configuration
    configure_profiling_impl,
    configure_tracing_impl,
    create_api_key_impl,
    create_application_category_impl,
    create_dashboard_impl,
    create_or_update_role_impl,
    create_project_impl,
    create_user_impl,
    delete_api_key_impl,
    delete_application_category_impl,
    delete_custom_cloud_pricing_impl,
    delete_integration_impl,
    delete_project_impl,
    get_ai_config_impl,
    get_application_categories_impl,
    # Application Monitoring
    get_application_impl,
    get_application_logs_impl,
    get_application_profiling_impl,
    get_application_rca_impl,
    get_application_traces_impl,
    # Overview Tools
    get_applications_overview_impl,
    # User Management
    get_current_user_impl,
    get_custom_applications_impl,
    # Custom Cloud Pricing
    get_custom_cloud_pricing_impl,
    get_dashboard_impl,
    # Database Instrumentation
    get_db_instrumentation_impl,
    get_deployments_overview_impl,
    get_incident_impl,
    get_inspection_config_impl,
    get_integration_impl,
    # Node & Incident Management
    get_node_impl,
    get_nodes_overview_impl,
    # Panel Data
    get_panel_data_impl,
    get_project_impl,
    get_project_status_impl,
    get_risks_overview_impl,
    get_roles_impl,
    # SSO/AI Configuration
    get_sso_config_impl,
    get_traces_overview_impl,
    # Health Check
    health_check_impl,
    # API Key Management
    list_api_keys_impl,
    # Dashboard Management
    list_dashboards_impl,
    # Configuration Management
    list_inspections_impl,
    # Integration Management
    list_integrations_impl,
    # Project Management
    list_projects_impl,
    list_users_impl,
    update_ai_config_impl,
    update_application_category_impl,
    update_application_risks_impl,
    update_current_user_impl,
    update_custom_applications_impl,
    update_custom_cloud_pricing_impl,
    update_dashboard_impl,
    update_db_instrumentation_impl,
    update_inspection_config_impl,
    update_project_settings_impl,
    update_sso_config_impl,
)
from mcp_coroot.server import (
    test_integration_impl as check_integration_impl,
)

# ============================================================================
# User Management Tests
# ============================================================================


class TestUserTools:
    """Test user-related tools."""

    @pytest.mark.asyncio
    async def test_get_current_user_success(self, mock_user):
        """Test successful get current user."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_current_user.return_value = mock_user
            mock_get_client.return_value = mock_client

            result = await get_current_user_impl()

            assert result["success"] is True
            assert result["user"] == mock_user

    @pytest.mark.asyncio
    async def test_get_current_user_error(self):
        """Test get current user with error."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_current_user.side_effect = CorootError("Auth error")
            mock_get_client.return_value = mock_client

            result = await get_current_user_impl()

            assert result["success"] is False
            assert "Auth error" in result["error"]

    @pytest.mark.asyncio
    async def test_update_current_user_success(self):
        """Test successful current user update."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            user_data = {"name": "John Doe", "email": "john@example.com"}
            mock_response = {"id": "user1", **user_data}
            mock_client.update_current_user.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await update_current_user_impl(user_data)

            assert result["success"] is True
            assert result["message"] == "User updated successfully"
            assert result["user"] == mock_response

    @pytest.mark.asyncio
    async def test_list_users_success(self):
        """Test successful user listing."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_response = {
                "users": [
                    {"id": "user1", "email": "admin@example.com", "role": "Admin"},
                    {"id": "user2", "email": "viewer@example.com", "role": "Viewer"},
                ]
            }
            mock_client.list_users.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await list_users_impl()

            assert result["success"] is True
            assert result["users"] == mock_response

    @pytest.mark.asyncio
    async def test_create_user_success(self):
        """Test successful user creation."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            user_data = {
                "email": "newuser@example.com",
                "name": "New User",
                "role": "Editor",
            }
            mock_response = {"id": "user3", **user_data}
            mock_client.create_user.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await create_user_impl(user_data)

            assert result["success"] is True
            assert result["message"] == "User created successfully"
            assert result["user"] == mock_response

    @pytest.mark.asyncio
    async def test_get_roles_success(self):
        """Test successful role retrieval."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_response = {
                "roles": [
                    {"name": "Admin", "permissions": ["all"]},
                    {"name": "Editor", "permissions": ["read", "write"]},
                    {"name": "Viewer", "permissions": ["read"]},
                ]
            }
            mock_client.get_roles.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await get_roles_impl()

            assert result["success"] is True
            assert result["roles"] == mock_response

    @pytest.mark.asyncio
    async def test_create_or_update_role_success(self):
        """Test successful role creation/update."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = Mock()
            mock_get_client.return_value = mock_client

            mock_response = {
                "name": "CustomRole",
                "permissions": ["read", "write"],
                "description": "Custom role for testing",
            }
            mock_client.create_or_update_role = AsyncMock(return_value=mock_response)

            result = await create_or_update_role_impl(
                "CustomRole", ["read", "write"], "Custom role for testing"
            )

            assert result["success"] is True
            assert result["message"] == "Role created/updated successfully"
            assert result["role"] == mock_response


# ============================================================================
# Project Management Tests
# ============================================================================


class TestProjectTools:
    """Test project management tools."""

    @pytest.mark.asyncio
    async def test_list_projects_success(self, mock_projects):
        """Test successful project listing."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.list_projects.return_value = mock_projects
            mock_get_client.return_value = mock_client

            result = await list_projects_impl()

            assert result["success"] is True
            assert result["count"] == 2
            assert result["projects"] == mock_projects

    @pytest.mark.asyncio
    async def test_get_project_success(self):
        """Test successful project retrieval."""
        project_data = {"id": "project1", "name": "Project 1", "settings": {}}
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_project.return_value = project_data
            mock_get_client.return_value = mock_client

            result = await get_project_impl("project1")

            assert result["success"] is True
            assert result["project"] == project_data

    @pytest.mark.asyncio
    async def test_create_project_success(self):
        """Test successful project creation."""
        new_project = {"id": "new-project", "name": "new-project"}
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.create_project.return_value = new_project
            mock_get_client.return_value = mock_client

            result = await create_project_impl("new-project")

            assert result["success"] is True
            assert result["message"] == "Project created successfully"
            assert result["project"] == new_project

    @pytest.mark.asyncio
    async def test_get_project_status_success(self):
        """Test successful project status retrieval."""
        status_data = {"status": "healthy", "prometheus": {"connected": True}}
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_project_status.return_value = status_data
            mock_get_client.return_value = mock_client

            result = await get_project_status_impl("project1")

            assert result["success"] is True
            assert result["status"] == status_data

    @pytest.mark.asyncio
    async def test_update_project_settings_success(self):
        """Test successful project settings update."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            settings = {"retention": "90d", "alerting": {"enabled": True}}
            mock_response = {"id": "project123", "settings": settings}
            mock_client.update_project.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await update_project_settings_impl("project123", settings)

            assert result["success"] is True
            assert result["message"] == "Project settings updated successfully"
            assert result["project"] == mock_response

    @pytest.mark.asyncio
    async def test_delete_project_success(self):
        """Test successful project deletion."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_response = {"status": "deleted"}
            mock_client.delete_project.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await delete_project_impl("project123")

            assert result["success"] is True
            assert result["message"] == "Project project123 deleted successfully"
            assert result["result"] == mock_response


# ============================================================================
# Application Monitoring Tests
# ============================================================================


class TestApplicationTools:
    """Test application monitoring tools."""

    @pytest.mark.asyncio
    async def test_get_application_success(self, mock_application):
        """Test successful application retrieval."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_application.return_value = mock_application
            mock_get_client.return_value = mock_client

            result = await get_application_impl(
                "project1", "default/deployment/frontend"
            )

            assert result["success"] is True
            assert result["application"] == mock_application

            # Verify URL encoding was applied
            mock_client.get_application.assert_called_once_with(
                "project1",
                "default%2Fdeployment%2Ffrontend",
                None,
                None,
            )

    @pytest.mark.asyncio
    async def test_get_application_with_timestamps(self, mock_application):
        """Test getting application with timestamp parameters."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_application.return_value = mock_application
            mock_get_client.return_value = mock_client

            result = await get_application_impl(
                "project1", "app1", from_timestamp=1000, to_timestamp=2000
            )

            assert result["success"] is True
            mock_client.get_application.assert_called_once_with(
                "project1", "app1", 1000, 2000
            )

    @pytest.mark.asyncio
    async def test_get_application_logs_success(self):
        """Test successful application logs retrieval."""
        logs_data = {"logs": [{"message": "Error", "severity": "error"}]}
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_application_logs.return_value = logs_data
            mock_get_client.return_value = mock_client

            result = await get_application_logs_impl(
                "project1",
                "app1",
                from_timestamp=1000,
                to_timestamp=2000,
                query="error",
                severity="error",
            )

            assert result["success"] is True
            assert result["logs"] == logs_data

            # Verify URL encoding was applied
            mock_client.get_application_logs.assert_called_once_with(
                "project1", "app1", 1000, 2000, "error", "error"
            )

    @pytest.mark.asyncio
    async def test_get_application_traces_success(self):
        """Test successful application traces retrieval."""
        traces_data = {"traces": [{"trace_id": "abc123", "duration": 150}]}
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_application_traces.return_value = traces_data
            mock_get_client.return_value = mock_client

            result = await get_application_traces_impl(
                "project1",
                "app1",
                from_timestamp=1000,
                to_timestamp=2000,
                trace_id="abc123",
                query="slow",
            )

            assert result["success"] is True
            assert result["traces"] == traces_data

    @pytest.mark.asyncio
    async def test_get_application_rca_success(self):
        """Test successful RCA retrieval."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
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
            mock_get_client.return_value = mock_client

            result = await get_application_rca_impl(
                "project123", "namespace/deployment/app"
            )

            assert result["success"] is True
            assert result["rca"] == mock_response

    @pytest.mark.asyncio
    async def test_get_application_profiling_success(self):
        """Test successful profiling data retrieval."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
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
            mock_get_client.return_value = mock_client

            result = await get_application_profiling_impl(
                "project123",
                "namespace/deployment/app",
                from_timestamp=1000,
                to_timestamp=2000,
                query="cpu",
            )

            assert result["success"] is True
            assert result["profiling"] == mock_response

    @pytest.mark.asyncio
    async def test_update_application_risks_success(self):
        """Test successful risk configuration update."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
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
            mock_get_client.return_value = mock_client

            result = await update_application_risks_impl(
                "project123", "namespace/deployment/app", risks
            )

            assert result["success"] is True
            assert result["message"] == "Application risks updated successfully"
            assert result["risks"] == mock_response


# ============================================================================
# Overview Tools Tests
# ============================================================================


class TestOverviewTools:
    """Test overview tools."""

    @pytest.mark.asyncio
    async def test_get_applications_overview_success(self):
        """Test successful applications overview."""
        overview_data = {"applications": [{"name": "app1", "status": "healthy"}]}
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_applications_overview.return_value = overview_data
            mock_get_client.return_value = mock_client

            result = await get_applications_overview_impl("project1", query="app")

            assert result["success"] is True
            assert result["overview"] == overview_data

    @pytest.mark.asyncio
    async def test_get_nodes_overview_success(self):
        """Test successful nodes overview."""
        nodes_data = {"nodes": [{"name": "node1", "cpu": 0.5}]}
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_nodes_overview.return_value = nodes_data
            mock_get_client.return_value = mock_client

            result = await get_nodes_overview_impl("project1")

            assert result["success"] is True
            assert result["overview"] == nodes_data

    @pytest.mark.asyncio
    async def test_get_traces_overview_success(self):
        """Test successful traces overview."""
        traces_data = {"total_traces": 1000, "error_rate": 0.02}
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_traces_overview.return_value = traces_data
            mock_get_client.return_value = mock_client

            result = await get_traces_overview_impl("project1")

            assert result["success"] is True
            assert result["overview"] == traces_data

    @pytest.mark.asyncio
    async def test_get_deployments_overview_success(self):
        """Test successful deployments overview."""
        deployments_data = {"deployments": [{"app": "app1", "version": "v1.2.3"}]}
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_deployments_overview.return_value = deployments_data
            mock_get_client.return_value = mock_client

            result = await get_deployments_overview_impl("project1")

            assert result["success"] is True
            assert result["overview"] == deployments_data

    @pytest.mark.asyncio
    async def test_get_risks_overview_success(self):
        """Test successful risks overview retrieval."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_response = {
                "high_risk_apps": ["app1", "app2"],
                "total_risks": 5,
                "critical_issues": 2,
            }
            mock_client.get_risks_overview.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await get_risks_overview_impl("project123", "critical")

            assert result["success"] is True
            assert result["overview"] == mock_response


# ============================================================================
# Integration Management Tests
# ============================================================================


class TestIntegrationTools:
    """Test integration management tools."""

    @pytest.mark.asyncio
    async def test_list_integrations_success(self):
        """Test successful integrations listing."""
        integrations_data = {"prometheus": {"configured": True}}
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.list_integrations.return_value = integrations_data
            mock_get_client.return_value = mock_client

            result = await list_integrations_impl("project1")

            assert result["success"] is True
            assert result["integrations"] == integrations_data

    @pytest.mark.asyncio
    async def test_configure_integration_success(self):
        """Test successful integration configuration."""
        config_result = {"status": "configured"}
        config = {"webhook_url": "https://example.com"}
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.configure_integration.return_value = config_result
            mock_get_client.return_value = mock_client

            result = await configure_integration_impl("project1", "webhook", config)

            assert result["success"] is True
            assert result["message"] == "webhook integration configured successfully"
            assert result["integration"] == config_result

    @pytest.mark.asyncio
    async def test_get_integration_success(self):
        """Test successful integration config retrieval."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = Mock()
            mock_get_client.return_value = mock_client

            mock_response = {
                "type": "prometheus",
                "url": "http://prometheus:9090",
                "enabled": True,
            }
            mock_client.get_integration = AsyncMock(return_value=mock_response)

            result = await get_integration_impl("project123", "prometheus")

            assert result["success"] is True
            assert result["config"] == mock_response

    @pytest.mark.asyncio
    async def test_test_integration_success(self):
        """Test successful integration test."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_response = {"status": "success", "message": "Connection successful"}
            mock_client.test_integration.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await check_integration_impl("project123", "prometheus")

            assert result["success"] is True
            assert result["message"] == "prometheus integration test completed"
            assert result["result"] == mock_response

    @pytest.mark.asyncio
    async def test_delete_integration_success(self):
        """Test successful integration deletion."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_response = {"status": "deleted"}
            mock_client.delete_integration.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await delete_integration_impl("project123", "slack")

            assert result["success"] is True
            assert result["message"] == "slack integration deleted successfully"
            assert result["result"] == mock_response


# ============================================================================
# Configuration Management Tests
# ============================================================================


class TestConfigurationTools:
    """Test configuration management tools."""

    @pytest.mark.asyncio
    async def test_list_inspections_success(self):
        """Test successful list inspections."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_response = {
                "checks": [
                    {
                        "id": "SLOAvailability",
                        "title": "SLO / Availability",
                        "status": "unknown",
                        "threshold": 0,
                        "unit": "percent",
                    },
                    {
                        "id": "SLOLatency",
                        "title": "SLO / Latency",
                        "status": "unknown",
                        "threshold": 0,
                        "unit": "seconds",
                    },
                ]
            }
            mock_client.list_inspections.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await list_inspections_impl("project123")

            assert result["success"] is True
            assert result["inspections"] == mock_response

    @pytest.mark.asyncio
    async def test_get_inspection_config_success(self):
        """Test successful get inspection config."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_response = {
                "form": {
                    "configs": [
                        {
                            "custom": False,
                            "total_requests_query": "",
                            "failed_requests_query": "",
                            "objective_percentage": 99,
                        }
                    ],
                    "default": True,
                },
                "integrations": [{"name": "Pagerduty", "details": ""}],
            }
            mock_client.get_inspection_config.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await get_inspection_config_impl(
                "project123", "namespace/deployment/app1", "SLOAvailability"
            )

            assert result["success"] is True
            assert result["config"] == mock_response

    @pytest.mark.asyncio
    async def test_update_inspection_config_success(self):
        """Test successful update inspection config."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            config = {
                "form": {
                    "configs": [
                        {
                            "custom": False,
                            "objective_percentage": 95,
                        }
                    ],
                    "default": False,
                }
            }
            mock_response = config
            mock_client.update_inspection_config.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await update_inspection_config_impl(
                "project123", "namespace/deployment/app1", "SLOAvailability", config
            )

            assert result["success"] is True
            assert (
                result["message"]
                == "SLOAvailability inspection configured successfully"
            )
            assert result["config"] == mock_response

    @pytest.mark.asyncio
    async def test_get_application_categories_success(self):
        """Test successful get application categories."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_response = [
                {
                    "name": "application",
                    "builtin": True,
                    "default": True,
                    "builtin_patterns": "",
                    "custom_patterns": "",
                    "notification_settings": {
                        "incidents": {"enabled": True, "pagerduty": {"enabled": True}},
                        "deployments": {"enabled": False},
                    },
                },
                {
                    "name": "control-plane",
                    "builtin": True,
                    "default": False,
                    "builtin_patterns": "kube-system/*",
                    "custom_patterns": "",
                },
            ]
            mock_client.get_application_categories.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await get_application_categories_impl("project123")

            assert result["success"] is True
            assert result["categories"] == mock_response

    @pytest.mark.asyncio
    async def test_create_application_category_impl(self):
        """Test create_application_category_impl functionality."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.create_application_category.return_value = {"status": "success"}
            mock_get_client.return_value = mock_client

            result = await create_application_category_impl(
                "project123",
                "test-category",
                "test/* qa/*",
                True,
                False,
                "#test-alerts",
            )

            assert result["success"] is True
            assert "created successfully" in result["message"]

            # Check that create_application_category was called with correct args
            mock_client.create_application_category.assert_called_once()
            call_args = mock_client.create_application_category.call_args
            assert call_args[0][0] == "project123"

            # Check the category dict structure
            category = call_args[0][1]
            assert category["name"] == "test-category"
            assert category["custom_patterns"] == "test/* qa/*"
            assert category["notification_settings"]["incidents"]["enabled"] is True
            assert category["notification_settings"]["deployments"]["enabled"] is False
            assert (
                category["notification_settings"]["incidents"]["slack"]["channel"]
                == "#test-alerts"
            )
            assert (
                category["notification_settings"]["deployments"]["slack"]["channel"]
                == "#test-alerts"
            )

    @pytest.mark.asyncio
    async def test_update_application_category_impl(self):
        """Test update_application_category_impl functionality."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            # Mock getting existing categories
            mock_client.get_application_categories.return_value = [
                {
                    "name": "test-category",
                    "custom_patterns": "test/*",
                    "notification_settings": {
                        "incidents": {"enabled": False},
                        "deployments": {"enabled": False},
                    },
                }
            ]
            mock_client.update_application_category.return_value = {"status": "success"}
            mock_get_client.return_value = mock_client

            result = await update_application_category_impl(
                "project123",
                "test-category",
                "test/* updated/*",
                True,
                None,  # Don't update deployments
                "#new-channel",
            )

            assert result["success"] is True
            assert "updated successfully" in result["message"]

            # Verify it called get_application_categories to fetch existing
            mock_client.get_application_categories.assert_called_once_with("project123")

            # Verify update was called with merged data
            mock_client.update_application_category.assert_called_once()
            call_args = mock_client.update_application_category.call_args
            assert call_args[0][0] == "project123"
            assert call_args[0][1] == "test-category"

            # Check the updated category structure
            updated_cat = call_args[0][2]
            assert updated_cat["custom_patterns"] == "test/* updated/*"
            assert updated_cat["notification_settings"]["incidents"]["enabled"] is True
            assert (
                updated_cat["notification_settings"]["deployments"]["enabled"] is False
            )  # Unchanged

            # Check slack channel was updated
            if "slack" in updated_cat["notification_settings"]["incidents"]:
                assert (
                    updated_cat["notification_settings"]["incidents"]["slack"][
                        "channel"
                    ]
                    == "#new-channel"
                )

    @pytest.mark.asyncio
    async def test_update_application_category_not_found(self):
        """Test update_application_category_impl with non-existent category."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            # Return empty list - category not found
            mock_client.get_application_categories.return_value = []
            mock_get_client.return_value = mock_client

            result = await update_application_category_impl(
                "project123", "non-existent", "test/*"
            )

            assert result["success"] is False
            assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_delete_application_category_impl(self):
        """Test delete_application_category_impl functionality."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.delete_application_category.return_value = {"status": "success"}
            mock_get_client.return_value = mock_client

            result = await delete_application_category_impl(
                "project123", "test-category"
            )

            assert result["success"] is True
            assert "deleted successfully" in result["message"]
            mock_client.delete_application_category.assert_called_once_with(
                "project123", "test-category"
            )

    @pytest.mark.asyncio
    async def test_get_custom_applications_success(self):
        """Test successful get custom applications."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_response = {
                "custom_applications": [
                    {
                        "name": "my-app",
                        "instance_patterns": ["container_name:my-app-*"],
                    }
                ]
            }
            mock_client.get_custom_applications.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await get_custom_applications_impl("project123")

            assert result["success"] is True
            assert result["applications"] == mock_response

    @pytest.mark.asyncio
    async def test_update_custom_applications_success(self):
        """Test successful update custom applications."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            applications = {
                "custom_applications": [
                    {
                        "name": "new-app",
                        "instance_patterns": ["container_name:new-app-*"],
                    }
                ]
            }
            mock_response = applications
            mock_client.update_custom_applications.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await update_custom_applications_impl("project123", applications)

            assert result["success"] is True
            assert result["message"] == "Custom applications updated successfully"
            assert result["applications"] == mock_response


# ============================================================================
# Advanced Configuration Tests
# ============================================================================


class TestAdvancedConfiguration:
    """Test advanced configuration tools."""

    @pytest.mark.asyncio
    async def test_configure_profiling_success(self):
        """Test successful profiling configuration."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = Mock()
            mock_get_client.return_value = mock_client

            mock_response = {"enabled": True, "sample_rate": 0.1}
            mock_client.configure_profiling = AsyncMock(return_value=mock_response)

            result = await configure_profiling_impl(
                "project123", "app/deployment", True, 0.1
            )

            assert result["success"] is True
            assert result["message"] == "Profiling configuration updated successfully"
            assert result["config"] == mock_response

    @pytest.mark.asyncio
    async def test_configure_tracing_success(self):
        """Test successful tracing configuration."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = Mock()
            mock_get_client.return_value = mock_client

            mock_response = {
                "enabled": True,
                "sample_rate": 0.05,
                "excluded_paths": ["/health", "/metrics"],
            }
            mock_client.configure_tracing = AsyncMock(return_value=mock_response)

            result = await configure_tracing_impl(
                "project123", "app/deployment", True, 0.05, ["/health", "/metrics"]
            )

            assert result["success"] is True
            assert result["message"] == "Tracing configuration updated successfully"
            assert result["config"] == mock_response

    @pytest.mark.asyncio
    async def test_configure_logs_success(self):
        """Test successful log configuration."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = Mock()
            mock_get_client.return_value = mock_client

            mock_response = {
                "enabled": True,
                "level": "warn",
                "excluded_patterns": [".*debug.*", ".*trace.*"],
            }
            mock_client.configure_logs = AsyncMock(return_value=mock_response)

            result = await configure_logs_impl(
                "project123", "app/deployment", True, "warn", [".*debug.*", ".*trace.*"]
            )

            assert result["success"] is True
            assert (
                result["message"] == "Log collection configuration updated successfully"
            )
            assert result["config"] == mock_response


# ============================================================================
# Node & Incident Management Tests
# ============================================================================


class TestNodeIncidentManagement:
    """Test node and incident management tools."""

    @pytest.mark.asyncio
    async def test_get_node_success(self):
        """Test successful node retrieval."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_response = {
                "id": "node1",
                "name": "worker-1",
                "cpu": {"usage": 0.45, "cores": 8},
                "memory": {"usage": 0.67, "total_gb": 32},
                "containers": [{"name": "app1", "status": "running"}],
            }
            mock_client.get_node.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await get_node_impl("project123", "node1")

            assert result["success"] is True
            assert result["node"] == mock_response

    @pytest.mark.asyncio
    async def test_get_incident_success(self):
        """Test successful incident retrieval."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_response = {
                "id": "incident1",
                "title": "High CPU usage",
                "severity": "critical",
                "status": "resolved",
                "timeline": [{"event": "started", "timestamp": 1234567890}],
            }
            mock_client.get_incident.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await get_incident_impl("project123", "incident1")

            assert result["success"] is True
            assert result["incident"] == mock_response


# ============================================================================
# Dashboard Management Tests
# ============================================================================


class TestDashboardManagement:
    """Test dashboard management tools."""

    @pytest.mark.asyncio
    async def test_list_dashboards_success(self):
        """Test successful dashboard listing."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_response = {
                "dashboards": [
                    {"id": "dash1", "name": "Service Overview"},
                    {"id": "dash2", "name": "Performance Metrics"},
                ]
            }
            mock_client.list_dashboards.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await list_dashboards_impl("project123")

            assert result["success"] is True
            assert result["dashboards"] == mock_response

    @pytest.mark.asyncio
    async def test_create_dashboard_success(self):
        """Test successful dashboard creation."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            dashboard = {
                "name": "New Dashboard",
                "panels": [{"type": "graph", "query": "cpu_usage"}],
            }
            mock_response = {"id": "dash3", **dashboard}
            mock_client.create_dashboard.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await create_dashboard_impl("project123", dashboard)

            assert result["success"] is True
            assert result["message"] == "Dashboard created successfully"
            assert result["dashboard"] == mock_response

    @pytest.mark.asyncio
    async def test_get_dashboard_success(self):
        """Test successful dashboard retrieval."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_response = {
                "id": "dash1",
                "name": "Service Overview",
                "panels": [{"type": "graph", "query": "service_latency"}],
            }
            mock_client.get_dashboard.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await get_dashboard_impl("project123", "dash1")

            assert result["success"] is True
            assert result["dashboard"] == mock_response

    @pytest.mark.asyncio
    async def test_update_dashboard_success(self):
        """Test successful dashboard update."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            dashboard = {"name": "Updated Dashboard", "panels": []}
            mock_response = {"id": "dash1", **dashboard}
            mock_client.update_dashboard.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await update_dashboard_impl("project123", "dash1", dashboard)

            assert result["success"] is True
            assert result["message"] == "Dashboard updated successfully"
            assert result["dashboard"] == mock_response


# ============================================================================
# API Key Management Tests
# ============================================================================


class TestAPIKeyManagement:
    """Test API key management tools."""

    @pytest.mark.asyncio
    async def test_list_api_keys_success(self):
        """Test successful API key listing."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_response = {
                "keys": [
                    {
                        "id": "key1",
                        "name": "Metrics Ingestion",
                        "created_at": 1234567890,
                    },
                    {"id": "key2", "name": "Backup Agent", "created_at": 1234567891},
                ]
            }
            mock_client.list_api_keys.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await list_api_keys_impl("project123")

            assert result["success"] is True
            assert result["api_keys"] == mock_response

    @pytest.mark.asyncio
    async def test_create_api_key_success(self):
        """Test successful API key creation."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_response = {
                "id": "key3",
                "name": "New Key",
                "secret": "sk_live_abcd1234",
                "created_at": 1234567892,
            }
            mock_client.create_api_key.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await create_api_key_impl("project123", "New Key", "Test key")

            assert result["success"] is True
            assert result["message"] == "API key created successfully"
            assert result["api_key"] == mock_response

    @pytest.mark.asyncio
    async def test_delete_api_key_success(self):
        """Test successful API key deletion."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            # Mock successful deletion (no return value)
            mock_client.delete_api_key.return_value = None
            mock_get_client.return_value = mock_client

            result = await delete_api_key_impl(
                "project123", "EMUHGTklu-miwJKD5IjO2Z4OSyO8Vrzn"
            )

            assert result["success"] is True
            assert result["message"] == "API key deleted successfully"


# ============================================================================
# Custom Cloud Pricing Tests
# ============================================================================


class TestCustomCloudPricing:
    """Test custom cloud pricing tools."""

    @pytest.mark.asyncio
    async def test_get_custom_cloud_pricing_success(self):
        """Test successful custom cloud pricing retrieval."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_response = {
                "cpu_hourly_cost": 0.05,
                "memory_gb_hourly_cost": 0.01,
            }
            mock_client.get_custom_cloud_pricing.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await get_custom_cloud_pricing_impl("project123")

            assert result["success"] is True
            assert result["pricing"] == mock_response

    @pytest.mark.asyncio
    async def test_update_custom_cloud_pricing_success(self):
        """Test successful custom cloud pricing update."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            pricing = {"cpu_hourly_cost": 0.06}
            mock_client.update_custom_cloud_pricing.return_value = pricing
            mock_get_client.return_value = mock_client

            result = await update_custom_cloud_pricing_impl("project123", pricing)

            assert result["success"] is True
            assert result["message"] == "Custom cloud pricing updated successfully"

    @pytest.mark.asyncio
    async def test_delete_custom_cloud_pricing_success(self):
        """Test successful custom cloud pricing deletion."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.delete_custom_cloud_pricing.return_value = {"status": "deleted"}
            mock_get_client.return_value = mock_client

            result = await delete_custom_cloud_pricing_impl("project123")

            assert result["success"] is True
            assert result["message"] == "Custom cloud pricing deleted successfully"


# ============================================================================
# SSO/AI Configuration Tests
# ============================================================================


class TestSSOAIConfiguration:
    """Test SSO and AI configuration tools."""

    @pytest.mark.asyncio
    async def test_get_sso_config_success(self):
        """Test successful SSO config retrieval."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_response = {
                "enabled": True,
                "provider": "okta",
                "roles": ["Admin", "Editor", "Viewer"],
            }
            mock_client.get_sso_config.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await get_sso_config_impl()

            assert result["success"] is True
            assert result["config"] == mock_response

    @pytest.mark.asyncio
    async def test_update_sso_config_success(self):
        """Test successful SSO config update."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            config = {"enabled": True, "provider": "saml"}
            mock_client.update_sso_config.return_value = config
            mock_get_client.return_value = mock_client

            result = await update_sso_config_impl(config)

            assert result["success"] is True
            assert result["message"] == "SSO configuration updated successfully"

    @pytest.mark.asyncio
    async def test_get_ai_config_success(self):
        """Test successful AI config retrieval."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_response = {
                "provider": "openai",
                "model": "gpt-4",
                "enabled": True,
            }
            mock_client.get_ai_config.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await get_ai_config_impl()

            assert result["success"] is True
            assert result["config"] == mock_response

    @pytest.mark.asyncio
    async def test_update_ai_config_success(self):
        """Test successful AI config update."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            config = {"provider": "anthropic", "model": "claude-3"}
            mock_client.update_ai_config.return_value = config
            mock_get_client.return_value = mock_client

            result = await update_ai_config_impl(config)

            assert result["success"] is True
            assert result["message"] == "AI configuration updated successfully"


# ============================================================================
# Database Instrumentation Tests
# ============================================================================


class TestDatabaseInstrumentation:
    """Test database instrumentation tools."""

    @pytest.mark.asyncio
    async def test_get_db_instrumentation_success(self):
        """Test successful DB instrumentation config retrieval."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_response = {
                "enabled": True,
                "sample_rate": 0.1,
                "slow_query_threshold_ms": 100,
            }
            mock_client.get_db_instrumentation.return_value = mock_response
            mock_get_client.return_value = mock_client

            result = await get_db_instrumentation_impl(
                "project123", "namespace/deployment/app", "mysql"
            )

            assert result["success"] is True
            assert result["config"] == mock_response

    @pytest.mark.asyncio
    async def test_update_db_instrumentation_success(self):
        """Test successful DB instrumentation config update."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            config = {"enabled": True, "sample_rate": 0.2}
            mock_client.update_db_instrumentation.return_value = config
            mock_get_client.return_value = mock_client

            result = await update_db_instrumentation_impl(
                "project123", "namespace/deployment/app", "postgres", config
            )

            assert result["success"] is True
            assert result["message"] == "postgres instrumentation updated successfully"
            assert result["config"] == config


# ============================================================================
# Panel Data Tests
# ============================================================================


class TestPanelData:
    """Test panel data tool."""

    @pytest.mark.asyncio
    async def test_get_panel_data_success(self):
        """Test successful panel data retrieval."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = Mock()
            mock_get_client.return_value = mock_client

            mock_response = {
                "metrics": [{"timestamp": 1234567890, "value": 42.5}],
                "title": "CPU Usage",
            }
            mock_client.get_panel_data = AsyncMock(return_value=mock_response)

            result = await get_panel_data_impl(
                "project123", "dashboard1", "panel1", "-1h", "now"
            )

            assert result["success"] is True
            assert result["data"] == mock_response


# ============================================================================
# Health Check Tests
# ============================================================================


class TestHealthCheck:
    """Test health check tool."""

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """Test successful health check."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.health_check.return_value = True
            mock_get_client.return_value = mock_client

            result = await health_check_impl()

            assert result["success"] is True
            assert result["healthy"] is True
            assert "healthy" in result["message"]

    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        """Test failed health check."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.health_check.return_value = False
            mock_get_client.return_value = mock_client

            result = await health_check_impl()

            assert result["success"] is True
            assert result["healthy"] is False
            assert "not responding" in result["message"]


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestErrorHandling:
    """Test error handling in server tools."""

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test error handling in tools."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.list_projects.side_effect = CorootError("API error")
            mock_get_client.return_value = mock_client

            result = await list_projects_impl()

            assert result["success"] is False
            assert "API error" in result["error"]

    @pytest.mark.asyncio
    async def test_missing_credentials(self):
        """Test handling of missing credentials."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_get_client.side_effect = ValueError("No credentials")

            result = await list_projects_impl()

            assert result["success"] is False
            assert "No credentials" in result["error"]

    @pytest.mark.asyncio
    async def test_unexpected_error(self):
        """Test handling of unexpected errors."""
        with patch("mcp_coroot.server.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.list_projects.side_effect = RuntimeError("Unexpected")
            mock_get_client.return_value = mock_client

            result = await list_projects_impl()

            assert result["success"] is False
            assert "Unexpected error" in result["error"]
