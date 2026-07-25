"""Parse, validate, and normalize raw Xcel Energy outage-map payloads.

All functions are pure and dependency-free (standard library only).  The
public API includes :func:`parse_events` (compatibility) and
:func:`parse_payload` (structured outcome).
"""

from __future__ import annotations

import datetime
import logging
import math
from types import MappingProxyType
from typing import Any

from .const import EXCLUDED_STATUSES
from .models import OutageEvent, ParseOutcome

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers — numeric coercion
# ---------------------------------------------------------------------------

_REQUIRED_FIELDS = frozenset({"identifier", "latitude", "longitude", "numPeople"})


def _parse_float(value: Any, field_name: str) -> float | None:
    """Coerce *value* to a finite float, returning ``None`` on failure.

    Rules:
    - Reject ``bool`` (a ``bool`` is a subclass of ``int`` in Python).
    - Reject non-finite values (NaN, Infinity).
    - Accept ``int`` / ``float`` and strings parseable as floats.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        val = float(value)
        if not math.isfinite(val):
            return None
        return val
    if isinstance(value, str):
        try:
            val = float(value.strip())
        except (ValueError, TypeError):
            return None
        if not math.isfinite(val):
            return None
        return val
    return None


def _parse_int_strict(value: Any, field_name: str) -> int | None:
    """Coerce *value* to a non-negative ``int``, returning ``None`` on failure.

    Rules:
    - Reject ``bool`` (Python ``bool`` is a subclass of ``int``).
    - Reject ``float`` / fractional values — only pure integer JSON values
      and integer-parseable strings are accepted.
    - Reject negative values.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        if value < 0:
            return None
        return value
    if isinstance(value, float):
        return None
    if isinstance(value, str):
        try:
            val = int(value.strip())
            if val < 0:
                return None
            return val
        except (ValueError, TypeError):
            return None
    return None


# ---------------------------------------------------------------------------
# Internal helpers — datetime
# ---------------------------------------------------------------------------


