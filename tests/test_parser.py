"""Tests for the parser module.

Target module: ``custom_components.xcel_outages.parser``.

The public API is :func:`parse_events`, which accepts a raw JSON-decoded value
and returns a ``list[OutageEvent]`` of normalised, **territory-neutral**,
active-only, deduplicated events as specified in ``docs/scoring-contract.md`` §1.

Events are included based on geographic validity (finite in-range coordinates),
not by state/territory.  Terminal statuses (resolved/closed/cancelled) are
excluded.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from custom_components.xcel_outages.parser import parse_events


# =========================================================================
# 1. Top-level validation — structured parse outcomes
# =========================================================================


class TestTopLevelValidation:
    """parse_events() must handle non-list and empty-list inputs gracefully."""

    def test_valid_empty_list_returns_empty(self, raw_events_valid_empty):
        result = parse_events(raw_events_valid_empty)
        assert isinstance(result, list)
        assert len(result) == 0

    def test_invalid_top_level_non_list_returns_empty(self, raw_events_non_list):
        result = parse_events(raw_events_non_list)
        assert isinstance(result, list)
        assert len(result) == 0

    def test_invalid_top_level_none_returns_empty(self):
        result = parse_events(None)
        assert isinstance(result, list)
        assert len(result) == 0

    def test_all_malformed_records_returns_empty(self, raw_events_all_malformed):
        result = parse_events(raw_events_all_malformed)
        assert isinstance(result, list)
        assert len(result) == 0


# =========================================================================
# 2. Event validation — non-dict entries are skipped
# =========================================================================


class TestEventValidation:
    """Non-dict entries in the payload list must be skipped silently."""

    def test_skip_non_dict_entries(self, raw_events_malformed):
        result = parse_events(raw_events_malformed)
        identifiers = [e.identifier for e in result]
        assert "good01" in identifiers
        assert "not_a_dict" not in identifiers

    def test_valid_filtered_records_preserved(self, raw_events_small_nearby):
        result = parse_events(raw_events_small_nearby)
        assert len(result) == 2
        identifiers = [e.identifier for e in result]
        assert "e001" in identifiers
        assert "e002" in identifiers


# =========================================================================
# 3. Territory-neutral parsing — non-CO events are NOT excluded
# =========================================================================


class TestTerritoryNeutral:
    """Events from any location (state, territory) are parsed and returned.
    The parser does NOT filter by Colorado or any specific region —
    geographic inclusion is handled downstream by distance-based scoring."""

    def test_non_colorado_event_included(self, raw_events_states_string):
        """MN-only event must be included (territory-neutral)."""
        result = parse_events(raw_events_states_string)
        identifiers = [e.identifier for e in result]
        assert "non_co_list" in identifiers

    def test_missing_states_not_excluded(self, raw_events_states_string):
        """Event with no 'states' key must be included."""
        result = parse_events(raw_events_states_string)
        identifiers = [e.identifier for e in result]
        assert "no_state" in identifiers

    def test_empty_states_list_included(self, raw_events_states_string):
        """Empty states list must be included."""
        result = parse_events(raw_events_states_string)
        identifiers = [e.identifier for e in result]
        assert "empty_states_list" in identifiers

    def test_string_states_normalised(self, raw_events_states_string):
        result = parse_events(raw_events_states_string)
        ev = {e.identifier: e for e in result}
        assert "str_state_co" in ev
        states = ev["str_state_co"].additional_properties["states"]
        assert isinstance(states, tuple)

    def test_list_states_normalised(self, raw_events_states_string):
        result = parse_events(raw_events_states_string)
        ev = {e.identifier: e for e in result}
        assert "list_state" in ev
        states = ev["list_state"].additional_properties["states"]
        assert isinstance(states, tuple)

    def test_all_seven_events_parsed(self, raw_events_states_string):
        """All 7 events (CO, non-CO, missing, empty states) are parsed
        when none have terminal statuses."""
        result = parse_events(raw_events_states_string)
        assert len(result) == 7


# =========================================================================
# 4. Status exclusion — terminal statuses still exclude
# =========================================================================


class TestStatusExclusion:
    """Events with resolved/closed/cancelled status (top-level or
    additionalProperties.outagestatus) must be excluded."""

    def test_active_retained(self, raw_events_outagestatus):
        result = parse_events(raw_events_outagestatus)
        identifiers = [e.identifier for e in result]
        assert "active_active" in identifiers

    def test_resolved_top_level_excluded(self, raw_events_outagestatus):
        result = parse_events(raw_events_outagestatus)
        identifiers = [e.identifier for e in result]
        assert "resolved_resolved" not in identifiers
        assert "top_resolved_outage_active" not in identifiers

    def test_resolved_outagestatus_excluded(self, raw_events_outagestatus):
        result = parse_events(raw_events_outagestatus)
        identifiers = [e.identifier for e in result]
        assert "top_active_outage_resolved" not in identifiers

    def test_resolved_excluded(self, raw_events_resolved):
        result = parse_events(raw_events_resolved)
        identifiers = [e.identifier for e in result]
        assert "active_01" in identifiers
        assert "resolved_01" not in identifiers
        assert "closed_01" not in identifiers
        assert "cancelled_01" not in identifiers

    def test_lowercase_resolved_excluded(self, raw_events_resolved):
        result = parse_events(raw_events_resolved)
        identifiers = [e.identifier for e in result]
        assert "resolved_case_02" not in identifiers


# =========================================================================
# 5. Bool / non-finite / fractional input rejection
# =========================================================================


class TestBoolNonFiniteFractionalRejection:
    """Boolean, non-finite, and fractional inputs must be rejected
    without raising exceptions."""

    def test_bool_identifier_skipped(self, raw_events_bool_nonfinite):
        result = parse_events(raw_events_bool_nonfinite)
        identifiers = [e.identifier for e in result]
        assert True not in identifiers

    def test_bool_numpeople_skipped(self, raw_events_bool_nonfinite):
        result = parse_events(raw_events_bool_nonfinite)
        identifiers = [e.identifier for e in result]
        assert "bool_numpeople" not in identifiers

    def test_fractional_numpeople_skipped(self, raw_events_bool_nonfinite):
        result = parse_events(raw_events_bool_nonfinite)
        identifiers = [e.identifier for e in result]
        assert "frac_numpeople" not in identifiers

    def test_inf_latitude_skipped(self, raw_events_bool_nonfinite):
        result = parse_events(raw_events_bool_nonfinite)
        identifiers = [e.identifier for e in result]
        assert "inf_lat" not in identifiers

    def test_nan_longitude_skipped(self, raw_events_bool_nonfinite):
        result = parse_events(raw_events_bool_nonfinite)
        identifiers = [e.identifier for e in result]
        assert "nan_lon" not in identifiers

    def test_no_exception_raised(self, raw_events_bool_nonfinite):
        try:
            parse_events(raw_events_bool_nonfinite)
        except Exception as exc:
            raise AssertionError(
                f"parse_events raised unexpected exception: {exc}"
            ) from exc


# =========================================================================
# 6. Malformed event handling — missing/bad coords, bad numPeople
# =========================================================================


class TestMalformedCoordinateHandling:
    """Events with missing or non-numeric coordinates must be skipped."""

    def test_missing_coordinates_skipped(self, raw_events_malformed):
        result = parse_events(raw_events_malformed)
        identifiers = [e.identifier for e in result]
        assert "missing_coords" not in identifiers

    def test_bad_latitude_skipped(self, raw_events_malformed):
        result = parse_events(raw_events_malformed)
        identifiers = [e.identifier for e in result]
        assert "bad_lat" not in identifiers

    def test_bad_longitude_skipped(self, raw_events_malformed):
        result = parse_events(raw_events_malformed)
        identifiers = [e.identifier for e in result]
        assert "bad_lon" not in identifiers


class TestNumPeopleHandling:
    """Events with missing or non-integer numPeople must be skipped."""

    def test_non_integer_numpeople_skipped(self, raw_events_malformed):
        result = parse_events(raw_events_malformed)
        identifiers = [e.identifier for e in result]
        assert "non_integer_people" not in identifiers

    def test_missing_numpeople_skipped(self, raw_events_malformed):
        result = parse_events(raw_events_malformed)
        identifiers = [e.identifier for e in result]
        assert "missing_people" not in identifiers

    def test_valid_numpeople_preserved(self, raw_events_malformed):
        result = parse_events(raw_events_malformed)
        identifiers = [e.identifier for e in result]
        assert "good01" in identifiers
        good = [e for e in result if e.identifier == "good01"][0]
        assert good.num_people == 50


class TestAdditionalPropertiesHandling:
    """Missing additionalProperties does NOT exclude (territory-neutral)."""

    def test_missing_additional_properties_included(self, raw_events_malformed):
        """Event 'no_addl_props' lacks additionalProperties but is still
        valid — territory-neutral parsing does not require it."""
        result = parse_events(raw_events_malformed)
        identifiers = [e.identifier for e in result]
        assert "no_addl_props" in identifiers


# =========================================================================
# 7. Deduplication
# =========================================================================


class TestDeduplication:
    """Duplicate identifiers — event with most recent last_updated_time wins."""

    def test_later_timestamp_wins(self, raw_events_dedup):
        result = parse_events(raw_events_dedup)
        ev = {e.identifier: e for e in result}
        assert "dup01" in ev
        assert ev["dup01"].num_people == 200
        assert ev["dup01"].title == "Second instance (later wins)"

    def test_unique_event_preserved(self, raw_events_dedup):
        result = parse_events(raw_events_dedup)
        ev = {e.identifier: e for e in result}
        assert "dup02" in ev
        assert ev["dup02"].num_people == 50

    def test_dedup_reduces_count(self, raw_events_dedup):
        result = parse_events(raw_events_dedup)
        assert len(result) == 2


# =========================================================================
# 8. Output shape — OutageEvent fields
# =========================================================================


class TestOutageEventShape:
    """Parsed events must be OutageEvent instances with expected attributes."""

    def test_is_outage_event_instance(self, raw_events_small_nearby):
        from custom_components.xcel_outages.models import OutageEvent

        result = parse_events(raw_events_small_nearby)
        for event in result:
            assert isinstance(event, OutageEvent)

    def test_expected_attributes_present(self, raw_events_small_nearby):
        result = parse_events(raw_events_small_nearby)
        for event in result:
            assert isinstance(event.identifier, str)
            assert event.start_time is None or isinstance(event.start_time, datetime)
            assert event.last_updated_time is None or isinstance(
                event.last_updated_time, datetime
            )
            assert event.etr_time is None or isinstance(event.etr_time, datetime)
            assert isinstance(event.title, str)
            assert isinstance(event.status, str)
            assert isinstance(event.cause, str)
            assert isinstance(event.num_people, int)
            assert isinstance(event.latitude, float)
            assert isinstance(event.longitude, float)
            assert isinstance(event.county, str)
            assert isinstance(event.additional_properties, Mapping)

    def test_states_immutable(self, raw_events_small_nearby):
        result = parse_events(raw_events_small_nearby)
        for event in result:
            states = event.additional_properties.get("states")
            if states is not None:
                assert isinstance(states, tuple), (
                    f"states should be tuple, got {type(states)}"
                )

    def test_status_preserved(self, raw_events_small_nearby):
        result = parse_events(raw_events_small_nearby)
        for event in result:
            assert isinstance(event.status, str)


# =========================================================================
# 9. Privacy — no home coordinates in parser output
# =========================================================================


class TestParserPrivacy:
    """Parser output must never contain home coordinate fields."""

    def test_no_home_coordinate_attributes(self, raw_events_small_nearby):
        result = parse_events(raw_events_small_nearby)
        for event in result:
            assert not hasattr(event, "home_lat")
            assert not hasattr(event, "home_lon")
            assert not hasattr(event, "home_latitude")
            assert not hasattr(event, "home_longitude")
            assert not hasattr(event, "home_coordinates")
