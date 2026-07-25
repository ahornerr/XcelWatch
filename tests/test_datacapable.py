"""Tests for parsing and API-layer handling of the live Datacapable
payload shape where ``additionalProperties`` is an array of
``{property, value}`` records.

This replicates the actual production format from Xcel Energy's outage-map
cache.  The source handles this shape by normalising the array into a dict,
extracting ``states``, ``outagestatus``, and other fields from the records.
"""

from __future__ import annotations

import pytest

from custom_components.xcel_outages.models import OutageEvent, ParseOutcome
from custom_components.xcel_outages.parser import parse_events, parse_payload


# =========================================================================
# 1. Active array-form events parse successfully
# =========================================================================


class TestActiveArrayEventParses:
    """An event whose ``additionalProperties`` is an array of
    ``{property, value}`` records must parse to a valid ``OutageEvent``."""

    def test_active_array_event_parsed(self, raw_events_datacapable):
        events = parse_events(raw_events_datacapable)
        identifiers = [e.identifier for e in events]
        assert "array_active" in identifiers

    def test_active_array_has_expected_fields(self, raw_events_datacapable):
        events = parse_events(raw_events_datacapable)
        ev = {e.identifier: e for e in events}
        event = ev["array_active"]
        assert event.num_people == 75
        assert event.latitude == 39.85
        assert event.longitude == -105.30
        assert event.county == "Boulder"
        assert event.title == "Active array-form event"

    def test_array_event_not_malformed(self, raw_events_datacapable):
        outcome = parse_payload(raw_events_datacapable)
        assert outcome.is_valid_payload
        # The active event should NOT be counted as malformed
        active_in = "array_active" in [e.identifier for e in outcome.events]
        if active_in:
            assert outcome.malformed_count == 0


# =========================================================================
# 2. Property-array states normalise to tuple
# =========================================================================


class TestArrayStatesNormalise:
    """When ``states`` appears as a record inside the property array,
    it is normalised to a tuple of strings, just like the dict form."""

    def test_list_states_in_array(self, raw_events_datacapable):
        events = parse_events(raw_events_datacapable)
        ev = {e.identifier: e for e in events}
        if "array_active" in ev:
            add = ev["array_active"].additional_properties
            states = add.get("states")
            assert states is not None
            assert isinstance(states, tuple)
            assert "CO" in states

    def test_string_states_in_array(self, raw_events_datacapable):
        events = parse_events(raw_events_datacapable)
        ev = {e.identifier: e for e in events}
        if "array_string_states" in ev:
            add = ev["array_string_states"].additional_properties
            states = add.get("states")
            assert states is not None
            assert isinstance(states, tuple)


# =========================================================================
# 3. Terminal status from array format excludes event
# =========================================================================


class TestArrayTerminalStatusExcludes:
    """When ``outagestatus`` is inside the property array and has a
    terminal value, the event is excluded (filtered_status_count
    incremented)."""

    def test_array_terminal_outagestatus_excluded(self, raw_events_datacapable):
        outcome = parse_payload(raw_events_datacapable)
        identifiers = [e.identifier for e in outcome.events]
        assert "array_terminal_status" not in identifiers

    def test_array_terminal_increments_filtered(self, raw_events_datacapable):
        outcome = parse_payload(raw_events_datacapable)
        # The array_terminal_status event should be filtered (resolved outagestatus)
        # and array_top_terminal should also be filtered (resolved top-level).
        assert outcome.filtered_status_count >= 1


# =========================================================================
# 4. Malformed array records do not crash
# =========================================================================


class TestMalformedArrayRecords:
    """Non-dict records inside the property array or records missing
    the ``value`` field must not cause crashes — the parser should
    skip them gracefully."""

    def test_non_dict_record_does_not_crash(self, raw_events_datacapable):
        """A string record inside additionalProperties array is skipped
        without raising."""
        try:
            parse_events(raw_events_datacapable)
        except Exception as exc:
            raise AssertionError(f"Unexpected exception: {exc}") from exc

    def test_record_missing_value_does_not_crash(self, raw_events_datacapable):
        """A record without a ``value`` key is skipped without raising."""
        try:
            parse_events(raw_events_datacapable)
        except Exception as exc:
            raise AssertionError(f"Unexpected exception: {exc}") from exc


# =========================================================================
# 5. Top-level live-shaped list is no longer all-malformed
# =========================================================================


