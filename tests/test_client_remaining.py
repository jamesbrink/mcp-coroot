"""Tests for remaining client functionality."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from mcp_coroot.client import CorootClient


@pytest.mark.asyncio
class TestRemainingClientFeatures:
    """Test remaining client features."""

    @pytest.fixture
    def client(self):
        """Create a test client."""
        return CorootClient(
            base_url="http://localhost:8080",
            username="admin",
            password="password",
        )

    # Node & Incident Management Tests

    async def test_get_node(self, client):
        """Test getting node details."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "id": "node1",
                "name": "worker-node-1",
                "cpu": {"usage": 0.56},
                "memory": {"usage": 0.78},
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.get_node("project123", "node1")

        assert result["id"] == "node1"
        assert result["cpu"]["usage"] == 0.56

    async def test_get_incident(self, client):
        """Test getting incident details."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "id": "incident1",
                "title": "Service degradation",
                "severity": "warning",
                "affected_apps": ["app1", "app2"],
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.get_incident("project123", "incident1")

        assert result["title"] == "Service degradation"
        assert len(result["affected_apps"]) == 2

    # Dashboard Management Tests

    async def test_list_dashboards(self, client):
        """Test listing dashboards."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "dashboards": [
                    {"id": "dash1", "name": "Overview"},
                    {"id": "dash2", "name": "Performance"},
                ]
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.list_dashboards("project123")

        assert result["dashboards"][0]["name"] == "Overview"

    async def test_create_dashboard(self, client):
        """Test creating a dashboard."""
        dashboard = {"name": "Custom Dashboard", "panels": []}
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value={"id": "dash3", **dashboard})
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.create_dashboard("project123", dashboard)

        assert result["id"] == "dash3"
        assert result["name"] == "Custom Dashboard"

    async def test_get_dashboard(self, client):
        """Test getting a specific dashboard."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "id": "dash1",
                "name": "Overview",
                "panels": [{"type": "graph"}],
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.get_dashboard("project123", "dash1")

        assert result["panels"][0]["type"] == "graph"

    async def test_update_dashboard(self, client):
        """Test updating a dashboard."""
        dashboard = {"name": "Updated Dashboard"}
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value={"id": "dash1", **dashboard})
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.update_dashboard("project123", "dash1", dashboard)

        assert result["name"] == "Updated Dashboard"

    # Integration Management Tests

    async def test_test_integration(self, client):
        """Test testing an integration."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={"status": "success", "message": "Connection verified"}
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.test_integration("project123", "prometheus")

        assert result["status"] == "success"

    async def test_delete_integration_with_204(self, client):
        """Test deleting an integration with 204 response."""
        mock_response = AsyncMock()
        mock_response.status_code = 204
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.delete_integration("project123", "slack")

        assert result["status"] == "deleted"

    async def test_delete_integration_with_json(self, client):
        """Test deleting an integration with JSON response."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json = Mock(return_value={"status": "removed", "type": "slack"})
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.delete_integration("project123", "slack")

        assert result["type"] == "slack"

    # Advanced Project Management Tests

    async def test_update_project(self, client):
        """Test updating project settings."""
        settings = {"retention": "60d"}
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={"id": "project123", "settings": settings}
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.update_project("project123", settings)

        assert result["settings"]["retention"] == "60d"

    async def test_delete_project_with_204(self, client):
        """Test deleting a project with 204 response."""
        mock_response = AsyncMock()
        mock_response.status_code = 204
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.delete_project("project123")

        assert result["status"] == "deleted"

    async def test_delete_project_with_empty_body(self, client):
        """Test deleting a project with 200 and empty body."""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.text = ""
        mock_response.json = Mock(
            side_effect=ValueError("No JSON object could be decoded")
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.delete_project("project123")

        assert result["status"] == "deleted"

    async def test_list_api_keys(self, client):
        """Test listing API keys."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "keys": [
                    {"id": "key1", "name": "Ingestion Key"},
                    {"id": "key2", "name": "Backup Key"},
                ]
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.list_api_keys("project123")

        assert len(result["keys"]) == 2

    async def test_create_api_key_with_description(self, client):
        """Test creating an API key with description."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "id": "key3",
                "name": "Test Key",
                "secret": "sk_test_123",
                "description": "For testing",
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch(
            "httpx.AsyncClient.request", return_value=mock_response
        ) as mock_request:
            result = await client.create_api_key(
                "project123", "Test Key", "For testing"
            )

            # Verify the correct structure was sent
            call_args = mock_request.call_args
            assert call_args.kwargs["json"]["action"] == "generate"
            assert (
                call_args.kwargs["json"]["description"] == "Test Key"
            )  # Uses name as description
            assert result["secret"] == "sk_test_123"

    async def test_create_api_key_without_description(self, client):
        """Test creating an API key without description."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={"id": "key3", "name": "Test Key", "secret": "sk_test_123"}
        )
        mock_response.raise_for_status = AsyncMock()

        with patch(
            "httpx.AsyncClient.request", return_value=mock_response
        ) as mock_request:
            await client.create_api_key("project123", "Test Key")

            # Verify the correct structure was sent (description is always included)
            call_args = mock_request.call_args
            assert call_args.kwargs["json"]["action"] == "generate"
            assert (
                call_args.kwargs["json"]["description"] == "Test Key"
            )  # Always uses name

    async def test_delete_api_key(self, client):
        """Test deleting an API key."""
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value={"status": "success"})
        mock_response.text = ""
        mock_response.raise_for_status = AsyncMock()
        mock_response.status_code = 200

        with patch(
            "httpx.AsyncClient.request", return_value=mock_response
        ) as mock_request:
            result = await client.delete_api_key(
                "project123", "EMUHGTklu-miwJKD5IjO2Z4OSyO8Vrzn"
            )

            # Verify request (should be 2 calls: login + delete)
            assert mock_request.call_count == 2
            # Check the second call (delete API key)
            delete_call = mock_request.call_args_list[1]
            assert delete_call.args[0] == "POST"
            assert delete_call.args[1].endswith("/api/project/project123/api_keys")

            # Verify the correct structure was sent
            call_args = mock_request.call_args
            assert call_args.kwargs["json"]["action"] == "delete"
            assert call_args.kwargs["json"]["key"] == "EMUHGTklu-miwJKD5IjO2Z4OSyO8Vrzn"

            # Verify result
            assert result["status"] == "success"

    # Application Category Management Tests

    async def test_create_application_category(self, client):
        """Test creating a new application category."""
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value={"status": "success"})
        mock_response.text = ""
        mock_response.raise_for_status = AsyncMock()
        mock_response.status_code = 200

        with patch(
            "httpx.AsyncClient.request", return_value=mock_response
        ) as mock_request:
            # The client method takes a category dictionary
            category = {
                "name": "test-category",
                "custom_patterns": "test/* qa/*",
                "notification_settings": {
                    "incidents": {"enabled": True},
                    "deployments": {"enabled": False}
                }
            }
            result = await client.create_application_category(
                "project123",
                category
            )

            # Verify request
            assert mock_request.call_count == 2  # login + create
            create_call = mock_request.call_args_list[1]
            assert create_call.args[0] == "POST"
            assert create_call.args[1].endswith("/api/project/project123/application_categories")

            # Verify the correct structure was sent
            call_args = mock_request.call_args
            json_data = call_args.kwargs["json"]
            assert json_data["name"] == "test-category"
            assert json_data["custom_patterns"] == "test/* qa/*"
            assert json_data["notification_settings"]["incidents"]["enabled"] is True
            assert json_data["notification_settings"]["deployments"]["enabled"] is False

            # Verify result
            assert result["status"] == "success"

    async def test_update_application_category(self, client):
        """Test updating an existing application category."""
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value={"status": "success"})
        mock_response.text = ""
        mock_response.raise_for_status = AsyncMock()
        mock_response.status_code = 200

        category_update = {
            "name": "test-category",
            "custom_patterns": "test/* updated/*",
            "notification_settings": {
                "incidents": {"enabled": True},
                "deployments": {"enabled": True}
            }
        }

        with patch(
            "httpx.AsyncClient.request", return_value=mock_response
        ) as mock_request:
            result = await client.update_application_category(
                "project123",
                "test-category",
                category_update
            )

            # Verify request
            assert mock_request.call_count == 2  # login + update
            update_call = mock_request.call_args_list[1]
            assert update_call.args[0] == "POST"
            assert update_call.args[1].endswith("/api/project/project123/application_categories")

            # Verify the correct structure was sent (NO action field for updates)
            call_args = mock_request.call_args
            json_data = call_args.kwargs["json"]
            assert "action" not in json_data
            assert json_data["id"] == "test-category"
            assert json_data["name"] == "test-category"
            assert json_data["custom_patterns"] == "test/* updated/*"
            assert json_data["notification_settings"]["incidents"]["enabled"] is True
            assert json_data["notification_settings"]["deployments"]["enabled"] is True

            # Verify result
            assert result["status"] == "success"

    async def test_delete_application_category(self, client):
        """Test deleting an application category."""
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value={"status": "success"})
        mock_response.text = ""
        mock_response.raise_for_status = AsyncMock()
        mock_response.status_code = 200

        with patch(
            "httpx.AsyncClient.request", return_value=mock_response
        ) as mock_request:
            result = await client.delete_application_category(
                "project123", "test-category"
            )

            # Verify request
            assert mock_request.call_count == 2  # login + delete
            delete_call = mock_request.call_args_list[1]
            assert delete_call.args[0] == "POST"
            assert delete_call.args[1].endswith("/api/project/project123/application_categories")

            # Verify the correct structure was sent
            call_args = mock_request.call_args
            json_data = call_args.kwargs["json"]
            assert json_data["action"] == "delete"
            assert json_data["id"] == "test-category"
            assert json_data["name"] == "test-category"  # Required for validation
            assert json_data["custom_patterns"] == ""  # Required for validation

            # Verify result
            assert result["status"] == "success"

    # User & Role Management Tests

    async def test_update_current_user(self, client):
        """Test updating current user."""
        user_data = {"name": "Jane Doe"}
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={"id": "user1", "email": "jane@example.com", **user_data}
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.update_current_user(user_data)

        assert result["name"] == "Jane Doe"

    async def test_list_users(self, client):
        """Test listing users."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "users": [
                    {"id": "user1", "email": "admin@example.com", "role": "Admin"},
                    {"id": "user2", "email": "user@example.com", "role": "Editor"},
                ]
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.list_users()

        assert result["users"][0]["role"] == "Admin"

    async def test_create_user(self, client):
        """Test creating a user."""
        user_data = {"email": "new@example.com", "name": "New User", "role": "Viewer"}
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value={"id": "user3", **user_data})
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.create_user(user_data)

        assert result["email"] == "new@example.com"
        assert result["role"] == "Viewer"

    async def test_get_roles(self, client):
        """Test getting available roles."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "roles": [
                    {"name": "Admin", "permissions": ["all"]},
                    {"name": "Editor", "permissions": ["read", "write"]},
                    {"name": "Viewer", "permissions": ["read"]},
                ]
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.get_roles()

        assert len(result["roles"]) == 3
        assert result["roles"][0]["name"] == "Admin"

    # Custom Cloud Pricing Tests

    async def test_get_custom_cloud_pricing(self, client):
        """Test getting custom cloud pricing."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "cpu_hourly_cost": 0.05,
                "memory_gb_hourly_cost": 0.01,
                "storage_gb_monthly_cost": 0.10,
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.get_custom_cloud_pricing("project123")

        assert result["cpu_hourly_cost"] == 0.05
        assert result["memory_gb_hourly_cost"] == 0.01

    async def test_update_custom_cloud_pricing(self, client):
        """Test updating custom cloud pricing."""
        pricing = {"cpu_hourly_cost": 0.06}
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value=pricing)
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.update_custom_cloud_pricing("project123", pricing)

        assert result["cpu_hourly_cost"] == 0.06

    async def test_delete_custom_cloud_pricing_with_204(self, client):
        """Test deleting custom cloud pricing with 204 response."""
        mock_response = AsyncMock()
        mock_response.status_code = 204
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.delete_custom_cloud_pricing("project123")

        assert result["status"] == "deleted"

    # SSO/AI Configuration Tests

    async def test_get_sso_config(self, client):
        """Test getting SSO configuration."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "enabled": True,
                "provider": "okta",
                "roles": ["Admin", "Editor", "Viewer"],
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.get_sso_config()

        assert result["enabled"] is True
        assert result["provider"] == "okta"

    async def test_update_sso_config(self, client):
        """Test updating SSO configuration."""
        config = {"enabled": True, "provider": "saml"}
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value=config)
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.update_sso_config(config)

        assert result["provider"] == "saml"

    async def test_get_ai_config(self, client):
        """Test getting AI configuration."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={"provider": "openai", "model": "gpt-4", "enabled": True}
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.get_ai_config()

        assert result["provider"] == "openai"
        assert result["model"] == "gpt-4"

    async def test_update_ai_config(self, client):
        """Test updating AI configuration."""
        config = {"provider": "anthropic", "model": "claude-3"}
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value=config)
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.update_ai_config(config)

        assert result["provider"] == "anthropic"

    # Database Instrumentation Tests

    async def test_get_db_instrumentation(self, client):
        """Test getting database instrumentation config."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "enabled": True,
                "sample_rate": 0.1,
                "slow_query_threshold_ms": 100,
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch(
            "httpx.AsyncClient.request", return_value=mock_response
        ) as mock_request:
            result = await client.get_db_instrumentation(
                "project123", "namespace/deployment/app", "mysql"
            )

            # Check URL encoding
            call_args = mock_request.call_args
            url = call_args.args[1]
            assert "namespace%2Fdeployment%2Fapp" in url
            assert result["enabled"] is True

    async def test_update_db_instrumentation(self, client):
        """Test updating database instrumentation config."""
        config = {"enabled": True, "sample_rate": 0.2}
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value=config)
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.update_db_instrumentation(
                "project123", "namespace/deployment/app", "postgres", config
            )

        assert result["sample_rate"] == 0.2

    # Risk Overview Test

    async def test_get_risks_overview(self, client):
        """Test getting risks overview."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "high_risk_apps": ["app1", "app2"],
                "total_risks": 5,
                "critical_issues": 2,
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.get_risks_overview("project123")

        assert result["total_risks"] == 5
        assert len(result["high_risk_apps"]) == 2

    # Panel Data Test

    async def test_get_panel_data(self, client):
        """Test getting panel data."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "metrics": [{"timestamp": 1234567890, "value": 42.5}],
                "title": "CPU Usage",
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch(
            "httpx.AsyncClient.request", return_value=mock_response
        ) as mock_request:
            result = await client.get_panel_data(
                "project123", "dashboard1", "panel1", {"from": "-1h", "to": "now"}
            )

            # Check that params were properly constructed
            call_args = mock_request.call_args
            assert call_args.kwargs["params"]["dashboard"] == "dashboard1"
            assert call_args.kwargs["params"]["panel"] == "panel1"
            assert call_args.kwargs["params"]["from"] == "-1h"
            assert result["metrics"][0]["value"] == 42.5

    # Individual Integration Test

    async def test_get_integration(self, client):
        """Test getting specific integration config."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "type": "prometheus",
                "url": "http://prometheus:9090",
                "enabled": True,
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.get_integration("project123", "prometheus")

        assert result["type"] == "prometheus"
        assert result["enabled"] is True

    # Advanced Configuration Tests

    async def test_configure_profiling(self, client):
        """Test configuring profiling."""
        mock_response = AsyncMock()
        mock_response.json = Mock(return_value={"enabled": True, "sample_rate": 0.1})
        mock_response.raise_for_status = AsyncMock()

        with patch(
            "httpx.AsyncClient.request", return_value=mock_response
        ) as mock_request:
            result = await client.configure_profiling(
                "project123",
                "namespace/deployment/app",
                {"enabled": True, "sample_rate": 0.1},
            )

            # Check URL encoding
            call_args = mock_request.call_args
            url = call_args.args[1]
            assert "namespace%2Fdeployment%2Fapp" in url
            assert result["sample_rate"] == 0.1

    async def test_configure_tracing(self, client):
        """Test configuring tracing."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "enabled": True,
                "sample_rate": 0.05,
                "excluded_paths": ["/health"],
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.configure_tracing(
                "project123",
                "app1",
                {"enabled": True, "sample_rate": 0.05, "excluded_paths": ["/health"]},
            )

        assert result["sample_rate"] == 0.05
        assert "/health" in result["excluded_paths"]

    async def test_configure_logs(self, client):
        """Test configuring log collection."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "enabled": True,
                "level": "warn",
                "excluded_patterns": [".*debug.*"],
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.configure_logs(
                "project123",
                "app1",
                {"enabled": True, "level": "warn", "excluded_patterns": [".*debug.*"]},
            )

        assert result["level"] == "warn"
        assert ".*debug.*" in result["excluded_patterns"]

    # Role Management Test

    async def test_create_or_update_role(self, client):
        """Test creating or updating a role."""
        mock_response = AsyncMock()
        mock_response.json = Mock(
            return_value={
                "name": "CustomRole",
                "permissions": ["read", "write"],
                "description": "Custom role for testing",
            }
        )
        mock_response.raise_for_status = AsyncMock()

        with patch("httpx.AsyncClient.request", return_value=mock_response):
            result = await client.create_or_update_role(
                {
                    "name": "CustomRole",
                    "permissions": ["read", "write"],
                    "description": "Custom role for testing",
                }
            )

        assert result["name"] == "CustomRole"
        assert "write" in result["permissions"]
