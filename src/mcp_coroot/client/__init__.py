"""Async client for the Coroot HTTP API."""

from .applications import (
    CHECK_IDS,
    INSTRUMENTATION_DEFAULT_PORTS,
    INSTRUMENTATION_TYPES,
    LOG_SEVERITIES,
    build_trace_param,
)
from .base import Enveloped, Transport, split_envelope
from .client import CorootClient
from .configuration import INTEGRATION_TYPES, NOTIFICATION_INTEGRATION_TYPES
from .dashboards import build_panel, metrics_query
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
from .ids import (
    PROJECT_SCOPE_APP_ID,
    ApplicationId,
    InvalidApplicationId,
    encode_segment,
    normalize_app_id,
)
from .overview import OVERVIEW_VIEWS
from .timerange import (
    InvalidTimeError,
    ms_to_iso,
    parse_duration_ms,
    resolve_epoch_ms,
    time_params,
    to_coroot_time,
)

__all__ = [
    "CHECK_IDS",
    "INSTRUMENTATION_DEFAULT_PORTS",
    "INSTRUMENTATION_TYPES",
    "INTEGRATION_TYPES",
    "LOG_SEVERITIES",
    "NOTIFICATION_INTEGRATION_TYPES",
    "OVERVIEW_VIEWS",
    "PROJECT_SCOPE_APP_ID",
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
    "Enveloped",
    "InvalidApplicationId",
    "InvalidTimeError",
    "Transport",
    "build_panel",
    "build_trace_param",
    "encode_segment",
    "metrics_query",
    "ms_to_iso",
    "normalize_app_id",
    "parse_duration_ms",
    "resolve_epoch_ms",
    "split_envelope",
    "time_params",
    "to_coroot_time",
]
