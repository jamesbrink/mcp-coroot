"""Async client for the Coroot HTTP API.

``__all__`` is the supported surface. Everything else in this package is an
implementation detail of the MCP server and may change without notice; import it
from its own module if you need it.
"""

from .client import CorootClient
from .errors import (
    CorootAuthenticationError,
    CorootConflictError,
    CorootConnectionError,
    CorootError,
    CorootNotFoundError,
    CorootPermissionError,
    CorootServerError,
    CorootUnsupportedError,
    CorootValidationError,
)
from .ids import ApplicationId, InvalidApplicationId, normalize_app_id
from .timerange import InvalidTimeError

__all__ = [
    "ApplicationId",
    "CorootAuthenticationError",
    "CorootClient",
    "CorootConflictError",
    "CorootConnectionError",
    "CorootError",
    "CorootNotFoundError",
    "CorootPermissionError",
    "CorootServerError",
    "CorootUnsupportedError",
    "CorootValidationError",
    "InvalidApplicationId",
    "InvalidTimeError",
    "normalize_app_id",
]
