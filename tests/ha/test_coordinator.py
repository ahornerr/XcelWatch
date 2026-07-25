"""Tests for the ``XcelOutagesCoordinator``.

Tests coordinate resolution, data refresh, UpdateFailed propagation, and
data retention after failures — all exercised **through the public API**
(``async_refresh`` / ``async_refresh``) rather than the
private ``_async_update_data``.

The ``DataUpdateCoordinator`` base class manages the ``data`` and
``last_update_success`` properties based on the outcome of
``_async_update_data``.  Tests verify this contract rather than
assuming the private method mutates those attributes directly.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.xcel_outages.const import (
    CONF_LATITUDE_OVERRIDE,
    CONF_LOCAL_RADIUS,
    CONF_LONGITUDE_OVERRIDE,
    CONF_MATERIAL_THRESHOLD,
    CONF_POLL_INTERVAL,
    CONF_SEARCH_RADIUS,
    CONF_USE_HOME_LOCATION,
    DEFAULT_LOCAL_RADIUS,
    DEFAULT_MATERIAL_THRESHOLD,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_SEARCH_RADIUS,
    DOMAIN,
)
from custom_components.xcel_outages.models import ParseOutcome, RiskContext

pytestmark = pytest.mark.hass


# =========================================================================
# Helpers
# =========================================================================


def _empty_outcome() -> ParseOutcome:
    """Valid empty parse outcome — no events in the system."""
    return ParseOutcome(
        events=(),
        is_valid_payload=True,
        raw_count=0,
        parsed_count=0,
        malformed_count=0,
        filtered_status_count=0,
    )


_FULL_OPTIONS = {
    CONF_SEARCH_RADIUS: DEFAULT_SEARCH_RADIUS,
    CONF_LOCAL_RADIUS: DEFAULT_LOCAL_RADIUS,
    CONF_MATERIAL_THRESHOLD: DEFAULT_MATERIAL_THRESHOLD,
    CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL,
}


# =========================================================================
# 1. Coordinate resolution
# =========================================================================


class TestCoordinateResolution:
    """``_get_home_coordinates`` resolves HA location vs. override."""

    async def test_uses_ha_location_by_default(self, hass):
        """When ``use_home_location`` is True, reads from ``hass.config``."""
        hass.config.latitude = 40.0
        hass.config.longitude = -105.0

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_USE_HOME_LOCATION: True},
            options=_FULL_OPTIONS,
            entry_id="coord_test_1",
        )
        entry.add_to_hass(hass)
        coordinator = XcelOutagesCoordinator(hass, entry)

        lat, lon = coordinator._get_home_coordinates()
        assert lat == 40.0
        assert lon == -105.0

    async def test_uses_override_when_not_using_ha_location(self, hass):
        """When ``use_home_location`` is False, reads entry data."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                CONF_USE_HOME_LOCATION: False,
                CONF_LATITUDE_OVERRIDE: 39.7392,
                CONF_LONGITUDE_OVERRIDE: -104.9903,
            },
            options=_FULL_OPTIONS,
            entry_id="coord_test_2",
        )
        entry.add_to_hass(hass)
        coordinator = XcelOutagesCoordinator(hass, entry)

        lat, lon = coordinator._get_home_coordinates()
        assert lat == 39.7392
        assert lon == -104.9903

    async def test_ha_location_change_reflected_at_runtime(self, hass):
        """Runtime changes to ``hass.config`` are picked up."""
        hass.config.latitude = 40.0
        hass.config.longitude = -105.0

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_USE_HOME_LOCATION: True},
            options=_FULL_OPTIONS,
            entry_id="coord_test_3",
        )
        entry.add_to_hass(hass)
        coordinator = XcelOutagesCoordinator(hass, entry)

        lat, lon = coordinator._get_home_coordinates()
        assert lat == 40.0

        hass.config.latitude = 41.0
        hass.config.longitude = -110.0

        lat, lon = coordinator._get_home_coordinates()
        assert lat == 41.0
        assert lon == -110.0


