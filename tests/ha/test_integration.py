"""Integration-level tests for the xcel_outages integration.

Tests ``async_setup_entry`` and ``async_unload_entry`` using ``MockConfigEntry``
and a mocked API to simulate the full lifecycle without live network requests.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from homeassistant.config_entries import ConfigEntryState

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
    DOMAIN,
    DEVICE_NAME,
)
from custom_components.xcel_outages.models import ParseOutcome, RiskContext

pytestmark = pytest.mark.hass


# =========================================================================
# Helpers
# =========================================================================


def _empty_outcome() -> ParseOutcome:
    """Valid empty parse outcome."""
    return ParseOutcome(
        events=(),
        is_valid_payload=True,
        raw_count=0,
        parsed_count=0,
        malformed_count=0,
        filtered_status_count=0,
    )


_ENTRY_DATA_HA = {CONF_USE_HOME_LOCATION: True}

_ENTRY_DATA_OVERRIDE = {
    CONF_USE_HOME_LOCATION: False,
    CONF_LATITUDE_OVERRIDE: 39.7392,
    CONF_LONGITUDE_OVERRIDE: -104.9903,
}

_FULL_OPTIONS = {
    CONF_SEARCH_RADIUS: 25,
    CONF_LOCAL_RADIUS: DEFAULT_LOCAL_RADIUS,
    CONF_MATERIAL_THRESHOLD: DEFAULT_MATERIAL_THRESHOLD,
    CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL,
}


def _make_entry(hass, data=None, options=None, entry_id="test_entry"):
    """Create a MockConfigEntry from the integration domain.

    Uses the standard HA test helper.  The caller **must** mock
    ``XcelOutageApi.fetch_events`` before calling ``async_setup``
    so no live request is made.
    """
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(
        domain=DOMAIN,
        data=data or _ENTRY_DATA_HA,
        options=options or _FULL_OPTIONS,
        entry_id=entry_id,
    )
    entry.add_to_hass(hass)
    return entry


# =========================================================================
# 1. Setup entry
# =========================================================================


class TestSetupEntry:
    """``async_setup_entry`` creates coordinator and forwards platforms."""

    async def test_setup_entry_with_ha_location(self, hass):
        """HA location entry → coordinator created with data."""
        hass.config.latitude = 39.7555
        hass.config.longitude = -105.2211
        entry = _make_entry(hass)

        with patch(
            "custom_components.xcel_outages.coordinator.XcelOutageApi.fetch_events",
            return_value=_empty_outcome(),
        ):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.LOADED
        assert DOMAIN in hass.data
        assert entry.entry_id in hass.data[DOMAIN]

        from custom_components.xcel_outages.coordinator import XcelOutagesCoordinator

        coordinator = hass.data[DOMAIN][entry.entry_id]
        assert isinstance(coordinator, XcelOutagesCoordinator)
        assert coordinator.data is not None
        assert isinstance(coordinator.data, RiskContext)
        assert coordinator.last_update_success is True

    async def test_setup_entry_with_override_coordinates(self, hass):
        """Override-coordinates entry includes required lat/lon keys
        in entry.data."""
        entry = _make_entry(hass, data=_ENTRY_DATA_OVERRIDE)

        with patch(
            "custom_components.xcel_outages.coordinator.XcelOutageApi.fetch_events",
            return_value=_empty_outcome(),
        ):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.LOADED
        assert entry.entry_id in hass.data[DOMAIN]

    async def test_setup_fails_on_api_error(self, hass):
        """If the initial API call fails, the entry is not loaded."""
        from custom_components.xcel_outages.api import XcelOutagesConnectionError

        entry = _make_entry(hass)

        with patch(
            "custom_components.xcel_outages.coordinator.XcelOutageApi.fetch_events",
            side_effect=XcelOutagesConnectionError("Fetch failed"),
        ):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        # First-failure goes to SETUP_RETRY or stays in NOT_LOADED
        assert entry.state in (
            ConfigEntryState.SETUP_RETRY,
            ConfigEntryState.SETUP_ERROR,
        )

    async def test_platforms_are_created(self, hass):
        """Setup creates sensor and binary_sensor entities."""
        hass.config.latitude = 39.7555
        hass.config.longitude = -105.2211
        entry = _make_entry(hass)

        with patch(
            "custom_components.xcel_outages.coordinator.XcelOutageApi.fetch_events",
            return_value=_empty_outcome(),
        ):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        risk = hass.states.get("sensor.xcel_outage_map_nearby_outage_risk")
        assert risk is not None
        assert risk.state == "0"

        binary = hass.states.get("binary_sensor.xcel_outage_map_material_outage_nearby")
        assert binary is not None
        assert binary.state == "off"


# =========================================================================
# 2. last_successful_update retention
# =========================================================================


class TestTimestampSensor:
    """The ``sensor.xcel_outage_map_last_update_timestamp`` freshness
    sensor records the last successful coordinator refresh time.  It is
    always available after the first successful poll."""

    _ENTITY_ID = "sensor.xcel_outage_map_last_update_timestamp"

    async def test_registered_after_setup(self, hass):
        """The timestamp sensor is registered after a successful setup."""
        hass.config.latitude = 39.7555
        hass.config.longitude = -105.2211
        entry = _make_entry(hass)

        with patch(
            "custom_components.xcel_outages.coordinator.XcelOutageApi.fetch_events",
            return_value=_empty_outcome(),
        ):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        state = hass.states.get(self._ENTITY_ID)
        assert state is not None
        assert state.state != "unavailable"
        assert "T" in state.state  # ISO-8601

    async def test_state_is_iso_timestamp(self, hass):
        """The native value is an ISO-8601 UTC timestamp string."""
        hass.config.latitude = 39.7555
        hass.config.longitude = -105.2211
        entry = _make_entry(hass)

        with patch(
            "custom_components.xcel_outages.coordinator.XcelOutageApi.fetch_events",
            return_value=_empty_outcome(),
        ):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        state = hass.states.get(self._ENTITY_ID)
        assert state is not None
        ts = state.state
        assert isinstance(ts, str)
        assert ts.endswith("+00:00") or ts.endswith("Z")
        assert "T" in ts

    async def test_remains_available_after_coordinator_failure(self, hass):
        """The timestamp sensor stays available after a coordinator
        refresh failure, retaining the last successful timestamp."""
        from custom_components.xcel_outages.api import XcelOutagesConnectionError

        hass.config.latitude = 39.7555
        hass.config.longitude = -105.2211
        entry = _make_entry(hass)

        with patch(
            "custom_components.xcel_outages.coordinator.XcelOutageApi.fetch_events",
            return_value=_empty_outcome(),
        ):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        ts_before = hass.states.get(self._ENTITY_ID).state
        assert ts_before is not None

        coordinator = hass.data[DOMAIN][entry.entry_id]
        with patch.object(
            coordinator._api,
            "fetch_events",
            side_effect=XcelOutagesConnectionError("transient"),
        ):
            await coordinator.async_refresh()
            await hass.async_block_till_done()

        state_after = hass.states.get(self._ENTITY_ID)
        assert state_after is not None
        assert state_after.state != "unavailable"
        assert state_after.state == ts_before

    async def test_listener_registered_after_setup(self, hass):
        """The freshness sensor registers exactly one coordinator listener
        on initialisation."""
        hass.config.latitude = 39.7555
        hass.config.longitude = -105.2211
        entry = _make_entry(hass)

        with patch(
            "custom_components.xcel_outages.coordinator.XcelOutageApi.fetch_events",
            return_value=_empty_outcome(),
        ):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        coordinator = hass.data[DOMAIN][entry.entry_id]
        listener_count = len(coordinator._listeners)
        # One listener per CoordinatorEntity (4 sensors) + one for
        # the standalone freshness sensor = 5 total.
        assert listener_count >= 5, (
            f"Expected ≥5 listeners (4 CoordinatorEntity + 1 freshness), "
            f"got {listener_count}"
        )

    async def test_listener_unsubscribed_on_unload(self, hass):
        """After the config entry is unloaded, the coordinator listener
        count returns to its pre-setup level (no stale references)."""
        hass.config.latitude = 39.7555
        hass.config.longitude = -105.2211
        entry = _make_entry(hass)

        with patch(
            "custom_components.xcel_outages.coordinator.XcelOutageApi.fetch_events",
            return_value=_empty_outcome(),
        ):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        coordinator = hass.data[DOMAIN][entry.entry_id]
        pre_unload = len(coordinator._listeners)

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

        post_unload = len(coordinator._listeners)
        # After unload the coordinator is removed from hass.data but
        # the _listeners dict should be empty (all removed).
        assert post_unload == 0, (
            f"Expected 0 listeners after unload, got {post_unload}"
        )

    async def test_no_extra_poll_from_listener_setup(self, hass):
        """Registering the freshness sensor listener does not trigger an
        additional coordinator refresh — the listener is purely a
        state-write callback."""
        hass.config.latitude = 39.7555
        hass.config.longitude = -105.2211
        entry = _make_entry(hass)

        with patch(
            "custom_components.xcel_outages.coordinator.XcelOutageApi.fetch_events",
            return_value=_empty_outcome(),
        ) as mock_fetch:
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        # Exactly 1 fetch: the coordinator's initial refresh.
        # No extra poll from platform setup or listener registration.
        assert mock_fetch.call_count == 1, (
            f"Expected 1 fetch, got {mock_fetch.call_count}"
        )


# =========================================================================
# 3. Lifecycle — all sensor entities after failure
# =========================================================================


class TestAllSensorsLifecycle:
    """After a coordinator failure, all primary and supporting sensor
    entities become unavailable while the timestamp (freshness) sensor
    remains available with its last value."""

    _SENSOR_IDS = [
        "sensor.xcel_outage_map_nearby_outage_risk",
        "sensor.xcel_outage_map_nearby_outage_customers",
        "sensor.xcel_outage_map_nearest_material_outage_distance",
        "sensor.xcel_outage_map_nearby_outage_count",
    ]
    _FRESHNESS_ID = "sensor.xcel_outage_map_last_update_timestamp"
    _BINARY_ID = "binary_sensor.xcel_outage_map_material_outage_nearby"

    async def _setup_and_fail(self, hass):
        """Helper: set up entry, then force a coordinator refresh failure."""
        from custom_components.xcel_outages.api import XcelOutagesConnectionError

        hass.config.latitude = 39.7555
        hass.config.longitude = -105.2211
        entry = _make_entry(hass)

        with patch(
            "custom_components.xcel_outages.coordinator.XcelOutageApi.fetch_events",
            return_value=_empty_outcome(),
        ):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        coordinator = hass.data[DOMAIN][entry.entry_id]
        with patch.object(
            coordinator._api,
            "fetch_events",
            side_effect=XcelOutagesConnectionError("fail"),
        ):
            await coordinator.async_refresh()
            await hass.async_block_till_done()

        return entry

    async def test_all_entities_registered_after_setup(self, hass):
        """All five sensors + binary sensor exist after setup with
        correct initial states."""
        hass.config.latitude = 39.7555
        hass.config.longitude = -105.2211
        entry = _make_entry(hass)

        with patch(
            "custom_components.xcel_outages.coordinator.XcelOutageApi.fetch_events",
            return_value=_empty_outcome(),
        ):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        for entity_id in self._SENSOR_IDS + [self._FRESHNESS_ID]:
            state = hass.states.get(entity_id)
            assert state is not None, f"{entity_id} not found"
            assert state.state != "unavailable", f"{entity_id} should be available"

        binary = hass.states.get(self._BINARY_ID)
        assert binary is not None
        assert binary.state == "off"

    async def test_primary_and_supporting_unavailable_after_failure(self, hass):
        """After a coordinator refresh failure, all primary and supporting
        sensor entities plus the binary sensor become unavailable."""
        await self._setup_and_fail(hass)

        for entity_id in self._SENSOR_IDS + [self._BINARY_ID]:
            state = hass.states.get(entity_id)
            assert state is not None, f"{entity_id} not found"
            assert state.state == "unavailable", (
                f"{entity_id} should be unavailable, got {state.state}"
            )

    async def test_freshness_remains_available_after_failure(self, hass):
        """The timestamp (freshness) sensor stays available after a
        coordinator failure, still holding the last successful timestamp."""
        await self._setup_and_fail(hass)

        state = hass.states.get(self._FRESHNESS_ID)
        assert state is not None
        assert state.state != "unavailable"
        assert "T" in state.state

    async def test_supporting_sensors_have_no_extra_attributes(self, hass):
        """Supporting sensors (customers, distance, count) are pure-value
        and expose no extra_state_attributes, even after failure."""
        await self._setup_and_fail(hass)

        for entity_id in self._SENSOR_IDS[1:]:  # skip risk
            state = hass.states.get(entity_id)
            assert state is not None
            non_standard = {
                k for k in (state.attributes or {})
                if k not in ("friendly_name", "icon", "device_class",
                             "state_class", "unit_of_measurement",
                             "restored", "supported_features")
            }
            assert len(non_standard) == 0, (
                f"{entity_id} has unexpected attributes: {non_standard}"
            )


# =========================================================================
# 4. Unload entry
# =========================================================================


class TestUnloadEntry:
    """``async_unload_entry`` tears down platforms and removes coordinator."""

    async def test_unload_removes_coordinator(self, hass):
        """After unload, coordinator is removed from ``hass.data``."""
        hass.config.latitude = 39.7555
        hass.config.longitude = -105.2211
        entry = _make_entry(hass)

        with patch(
            "custom_components.xcel_outages.coordinator.XcelOutageApi.fetch_events",
            return_value=_empty_outcome(),
        ):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        assert entry.entry_id in hass.data[DOMAIN]

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

        assert entry.entry_id not in hass.data[DOMAIN]

    async def test_unload_removes_entities(self, hass):
        """After unload, entities become unavailable (restored=True)
        — they are removed from the device registry but persist in the
        state machine as unavailable."""
        hass.config.latitude = 39.7555
        hass.config.longitude = -105.2211
        entry = _make_entry(hass)

        with patch(
            "custom_components.xcel_outages.coordinator.XcelOutageApi.fetch_events",
            return_value=_empty_outcome(),
        ):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        assert hass.states.get("sensor.xcel_outage_map_nearby_outage_risk") is not None

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

        # After unload the state becomes unavailable / restored
        state = hass.states.get("sensor.xcel_outage_map_nearby_outage_risk")
        assert state is None or state.state == "unavailable"

    async def test_unload_returns_true(self, hass):
        """``async_unload_entry`` returns ``True`` on success."""
        hass.config.latitude = 39.7555
        hass.config.longitude = -105.2211
        entry = _make_entry(hass)

        with patch(
            "custom_components.xcel_outages.coordinator.XcelOutageApi.fetch_events",
            return_value=_empty_outcome(),
        ):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        result = await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert result is True

    async def test_unload_without_setup_does_not_crash(self, hass):
        """Unloading an entry that was never set up is a safe no-op."""
        entry = _make_entry(hass)
        result = await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert result is True


# =========================================================================
# 4. Reload via update listener — mocks maintained during reload
# =========================================================================


class TestReloadBehavior:
    """The integration registers an update listener that triggers a reload
    when entry data or options are modified.  Mocks must remain active
    during the reload to prevent live requests."""

    async def test_reload_on_options_change(self, hass):
        """Changing options triggers a reload via the update listener.
        The mock remains active so no live request is made."""
        hass.config.latitude = 39.7555
        hass.config.longitude = -105.2211
        entry = _make_entry(hass)

        with patch(
            "custom_components.xcel_outages.coordinator.XcelOutageApi.fetch_events",
            return_value=_empty_outcome(),
        ) as mock_fetch:
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

            assert entry.state is ConfigEntryState.LOADED
            initial_call_count = mock_fetch.call_count

            # Modify options — triggers reload which calls fetch again
            hass.config_entries.async_update_entry(
                entry,
                options={
                    CONF_SEARCH_RADIUS: 50,
                    CONF_LOCAL_RADIUS: DEFAULT_LOCAL_RADIUS,
                    CONF_MATERIAL_THRESHOLD: DEFAULT_MATERIAL_THRESHOLD,
                    CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL,
                },
            )
            await hass.async_block_till_done()

        # Still loaded after reload
        assert entry.state is ConfigEntryState.LOADED
        # fetch was called during the reload (new coordinator refresh)
        assert mock_fetch.call_count > initial_call_count

    async def test_reload_on_data_change(self, hass):
        """Changing entry data (e.g. location override) triggers reload
        with the same mock covering both setup and reload."""
        hass.config.latitude = 39.7555
        hass.config.longitude = -105.2211
        entry = _make_entry(hass)

        with patch(
            "custom_components.xcel_outages.coordinator.XcelOutageApi.fetch_events",
            return_value=_empty_outcome(),
        ) as mock_fetch:
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

            assert entry.state is ConfigEntryState.LOADED
            initial_calls = mock_fetch.call_count

            # Change data (simulate switching to override)
            hass.config_entries.async_update_entry(
                entry,
                data={
                    CONF_USE_HOME_LOCATION: False,
                    CONF_LATITUDE_OVERRIDE: 39.7392,
                    CONF_LONGITUDE_OVERRIDE: -104.9903,
                },
            )
            await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.LOADED
        assert mock_fetch.call_count > initial_calls

    async def test_reload_produces_fresh_coordinator(self, hass):
        """After reload, a new coordinator is created (data is fresh)."""
        hass.config.latitude = 39.7555
        hass.config.longitude = -105.2211
        entry = _make_entry(hass)

        with patch(
            "custom_components.xcel_outages.coordinator.XcelOutageApi.fetch_events",
            return_value=_empty_outcome(),
        ):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        old_coordinator = hass.data[DOMAIN][entry.entry_id]

        with patch(
            "custom_components.xcel_outages.coordinator.XcelOutageApi.fetch_events",
            return_value=_empty_outcome(),
        ):
            hass.config_entries.async_update_entry(
                entry,
                options={
                    CONF_SEARCH_RADIUS: 75,
                    CONF_LOCAL_RADIUS: DEFAULT_LOCAL_RADIUS,
                    CONF_MATERIAL_THRESHOLD: DEFAULT_MATERIAL_THRESHOLD,
                    CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL,
                },
            )
            await hass.async_block_till_done()

        # A new coordinator instance should have been created
        new_coordinator = hass.data[DOMAIN][entry.entry_id]
        assert new_coordinator is not old_coordinator


# =========================================================================
# 5. No duplicate coordinator refresh from platform setup
# =========================================================================


class TestNoDuplicateRefresh:
    """Platform ``async_setup_entry`` should NOT trigger an additional
    coordinator refresh — the coordinator has already done its initial
    refresh before platforms are forwarded.

    The total number of API fetch calls after a full setup should be
    exactly 1 (the coordinator's ``async_config_entry_first_refresh``).
    """

    async def test_platform_setup_does_not_trigger_extra_refresh(self, hass):
        """The initial refresh happens once during ``async_setup_entry``.
        Platform setup (sensor, binary_sensor) reads data from the
        coordinator without calling fetch again."""
        hass.config.latitude = 39.7555
        hass.config.longitude = -105.2211
        entry = _make_entry(hass)

        with patch(
            "custom_components.xcel_outages.coordinator.XcelOutageApi.fetch_events",
            return_value=_empty_outcome(),
        ) as mock_fetch:
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        # Exactly 1 fetch: the coordinator's initial refresh.
        # Platform setup reads cached data from coordinator.data.
        assert mock_fetch.call_count == 1, (
            f"Expected 1 fetch (coordinator refresh), got {mock_fetch.call_count}"
        )

        # Entities are available with correct data
        risk = hass.states.get("sensor.xcel_outage_map_nearby_outage_risk")
        assert risk is not None
        assert risk.state == "0"

        binary = hass.states.get("binary_sensor.xcel_outage_map_material_outage_nearby")
        assert binary is not None
        assert binary.state == "off"
