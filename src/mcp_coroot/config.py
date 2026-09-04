"""Runtime configuration.

Settings are read from environment variables once, at startup, by the CLI. Nothing
in this package reads the environment at import time.

Environment variables:

``COROOT_BASE_URL``        Coroot URL, e.g. ``https://coroot.example.com`` (default
                           ``http://localhost:8080``). ``COROOT_URL`` is accepted as an
                           alias.
``COROOT_USERNAME`` /      Credentials for automatic login (recommended).
``COROOT_PASSWORD``
``COROOT_SESSION_COOKIE``  Value of an existing ``coroot_session`` cookie (SSO / MFA).
``COROOT_API_KEY``         Project API key; only used for the Prometheus-compatible
                           ``/api/v1/*`` query endpoints.
``COROOT_PROJECT``         Default project id used when a tool omits ``project_id``.
``COROOT_TIMEOUT``         HTTP timeout in seconds (default 30).
``COROOT_VERIFY_SSL``      ``false`` to skip TLS verification (default ``true``).
``COROOT_READ_ONLY``       ``true`` to hide every tool that modifies Coroot.
``COROOT_MAX_OUTPUT_CHARS`` Character budget for a single tool response (default 40000).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

DEFAULT_BASE_URL = "http://localhost:8080"
DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_OUTPUT_CHARS = 40_000
MIN_MAX_OUTPUT_CHARS = 2_000

SESSION_COOKIE_NAME = "coroot_session"
API_KEY_HEADER = "X-API-Key"

AuthMode = Literal["session_cookie", "password", "api_key", "none"]

_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"0", "false", "no", "off"})


class ConfigError(ValueError):
    """Raised when the environment holds an invalid setting."""


def _parse_bool(name: str, raw: str | None, default: bool) -> bool:
    if raw is None or raw.strip() == "":
        return default
    value = raw.strip().lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ConfigError(f"{name} must be a boolean (true/false), got {raw!r}")


def _parse_float(name: str, raw: str | None, default: float) -> float:
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from exc


def _parse_int(name: str, raw: str | None, default: int) -> int:
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc


def _optional(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = raw.strip()
    return value or None


@dataclass(frozen=True, slots=True)
class Settings:
    """Immutable server configuration."""

    base_url: str = DEFAULT_BASE_URL
    username: str | None = None
    password: str | None = None
    session_cookie: str | None = None
    api_key: str | None = None
    default_project: str | None = None
    timeout: float = DEFAULT_TIMEOUT
    verify_ssl: bool = True
    read_only: bool = False
    max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS

    def __post_init__(self) -> None:
        url = self.base_url.strip().rstrip("/")
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ConfigError(
                "COROOT_BASE_URL must be an http(s) URL such as "
                f"http://localhost:8080, got {self.base_url!r}"
            )
        object.__setattr__(self, "base_url", url)
        if self.timeout <= 0:
            raise ConfigError("COROOT_TIMEOUT must be greater than zero")
        if self.max_output_chars < MIN_MAX_OUTPUT_CHARS:
            raise ConfigError(
                f"COROOT_MAX_OUTPUT_CHARS must be at least {MIN_MAX_OUTPUT_CHARS}"
            )
        if (self.username is None) != (self.password is None):
            raise ConfigError(
                "COROOT_USERNAME and COROOT_PASSWORD must be set together"
            )

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        """Build settings from ``env`` (defaults to ``os.environ``)."""
        source = os.environ if env is None else env
        base_url = _optional(source.get("COROOT_BASE_URL")) or _optional(
            source.get("COROOT_URL")
        )
        return cls(
            base_url=base_url or DEFAULT_BASE_URL,
            username=_optional(source.get("COROOT_USERNAME")),
            password=_optional(source.get("COROOT_PASSWORD")),
            session_cookie=_optional(source.get("COROOT_SESSION_COOKIE")),
            api_key=_optional(source.get("COROOT_API_KEY")),
            default_project=_optional(source.get("COROOT_PROJECT")),
            timeout=_parse_float(
                "COROOT_TIMEOUT", source.get("COROOT_TIMEOUT"), DEFAULT_TIMEOUT
            ),
            verify_ssl=_parse_bool(
                "COROOT_VERIFY_SSL", source.get("COROOT_VERIFY_SSL"), True
            ),
            read_only=_parse_bool(
                "COROOT_READ_ONLY", source.get("COROOT_READ_ONLY"), False
            ),
            max_output_chars=_parse_int(
                "COROOT_MAX_OUTPUT_CHARS",
                source.get("COROOT_MAX_OUTPUT_CHARS"),
                DEFAULT_MAX_OUTPUT_CHARS,
            ),
        )

    @property
    def can_login(self) -> bool:
        """True when username/password login is possible."""
        return self.username is not None and self.password is not None

    @property
    def auth_mode(self) -> AuthMode:
        """The authentication method that will be used for management APIs."""
        if self.session_cookie:
            return "session_cookie"
        if self.can_login:
            return "password"
        if self.api_key:
            return "api_key"
        return "none"

    def redacted(self) -> dict[str, object]:
        """Settings without secrets, for diagnostics."""
        return {
            "base_url": self.base_url,
            "auth_mode": self.auth_mode,
            "username": self.username,
            "default_project": self.default_project,
            "timeout": self.timeout,
            "verify_ssl": self.verify_ssl,
            "read_only": self.read_only,
            "max_output_chars": self.max_output_chars,
        }
