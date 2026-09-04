"""Tests for environment based configuration."""

from __future__ import annotations

import pytest

from mcp_coroot.config import ConfigError, Settings


def test_defaults() -> None:
    settings = Settings.from_env({})
    assert settings.base_url == "http://localhost:8080"
    assert settings.auth_mode == "none"
    assert settings.timeout == 30.0
    assert settings.verify_ssl is True
    assert settings.read_only is False


def test_full_env() -> None:
    settings = Settings.from_env(
        {
            "COROOT_BASE_URL": "https://coroot.example.com/ ",
            "COROOT_USERNAME": "me",
            "COROOT_PASSWORD": "pw",
            "COROOT_PROJECT": "abc12345",
            "COROOT_TIMEOUT": "5.5",
            "COROOT_VERIFY_SSL": "no",
            "COROOT_READ_ONLY": "1",
            "COROOT_MAX_OUTPUT_CHARS": "5000",
        }
    )
    assert settings.base_url == "https://coroot.example.com"
    assert settings.auth_mode == "password"
    assert settings.can_login
    assert settings.default_project == "abc12345"
    assert settings.timeout == 5.5
    assert settings.verify_ssl is False
    assert settings.read_only is True
    assert settings.max_output_chars == 5000
    redacted = settings.redacted()
    assert "pw" not in str(redacted)
    assert redacted["username"] == "me"


def test_url_alias_and_cookie_priority() -> None:
    settings = Settings.from_env(
        {
            "COROOT_URL": "http://alias:8080",
            "COROOT_SESSION_COOKIE": "c",
            "COROOT_USERNAME": "u",
            "COROOT_PASSWORD": "p",
        }
    )
    assert settings.base_url == "http://alias:8080"
    assert settings.auth_mode == "session_cookie"


def test_api_key_only() -> None:
    assert Settings.from_env({"COROOT_API_KEY": "k"}).auth_mode == "api_key"


@pytest.mark.parametrize(
    "env",
    [
        {"COROOT_BASE_URL": "coroot.example.com"},
        {"COROOT_BASE_URL": "ftp://x"},
        {"COROOT_TIMEOUT": "abc"},
        {"COROOT_TIMEOUT": "0"},
        {"COROOT_VERIFY_SSL": "maybe"},
        {"COROOT_MAX_OUTPUT_CHARS": "10"},
        {"COROOT_MAX_OUTPUT_CHARS": "lots"},
        {"COROOT_USERNAME": "only-user"},
    ],
)
def test_invalid_env(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError):
        Settings.from_env(env)
