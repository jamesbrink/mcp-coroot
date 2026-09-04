"""Time range helpers.

Coroot's HTTP API accepts ``from``/``to`` as either epoch **milliseconds** or a
relative expression such as ``now-1h`` (``now``, ``now-30m``, ``now-2d``, ``now-1w``).
This module accepts the friendlier forms an LLM is likely to produce and converts
them to what Coroot expects.
"""

from __future__ import annotations

import re
import time
from datetime import UTC, datetime

TimeInput = str | int | float | datetime | None

_UNIT_MS: dict[str, float] = {
    "ns": 1e-6,
    "us": 1e-3,
    "µs": 1e-3,
    "ms": 1.0,
    "s": 1_000.0,
    "m": 60_000.0,
    "h": 3_600_000.0,
    "d": 86_400_000.0,
    "w": 604_800_000.0,
}

_DURATION_TOKEN = re.compile(r"(\d+(?:\.\d+)?)(ns|us|µs|ms|s|m|h|d|w)")
_DURATION = re.compile(r"^(?:\d+(?:\.\d+)?(?:ns|us|µs|ms|s|m|h|d|w))+$")
_RELATIVE = re.compile(r"^now(?:([+-])(.+))?$")
_NUMBER = re.compile(r"^-?\d+(?:\.\d+)?$")

#: Epoch values below this are treated as seconds rather than milliseconds.
_SECONDS_THRESHOLD = 100_000_000_000  # year 5138 in seconds, 1973 in ms


class InvalidTimeError(ValueError):
    """The value could not be interpreted as a point in time."""


def parse_duration_ms(value: str | int | float) -> int:
    """Convert ``"5m"``, ``"1h30m"``, ``90`` (seconds) or ``1500.0`` (ms) to ms.

    Integers are interpreted as milliseconds when they look like one (>= 10 s
    expressed in ms is ambiguous, so plain numbers are always taken as ms, matching
    Coroot's JSON encoding of durations).
    """
    if isinstance(value, bool):  # bool is an int subclass; reject explicitly
        raise InvalidTimeError("duration must be a string or number")
    if isinstance(value, int | float):
        if value < 0:
            raise InvalidTimeError("duration must not be negative")
        return int(value)
    text = value.strip().lower().replace(" ", "")
    if _NUMBER.match(text):
        return parse_duration_ms(float(text))
    if not _DURATION.match(text):
        raise InvalidTimeError(
            f"invalid duration {value!r}: use Go-style durations such as "
            "'30s', '5m', '1h30m', '2d'"
        )
    total = 0.0
    for amount, unit in _DURATION_TOKEN.findall(text):
        total += float(amount) * _UNIT_MS[unit]
    return int(total)


def _epoch_ms(number: float) -> str:
    if number < 0:
        raise InvalidTimeError("timestamps must not be negative")
    if number < _SECONDS_THRESHOLD:
        number *= 1000
    return str(int(number))


def to_coroot_time(value: TimeInput) -> str | None:
    """Normalise a user supplied time into a Coroot ``from``/``to`` parameter.

    Accepted inputs:

    * ``None`` or ``""`` -> ``None`` (let Coroot apply its default window)
    * ``now``, ``now-1h``, ``now+30m`` -> passed through
    * bare durations ``1h``, ``-30m``, ``2d`` -> ``now-1h`` etc.
    * epoch seconds or milliseconds (int, float or numeric string)
    * ISO-8601 timestamps (``2026-09-04T10:00:00Z``); naive values are UTC
    * :class:`datetime.datetime` objects
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        stamp = value if value.tzinfo else value.replace(tzinfo=UTC)
        return str(int(stamp.timestamp() * 1000))
    if isinstance(value, bool):
        raise InvalidTimeError("time must be a string, number or datetime")
    if isinstance(value, int | float):
        return _epoch_ms(float(value))

    text = value.strip()
    if not text:
        return None
    lowered = text.lower().replace(" ", "")
    relative = _RELATIVE.match(lowered)
    if relative:
        sign, duration = relative.group(1), relative.group(2)
        if sign is None:
            return "now"
        if not _DURATION.match(duration):
            raise InvalidTimeError(
                f"invalid relative time {value!r}: use e.g. 'now-1h', 'now-30m'"
            )
        return f"now{sign}{duration}"
    if _NUMBER.match(lowered):
        return _epoch_ms(float(lowered))
    stripped = lowered.lstrip("+-")
    if _DURATION.match(stripped):
        sign = "+" if lowered.startswith("+") else "-"
        return f"now{sign}{stripped}"
    iso = text
    if iso.endswith("Z") or iso.endswith("z"):
        iso = iso[:-1] + "+00:00"
    try:
        stamp = datetime.fromisoformat(iso)
    except ValueError as exc:
        raise InvalidTimeError(
            f"invalid time {value!r}: use 'now-1h', a bare duration like '30m', "
            "an epoch timestamp, or an ISO-8601 date"
        ) from exc
    return to_coroot_time(stamp)


def time_params(
    from_: TimeInput = None, to: TimeInput = None, **extra: str | None
) -> dict[str, str]:
    """Build the ``from``/``to`` query parameters (omitting unset values)."""
    params: dict[str, str] = {}
    start = to_coroot_time(from_)
    end = to_coroot_time(to)
    if start is not None:
        params["from"] = start
    if end is not None:
        params["to"] = end
    for key, value in extra.items():
        if value:
            params[key] = value
    return params


def ms_to_iso(value: int | float | None) -> str | None:
    """Render an epoch-millisecond timestamp as ISO-8601 UTC (``None`` passthrough)."""
    if value is None or value <= 0:
        return None
    return (
        datetime.fromtimestamp(value / 1000, tz=UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def resolve_epoch_ms(
    value: TimeInput, *, default: str = "now", now_ms: int | None = None
) -> int:
    """Resolve a time input to absolute epoch milliseconds.

    Relative expressions are evaluated against ``now_ms`` (default: the current
    time). Used for endpoints that need absolute timestamps, such as the
    Prometheus-compatible query API.
    """
    text = to_coroot_time(value) or default
    now = int(time.time() * 1000) if now_ms is None else now_ms
    relative = _RELATIVE.match(text)
    if relative:
        sign, duration = relative.group(1), relative.group(2)
        if sign is None:
            return now
        delta = parse_duration_ms(duration)
        return now + delta if sign == "+" else now - delta
    return int(text)
