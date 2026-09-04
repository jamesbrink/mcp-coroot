"""Tests for identifier and time-range helpers."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from mcp_coroot.client.ids import (
    PROJECT_SCOPE_APP_ID,
    ApplicationId,
    InvalidApplicationId,
    encode_segment,
    normalize_app_id,
)
from mcp_coroot.client.timerange import (
    InvalidTimeError,
    ms_to_iso,
    parse_duration_ms,
    time_params,
    to_coroot_time,
)


def test_parse_four_part() -> None:
    app = ApplicationId.parse("hwvop6p7:default:Deployment:checkout")
    assert app == ApplicationId("hwvop6p7", "default", "Deployment", "checkout")
    assert str(app) == "hwvop6p7:default:Deployment:checkout"
    assert app.short == "default:Deployment:checkout"
    assert app.is_complete


def test_parse_three_part_with_fallback() -> None:
    app = ApplicationId.parse("default:Deployment:api", fallback_cluster_id="p1")
    assert str(app) == "p1:default:Deployment:api"
    assert not ApplicationId.parse("default:Deployment:api").is_complete


def test_name_with_colon_and_external() -> None:
    app = ApplicationId.parse("c1:_:Deployment:redis:6379")
    assert app.name == "redis:6379"
    ext = ApplicationId.parse("external:ExternalService:db.example.com:5432")
    assert ext.cluster_id == "external"
    assert ext.name == "db.example.com:5432"
    ext2 = ApplicationId.parse("external:external:ExternalService:api")
    assert ext2 == ApplicationId("external", "external", "ExternalService", "api")


def test_invalid_ids() -> None:
    for bad in ("checkout", "ns:name"):
        with pytest.raises(InvalidApplicationId):
            ApplicationId.parse(bad)


def test_normalize_and_scope() -> None:
    assert normalize_app_id("ns:Deployment:a", project_id="p1") == "p1:ns:Deployment:a"
    assert normalize_app_id(" :: ") == PROJECT_SCOPE_APP_ID
    assert ApplicationId.parse("::").is_project_scope


def test_encode_segment() -> None:
    assert encode_segment("p1:ns:Deployment:a+b") == "p1%3Ans%3ADeployment%3Aa%2Bb"
    assert encode_segment("::") == "%3A%3A"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("now", "now"),
        ("NOW-1H", "now-1h"),
        ("now - 30m", "now-30m"),
        ("now+15m", "now+15m"),
        ("1h", "now-1h"),
        ("-2d", "now-2d"),
        ("+10m", "now+10m"),
        ("1h30m", "now-1h30m"),
        (1_700_000_000, "1700000000000"),
        (1_700_000_000_000, "1700000000000"),
        ("1700000000", "1700000000000"),
        (1_700_000_000.5, "1700000000500"),
        ("2024-01-01T00:00:00Z", "1704067200000"),
        ("2024-01-01T00:00:00+02:00", "1704060000000"),
        ("2024-01-01", "1704067200000"),
        (datetime(2024, 1, 1, tzinfo=UTC), "1704067200000"),
        (datetime(2024, 1, 1), "1704067200000"),
    ],
)
def test_to_coroot_time(value: object, expected: str | None) -> None:
    assert to_coroot_time(value) == expected  # type: ignore[arg-type]


@pytest.mark.parametrize("value", ["yesterday", "now-1x", "-5", "1h ago", True, -5])
def test_invalid_times(value: object) -> None:
    with pytest.raises(InvalidTimeError):
        to_coroot_time(value)  # type: ignore[arg-type]


def test_time_params() -> None:
    assert time_params() == {}
    assert time_params("1h", "now") == {"from": "now-1h", "to": "now"}
    assert time_params(None, None, incident="abc", alert=None) == {"incident": "abc"}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("5m", 300_000),
        ("1h30m", 5_400_000),
        ("500ms", 500),
        (1500, 1500),
        ("90", 90),
        (2.5, 2),
    ],
)
def test_parse_duration(value: object, expected: int) -> None:
    assert parse_duration_ms(value) == expected  # type: ignore[arg-type]


@pytest.mark.parametrize("value", ["soon", "-5m", -1, True])
def test_parse_duration_invalid(value: object) -> None:
    with pytest.raises(InvalidTimeError):
        parse_duration_ms(value)  # type: ignore[arg-type]


def test_ms_to_iso() -> None:
    assert ms_to_iso(1704067200000) == "2024-01-01T00:00:00Z"
    assert ms_to_iso(None) is None
    assert ms_to_iso(0) is None