# =========================================================================
# 2. Successful first refresh (via async_refresh)
# =========================================================================


class TestSuccessfulFirstRefresh:
    """``async_refresh`` populates data and sets ``last_update_success``.

    We use ``async_refresh`` rather than
    ``async_refresh`` because the latter requires
    that the coordinator is owned by a config entry managed through
    ``async_setup_entry`` — unit tests create the coordinator manually.
    """

    async def test_first_refresh_sets_data(self, hass):
        """After a successful refresh, ``coordinator.data`` is a
        ``RiskContext`` and ``last_update_success`` is True."""
        hass.config.latitude = 39.7555
        hass.config.longitude = -105.2211

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_USE_HOME_LOCATION: True},
            options=_FULL_OPTIONS,
            entry_id="refresh_test_1",
        )
        entry.add_to_hass(hass)
        coordinator = XcelOutagesCoordinator(hass, entry)

        with patch.object(
            coordinator._api, "fetch_events", return_value=_empty_outcome()
        ):
            await coordinator.async_refresh()

        assert coordinator.last_update_success is True
        assert isinstance(coordinator.data, RiskContext)
        assert coordinator.data.risk == 0
        assert coordinator.data.band == "None"

    async def test_first_refresh_with_custom_options(self, hass):
        """Custom options are passed through to scoring."""
        hass.config.latitude = 39.7555
        hass.config.longitude = -105.2211

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_USE_HOME_LOCATION: True},
            options={
                CONF_SEARCH_RADIUS: 50,
                CONF_LOCAL_RADIUS: 20,
                CONF_MATERIAL_THRESHOLD: 100,
                CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL,
            },
            entry_id="refresh_test_2",
        )
        entry.add_to_hass(hass)
        coordinator = XcelOutagesCoordinator(hass, entry)

        with patch.object(
            coordinator._api, "fetch_events", return_value=_empty_outcome()
        ):
            await coordinator.async_refresh()

        assert coordinator.last_update_success is True
        assert isinstance(coordinator.data, RiskContext)


# =========================================================================
# 3. Subsequent refresh (via async_refresh)
# =========================================================================


class TestSubsequentRefresh:
    """``async_refresh`` updates data and preserves success state."""

    async def test_refresh_updates_data(self, hass):
        hass.config.latitude = 39.7555
        hass.config.longitude = -105.2211

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_USE_HOME_LOCATION: True},
            options=_FULL_OPTIONS,
            entry_id="refresh_sub_1",
        )
        entry.add_to_hass(hass)
        coordinator = XcelOutagesCoordinator(hass, entry)

        with patch.object(
            coordinator._api, "fetch_events", return_value=_empty_outcome()
        ):
            await coordinator.async_refresh()

        first_data = coordinator.data
        assert first_data is not None

        # Second refresh with same data
        with patch.object(
            coordinator._api, "fetch_events", return_value=_empty_outcome()
        ):
            await coordinator.async_refresh()

        # Data may be the same (risk 0) but last_update_success must be True
        assert coordinator.last_update_success is True
        assert coordinator.data is not None


# =========================================================================
# 4. UpdateFailed handling (public API)
# =========================================================================