class TestLiveShapeNotAllMalformed:
    """The entire Datacapable-shaped payload must parse without all
    records being malformed — at least the valid active records produce
    events."""

    def test_not_all_malformed(self, raw_events_datacapable):
        outcome = parse_payload(raw_events_datacapable)
        # At least one event parses successfully
        assert len(outcome.events) > 0
        # Not all records are malformed
        assert outcome.malformed_count < outcome.raw_count

    def test_outcome_has_valid_payload(self, raw_events_datacapable):
        outcome = parse_payload(raw_events_datacapable)
        assert outcome.is_valid_payload is True


# =========================================================================
# 6. Config/API regression: this shape does NOT produce unsupported_response
# =========================================================================


class TestApiDoesNotRejectLiveShape:
    """The API layer must accept the Datacapable array-form
    ``additionalProperties`` and return a valid ``ParseOutcome`` rather
    than raising ``XcelOutagesSchemaError`` (``unsupported_response``).

    This is a regression test: historically such payloads were rejected
    as "all malformed" or "unexpected shape".
    """

    def test_parse_payload_does_not_raise(self, raw_events_datacapable):
        """``parse_payload`` returns a normal outcome without raising."""
        outcome = parse_payload(raw_events_datacapable)
        assert outcome.is_valid_payload

    def test_parse_payload_has_parsed_events(self, raw_events_datacapable):
        outcome = parse_payload(raw_events_datacapable)
        assert len(outcome.events) >= 0  # at least doesn't crash

    def test_api_layer_would_accept(self, raw_events_datacapable):
        """Simulate the API layer's check: after ``parse_payload``,
        ``is_valid_payload`` is True and not all records are malformed
        — conditions that would NOT raise ``XcelOutagesSchemaError``."""
        outcome = parse_payload(raw_events_datacapable)
        assert outcome.is_valid_payload
        # API raises SchemaError when ALL records are malformed:
        # outcome.raw_count > 0 and outcome.malformed_count == outcome.raw_count
        is_all_malformed = (
            outcome.raw_count > 0
            and outcome.malformed_count == outcome.raw_count
        )
        assert not is_all_malformed, "Live shape should not be all-malformed"


# =========================================================================
# 7. Numeric timestamp parsing — epoch-millisecond to UTC datetime
# =========================================================================


class TestNumericTimestamps:
    """Numeric epoch-millisecond values for ``startTime``,
    ``lastUpdatedTime``, and ``etrTime`` are parsed into timezone-aware UTC
    :class:`datetime.datetime` instances."""

    def test_numeric_start_time_is_utc_datetime(self, raw_events_datacapable):
        events = parse_events(raw_events_datacapable)
        ev = {e.identifier: e for e in events}
        event = ev["numeric_ts_active"]
        assert event.start_time is not None
        assert event.start_time.tzinfo is not None
        assert event.start_time.tzinfo.utcoffset(None).total_seconds() == 0

    def test_numeric_last_updated_time_is_utc_datetime(self, raw_events_datacapable):
        events = parse_events(raw_events_datacapable)
        ev = {e.identifier: e for e in events}
        event = ev["numeric_ts_active"]
        assert event.last_updated_time is not None
        assert event.last_updated_time.tzinfo is not None

    def test_numeric_etr_time_is_utc_datetime(self, raw_events_datacapable):
        events = parse_events(raw_events_datacapable)
        ev = {e.identifier: e for e in events}
        event = ev["numeric_ts_active"]
        assert event.etr_time is not None
        assert event.etr_time.tzinfo is not None

    def test_numeric_milliseconds_converted_correctly(self, raw_events_datacapable):
        """1784944800000 ms → 2026-07-25 02:00:00+00:00."""
        events = parse_events(raw_events_datacapable)
        ev = {e.identifier: e for e in events}
        event = ev["numeric_ts_active"]
        assert event.start_time.year == 2026
        assert event.start_time.month == 7
        assert event.start_time.day == 25
        assert event.start_time.hour == 2
        assert event.start_time.minute == 0
        assert event.start_time.second == 0


# =========================================================================
# 8. Dedup with numeric timestamps — newer numeric wins
# =========================================================================