def _parse_datetime(value: Any) -> datetime.datetime | None:
    """Parse an ISO-8601 datetime string or numeric epoch-millisecond value.

    Accepts:
    * Strings with and without trailing ``Z`` / timezone offset.
    * ``int`` / ``float`` epoch-millisecond timestamps (non-bool, finite).

    Returns ``None`` when the value is missing, unparsable, or out of range.
    Error messages never include the raw value.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            return None
        try:
            return datetime.datetime.fromtimestamp(
                value / 1000.0, tz=datetime.timezone.utc
            )
        except (OSError, OverflowError, ValueError):
            return None
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        # Python 3.11+ has fromisoformat that accepts Z; for 3.10 compat
        # handle Z manually.
        if text.endswith("Z"):
            return datetime.datetime.fromisoformat(text[:-1]).replace(
                tzinfo=datetime.timezone.utc
            )
        return datetime.datetime.fromisoformat(text)
    except (ValueError, TypeError):
        _LOGGER.debug("Cannot parse datetime %r", text)
        return None


# ---------------------------------------------------------------------------
# Internal helpers — status detection
# ---------------------------------------------------------------------------


def _normalize_states(raw: Any) -> tuple[str, ...]:
    """Normalise the ``states`` field to a ``tuple[str, ...]``.

    The source may provide ``states`` as a single string (``"CO"``) or as a
    list (``["CO"]``).  Missing or ``None`` values produce an empty tuple.
    """
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, (list, tuple)):
        return tuple(str(s) for s in raw)
    return ()


def _normalize_additional_properties(raw: Any) -> dict[str, Any] | None:
    """Normalise ``additionalProperties`` to a ``dict``.

    The live endpoint may return ``additionalProperties`` as either:

    * A ``dict`` — used as-is.
    * A ``list`` of ``{"property": <str>, "value": <any>}`` records —
      converted to a ``dict`` (last value wins on duplicate property names).
    * ``None`` or absent — treated as an empty dict.
    * Any other type — returns ``None`` (unusable, triggers strict malformed
      handling in the caller).

    Malformed list items (non-dict, missing ``property`` key, non-string
    ``property``) are silently skipped.
    """
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        result: dict[str, Any] = {}
        for item in raw:
            if not isinstance(item, dict):
                continue
            prop = item.get("property")
            if not isinstance(prop, str):
                continue
            result[prop] = item.get("value")
        return result
    return None


def _is_excluded_status(raw: dict[str, Any]) -> bool:
    """Return ``True`` if **either** the top-level ``status`` or the
    supplemental ``outagestatus`` (inside ``additionalProperties``) is a
    terminal value (resolved/closed/cancelled/complete/completed).

    Comparison is case-insensitive.  Missing or non-string values are ignored.
    ``additionalProperties`` is normalised from the list-of-records form
    transparently.
    """
    status = raw.get("status")
    if isinstance(status, str) and status.strip().lower() in EXCLUDED_STATUSES:
        return True
    add_props = _normalize_additional_properties(raw.get("additionalProperties"))
    if add_props is not None:
        outagestatus = add_props.get("outagestatus")
        if (
            isinstance(outagestatus, str)
            and outagestatus.strip().lower() in EXCLUDED_STATUSES
        ):
            return True
    return False


# ---------------------------------------------------------------------------
# Internal helper — deduplication
# ---------------------------------------------------------------------------


def _deduplicate_events(parsed: list[OutageEvent]) -> list[OutageEvent]:
    """Deduplicate events by ``identifier``, keeping the most recently
    updated event.  Stable on equal / ``None`` timestamps.

    ``None`` (missing) timestamps are treated as the earliest possible value
    so that an event with a known timestamp always wins over one without.
    """
    seen: dict[str, OutageEvent] = {}
    for event in parsed:
        existing = seen.get(event.identifier)
        if existing is None:
            seen[event.identifier] = event
        else:
            existing_ts = existing.last_updated_time or datetime.datetime.min.replace(
                tzinfo=datetime.timezone.utc
            )
            candidate_ts = event.last_updated_time or datetime.datetime.min.replace(
                tzinfo=datetime.timezone.utc
            )
            if existing_ts.tzinfo is None:
                existing_ts = existing_ts.replace(tzinfo=datetime.timezone.utc)
            if candidate_ts.tzinfo is None:
                candidate_ts = candidate_ts.replace(tzinfo=datetime.timezone.utc)
            if candidate_ts > existing_ts:
                seen[event.identifier] = event
    return list(seen.values())


# ---------------------------------------------------------------------------
# Public API — single-event parse
# ---------------------------------------------------------------------------


def parse_event(raw: dict[str, Any]) -> OutageEvent | None:
    """Attempt to parse and validate a single raw event *dict*.

    Returns an :class:`~models.OutageEvent` instance on success, or ``None``
    when the event is malformed.  **Privacy note**: error messages never
    include the raw payload.

    Validation steps (in order):

    1. All required fields (``identifier``, ``latitude``, ``longitude``,
       ``numPeople``) must be present.
    2. ``latitude`` and ``longitude`` must be finite floats within range.
    3. ``numPeople`` must be a non-negative integer (no bool, no float).
    4. ``additionalProperties`` (if present) is normalised via
       :func:`_normalize_additional_properties` — accepts both ``dict`` and
       ``list``-of-records forms.  Supplemental fields (including ``states``)
       are normalised and the result is wrapped in an immutable
       :class:`~types.MappingProxyType`.
    """
    # --- presence check ----------------------------------------------------
    missing = _REQUIRED_FIELDS - raw.keys()
    if missing:
        _LOGGER.debug("Skipping event missing required fields: %s", sorted(missing))
        return None

    identifier = raw.get("identifier")
    if not isinstance(identifier, str) or not identifier.strip():
        _LOGGER.debug("Skipping event with invalid identifier")
        return None

    # --- coordinates (finite decimal allowed) ------------------------------
    lat = _parse_float(raw.get("latitude"), "latitude")
    lon = _parse_float(raw.get("longitude"), "longitude")
    if lat is None or lon is None:
        return None
    if not (-90.0 <= lat <= 90.0):
        return None
    if not (-180.0 <= lon <= 180.0):
        return None

    # --- customer count (strict integer only, no bool, no float) -----------
    num_people = _parse_int_strict(raw.get("numPeople"), "numPeople")
    if num_people is None:
        return None

    # --- additionalProperties + states normalisation -----------------------
    add_props = _normalize_additional_properties(raw.get("additionalProperties"))
    if add_props is None:
        return None

    # Build an immutable copy with ``states`` normalised to tuple
    immutable_add_props: dict[str, Any] = dict(add_props)
    immutable_add_props["states"] = _normalize_states(add_props.get("states"))
    frozen_add_props = MappingProxyType(immutable_add_props)

    # --- timestamps (optional; parse failure is non-fatal) -----------------
    start_time = _parse_datetime(raw.get("startTime"))
    last_updated_time = _parse_datetime(raw.get("lastUpdatedTime"))
    etr_time = _parse_datetime(raw.get("etrTime"))

    # --- strings (empty string on missing) ---------------------------------
    title = str(raw.get("title", "") or "")
    status = str(raw.get("status", "") or "")
    cause = str(raw.get("cause", "") or "")
    county = str(raw.get("county", "") or "")

    return OutageEvent(
        identifier=identifier.strip(),
        start_time=start_time,
        last_updated_time=last_updated_time,
        etr_time=etr_time,
        title=title,
        status=status,
        cause=cause,
        num_people=num_people,
        latitude=lat,
        longitude=lon,
        county=county,
        additional_properties=frozen_add_props,
    )


# ---------------------------------------------------------------------------
# Public API — structured outcome
# ---------------------------------------------------------------------------


def parse_payload(raw: Any) -> ParseOutcome:
    """Parse an API response into a structured :class:`~models.ParseOutcome`.

    The outcome distinguishes:

    * **Non-list payload** (``is_valid_payload=False``) — schema failure.
    * **All-malformed records** (``is_valid_payload=True``,
      ``malformed_count == raw_count > 0``) — possible schema change.
    * **All-valid-but-filtered**  (``is_valid_payload=True``,
      ``parsed_count > 0``, zero events) — valid no-outage data
      (all events have a resolved/closed/cancelled status).
    * **Normal data** — events are returned with populated aggregate counts.

    Parameters
    ----------
    raw:
        The deserialised JSON payload from the endpoint.  Expected to be a
        ``list``, but any value is handled without raising.
    """
    if not isinstance(raw, list):
        return ParseOutcome(
            events=(),
            is_valid_payload=False,
            raw_count=0,
            parsed_count=0,
            malformed_count=0,
            filtered_status_count=0,
        )

    raw_count = len(raw)
    malformed_count = 0
    filtered_status_count = 0
    passed: list[OutageEvent] = []

    for item in raw:
        if not isinstance(item, dict):
            malformed_count += 1
            continue
        event = parse_event(item)
        if event is None:
            malformed_count += 1
            continue
        if _is_excluded_status(item):
            filtered_status_count += 1
            continue
        passed.append(event)

    deduped = _deduplicate_events(passed)

    return ParseOutcome(
        events=tuple(deduped),
        is_valid_payload=True,
        raw_count=raw_count,
        parsed_count=raw_count - malformed_count,
        malformed_count=malformed_count,
        filtered_status_count=filtered_status_count,
    )


# ---------------------------------------------------------------------------
# Public API — compatibility shim
# ---------------------------------------------------------------------------


def parse_events(raw_list: list[Any]) -> list[OutageEvent]:
    """Parse a raw payload list into deduplicated events (status-active only).

    .. deprecated::
        Prefer :func:`parse_payload` for new code.  This function exists for
        backward compatibility and simply returns
        ``list(parse_payload(raw_list).events)``.
    """
    return list(parse_payload(raw_list).events)