class TestUpdateFailed:
    """On API failure the coordinator catches the error, sets
    ``last_update_success = False``, and retains previous data."""

    async def test_first_refresh_failure_sets_last_update_false(self, hass):
        """If the initial refresh fails, ``last_update_success`` is False
        and ``data`` remains None."""
        from custom_components.xcel_outages.api import XcelOutagesConnectionError

        hass.config.latitude = 39.7555
        hass.config.longitude = -105.2211

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_USE_HOME_LOCATION: True},
            options=_FULL_OPTIONS,
            entry_id="fail_test_1",
        )
        entry.add_to_hass(hass)
        coordinator = XcelOutagesCoordinator(hass, entry)

        with patch.object(
            coordinator._api,
            "fetch_events",
            side_effect=XcelOutagesConnectionError("Network unreachable"),
        ):
            # async_refresh does NOT re-raise
            # UpdateFailed — it catches it and sets last_update_success
            await coordinator.async_refresh()

        assert coordinator.last_update_success is False
        assert coordinator.data is None  # no prior data to retain

    async def test_subsequent_refresh_preserves_old_data(self, hass):
        """After a successful refresh, a subsequent failure retains the
        last good data and sets ``last_update_success`` to False."""
        from custom_components.xcel_outages.api import XcelOutagesConnectionError

        hass.config.latitude = 39.7555
        hass.config.longitude = -105.2211

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_USE_HOME_LOCATION: True},
            options=_FULL_OPTIONS,
            entry_id="fail_test_2",
        )
        entry.add_to_hass(hass)
        coordinator = XcelOutagesCoordinator(hass, entry)

        # Successful first fetch
        with patch.object(
            coordinator._api, "fetch_events", return_value=_empty_outcome()
        ):
            await coordinator.async_refresh()

        assert coordinator.last_update_success is True
        first_data = coordinator.data

        # Failed subsequent fetch
        with patch.object(
            coordinator._api,
            "fetch_events",
            side_effect=XcelOutagesConnectionError("Timeout"),
        ):
            await coordinator.async_refresh()

        assert coordinator.last_update_success is False
        # The old data must be preserved
        assert coordinator.data is first_data

    async def test_schema_error_sets_last_update_false(self, hass):
        """``XcelOutagesSchemaError`` is also translated to
        ``last_update_success = False``."""
        from custom_components.xcel_outages.api import XcelOutagesSchemaError

        hass.config.latitude = 39.7555
        hass.config.longitude = -105.2211

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_USE_HOME_LOCATION: True},
            options=_FULL_OPTIONS,
            entry_id="fail_test_3",
        )
        entry.add_to_hass(hass)
        coordinator = XcelOutagesCoordinator(hass, entry)

        with patch.object(
            coordinator._api,
            "fetch_events",
            side_effect=XcelOutagesSchemaError("Bad data"),
        ):
            await coordinator.async_refresh()

        assert coordinator.last_update_success is False


# =========================================================================
# 5. Invalid schema / all-malformed → NOT risk 0
# =========================================================================


class TestInvalidSchemaNotRiskZero:
    """When the API response is invalid, ``last_update_success`` becomes
    False — the coordinator does NOT return risk 0."""

    async def test_non_list_payload_sets_update_false(self, hass):
        """Non-list payload leads to failed refresh, not risk 0."""
        from custom_components.xcel_outages.api import XcelOutagesSchemaError

        hass.config.latitude = 39.7555
        hass.config.longitude = -105.2211

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_USE_HOME_LOCATION: True},
            options=_FULL_OPTIONS,
            entry_id="schema_test_1",
        )
        entry.add_to_hass(hass)
        coordinator = XcelOutagesCoordinator(hass, entry)

        with patch.object(
            coordinator._api,
            "fetch_events",
            side_effect=XcelOutagesSchemaError("Payload is not a list"),
        ):
            await coordinator.async_refresh()

        assert coordinator.last_update_success is False
        # Must NOT be risk 0 — data stays None
        assert coordinator.data is None

    async def test_all_malformed_sets_update_false(self, hass):
        """All records malformed → failed refresh, not risk 0."""
        from custom_components.xcel_outages.api import XcelOutagesSchemaError

        hass.config.latitude = 39.7555
        hass.config.longitude = -105.2211

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_USE_HOME_LOCATION: True},
            options=_FULL_OPTIONS,
            entry_id="schema_test_2",
        )
        entry.add_to_hass(hass)
        coordinator = XcelOutagesCoordinator(hass, entry)

        with patch.object(
            coordinator._api,
            "fetch_events",
            side_effect=XcelOutagesSchemaError("All records malformed"),
        ):
            await coordinator.async_refresh()

        assert coordinator.last_update_success is False


