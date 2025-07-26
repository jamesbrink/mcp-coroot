"""Shared test fixtures and configuration."""

from unittest.mock import AsyncMock, Mock

import pytest

from mcp_coroot.client import CorootClient


@pytest.fixture
def base_url():
    """Base URL for testing."""
    return "http://localhost:8080"


@pytest.fixture
def client(base_url):
    """Create a test client with all auth methods."""
    return CorootClient(
        base_url=base_url,
        api_key="test-api-key",
        session_cookie="test-session-cookie",
    )


@pytest.fixture
def client_with_creds(base_url):
    """Create a test client with username/password."""
    return CorootClient(
        base_url=base_url,
        username="test-user",
        password="test-pass",
    )


@pytest.fixture
def client_minimal(base_url):
    """Create a minimal test client."""
    return CorootClient(base_url=base_url)


@pytest.fixture
def mock_response():
    """Create a mock HTTP response."""
    response = AsyncMock()
    response.raise_for_status = AsyncMock()
    response.status_code = 200
    response.headers = {"content-type": "application/json"}
    response.json = Mock(return_value={})
    return response


@pytest.fixture
def mock_projects():
    """Sample project data."""
    return [
        {"id": "project1", "name": "Project 1"},
        {"id": "project2", "name": "Project 2"},
    ]


@pytest.fixture
def mock_user():
    """Sample user data."""
    return {
        "id": 1,
        "email": "admin@example.com",
        "name": "Admin User",
        "roles": ["Admin"],
    }


@pytest.fixture
def mock_application():
    """Sample application data."""
    return {
        "id": "default/deployment/frontend",
        "name": "frontend",
        "namespace": "default",
        "metrics": {
            "cpu": 0.45,
            "memory": 0.62,
        },
        "status": "healthy",
    }