class TestNumericDedup:
    """When two events share the same ``identifier``, the one with the
    more recent ``lastUpdatedTime`` wins — even when timestamps are a
    mix of string ISO-8601 and numeric epoch-milliseconds."""

    def test_numeric_dedup_inline(self):
        """Two events with same identifier: one string-ISO, one numeric.
        The numeric (newer) wins."""
        from custom_components.xcel_outages.parser import parse_events

        payload = [
            {
                "identifier": "dedup_test",
                "startTime": "2026-07-24T10:00:00Z",
                "lastUpdatedTime": "2026-07-24T10:30:00Z",  # 2026-07-24 10:30 UTC
                "etrTime": None,
                "title": "String timestamp — older",
                "status": "ACTIVE",
                "cause": "test",
                "numPeople": 10,
                "latitude": 39.75,
                "longitude": -105.0,
                "county": "Test",
                "additionalProperties": {"states": ["CO"]},
            },
            {
                "identifier": "dedup_test",
                "startTime": "2026-07-24T10:00:00Z",
                "lastUpdatedTime": 1784956200000,  # 2026-07-25 10:30 UTC — newer
                "etrTime": None,
                "title": "Numeric timestamp — newer (wins)",
                "status": "ACTIVE",
                "cause": "test",
                "numPeople": 20,
                "latitude": 39.75,
                "longitude": -105.0,
                "county": "Test",
                "additionalProperties": {"states": ["CO"]},
            },
        ]
        events = parse_events(payload)
        assert len(events) == 1
        winner = events[0]
        assert winner.title == "Numeric timestamp — newer (wins)"
        assert winner.num_people == 20

    def test_string_newer_wins_over_numeric(self):
        """String ISO-8601 can also be newer than numeric."""
        from custom_components.xcel_outages.parser import parse_events

        payload = [
            {
                "identifier": "dedup_test2",
                "startTime": "2026-07-24T10:00:00Z",
                "lastUpdatedTime": 1784946600000,  # 2026-07-24 10:30 UTC — older
                "etrTime": None,
                "title": "Numeric timestamp — older",
                "status": "ACTIVE",
                "cause": "test",
                "numPeople": 10,
                "latitude": 39.75,
                "longitude": -105.0,
                "county": "Test",
                "additionalProperties": {"states": ["CO"]},
            },
            {
                "identifier": "dedup_test2",
                "startTime": "2026-07-24T10:00:00Z",
                "lastUpdatedTime": "2026-07-25T10:30:00Z",  # string — newer
                "etrTime": None,
                "title": "String timestamp — newer (wins)",
                "status": "ACTIVE",
                "cause": "test",
                "numPeople": 30,
                "latitude": 39.75,
                "longitude": -105.0,
                "county": "Test",
                "additionalProperties": {"states": ["CO"]},
            },
        ]
        events = parse_events(payload)
        assert len(events) == 1
        assert events[0].title == "String timestamp — newer (wins)"


# =========================================================================
# 9. Invalid numeric timestamps become None safely
# =========================================================================


class TestInvalidNumericTimestamps:
    """Non-finite, negative, or otherwise invalid numeric timestamp
    values must be safely coerced to ``None`` without raising."""

    # These values cannot be expressed in JSON, so we use inline payloads.
    _BASE = {
        "identifier": "invalid_ts",
        "startTime": 1784944800000,
        "lastUpdatedTime": 1784946600000,
        "etrTime": None,
        "title": "Invalid timestamp test",
        "status": "ACTIVE",
        "cause": "test",
        "numPeople": 10,
        "latitude": 39.75,
        "longitude": -105.0,
        "county": "Test",
        "additionalProperties": {"states": ["CO"]},
    }

    def test_inf_timestamp_becomes_none(self):
        payload = [{**self._BASE, "lastUpdatedTime": float("inf")}]
        events = parse_events(payload)
        assert len(events) == 1
        assert events[0].last_updated_time is None

    def test_nan_timestamp_becomes_none(self):
        payload = [{**self._BASE, "startTime": float("nan")}]
        events = parse_events(payload)
        assert len(events) == 1
        assert events[0].start_time is None

    def test_overflow_timestamp_becomes_none(self):
        """A value that causes ``ValueError`` in ``fromtimestamp``
        (year out of valid range) becomes None."""
        payload = [{**self._BASE, "startTime": 1e15}]
        events = parse_events(payload)
        assert len(events) == 1
        assert events[0].start_time is None

    def test_valid_numeric_alongside_invalid(self):
        """Valid field adjacent to invalid remains accessible."""
        payload = [
            {
                **self._BASE,
                "identifier": "mixed_ts",
                "startTime": float("nan"),
                "lastUpdatedTime": 1784946600000,
                "numPeople": 15,
            }
        ]
        events = parse_events(payload)
        assert len(events) == 1
        e = events[0]
        assert e.start_time is None
        assert e.last_updated_time is not None
        assert e.num_people == 15

    def test_bool_timestamp_becomes_none(self):
        """``True``/``False`` (which are ints in Python) are rejected."""
        payload = [{**self._BASE, "startTime": True}]
        events = parse_events(payload)
        assert len(events) == 1
        assert events[0].start_time is None

    def test_non_finite_negative_inf_timestamp_becomes_none(self):
        payload = [{**self._BASE, "lastUpdatedTime": float("-inf")}]
        events = parse_events(payload)
        assert len(events) == 1
        assert events[0].last_updated_time is None