# =========================================================================
# 6. Valid empty / filtered response → risk 0
# =========================================================================


class TestValidEmptyReturnsRiskZero:
    """A valid empty or status-filtered response yields risk 0 (no
    actionable events)."""

    async def test_empty_list_returns_risk_zero(self, hass):
        """Valid empty list → risk 0."""
        hass.config.latitude = 39.7555
        hass.config.longitude = -105.2211

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_USE_HOME_LOCATION: True},
            options=_FULL_OPTIONS,
            entry_id="empty_test_1",
        )
        entry.add_to_hass(hass)
        coordinator = XcelOutagesCoordinator(hass, entry)

        with patch.object(
            coordinator._api, "fetch_events", return_value=_empty_outcome()
        ):
            await coordinator.async_refresh()

        assert coordinator.last_update_success is True
        assert coordinator.data is not None
        assert coordinator.data.risk == 0
        assert coordinator.data.band == "None"

    async def test_filtered_out_events_returns_risk_zero(self, hass):
        """Records exist but all filtered (status-filtered) → risk 0."""
        filtered_outcome = ParseOutcome(
            events=(),
            is_valid_payload=True,
            raw_count=5,
            parsed_count=5,
            malformed_count=0,
            filtered_status_count=5,
        )

        hass.config.latitude = 39.7555
        hass.config.longitude = -105.2211

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_USE_HOME_LOCATION: True},
            options=_FULL_OPTIONS,
            entry_id="empty_test_2",
        )
        entry.add_to_hass(hass)
        coordinator = XcelOutagesCoordinator(hass, entry)

        with patch.object(
            coordinator._api,
            "fetch_events",
            return_value=filtered_outcome,
        ):
            await coordinator.async_refresh()

        assert coordinator.last_update_success is True
        assert coordinator.data is not None
        assert coordinator.data.risk == 0


# =========================================================================
# 7. Privacy — no home coordinates in coordinator state
# =========================================================================


class TestCoordinatorPrivacy:
    """The coordinator must not store home coordinates anywhere
    reachable via its public attributes."""

    async def test_data_is_risk_context_without_home_coords(self, hass):
        """``coordinator.data`` is a plain ``RiskContext`` with no home
        coordinate fields."""
        hass.config.latitude = 39.7555
        hass.config.longitude = -105.2211

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_USE_HOME_LOCATION: True},
            options=_FULL_OPTIONS,
            entry_id="privacy_test_1",
        )
        entry.add_to_hass(hass)
        coordinator = XcelOutagesCoordinator(hass, entry)

        with patch.object(
            coordinator._api, "fetch_events", return_value=_empty_outcome()
        ):
            await coordinator.async_refresh()

        ctx = coordinator.data
        assert isinstance(ctx, RiskContext)
        assert not hasattr(ctx, "home_lat")
        assert not hasattr(ctx, "home_lon")
        assert not hasattr(ctx, "home_latitude")
        assert not hasattr(ctx, "home_longitude")

    async def test_no_coordinate_leak_on_failure(self, hass):
        """After a failed refresh, the coordinator still exposes no
        home coordinate attributes."""
        from custom_components.xcel_outages.api import XcelOutagesConnectionError

        hass.config.latitude = 39.7555
        hass.config.longitude = -105.2211

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={CONF_USE_HOME_LOCATION: True},
            options=_FULL_OPTIONS,
            entry_id="privacy_test_2",
        )
        entry.add_to_hass(hass)
        coordinator = XcelOutagesCoordinator(hass, entry)

        with patch.object(
            coordinator._api,
            "fetch_events",
            side_effect=XcelOutagesConnectionError("Error"),
        ):
            await coordinator.async_refresh()

        assert not hasattr(coordinator, "home_lat")
        assert not hasattr(coordinator, "home_lon")


# =========================================================================
# Imports at module bottom
# =========================================================================
from pytest_homeassistant_custom_component.common import MockConfigEntry
from custom_components.xcel_outages.coordinator import XcelOutagesCoordinator
