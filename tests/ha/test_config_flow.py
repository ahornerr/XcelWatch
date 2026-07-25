"""Tests for the Xcel Outage Map config flow.

The setup flow has three steps:

1. **Location** (step_id ``"location"``) — choose HA coordinates or
   override location.  Only a boolean toggle is shown.
2. **Override** (step_id ``"override"``, conditional) — when override
   location is selected, both lat/lon are **required** (``vol.Required``)
   and validated to be within bounds.  No silent defaults.
3. **Params** (step_id ``"params"``) — search radius, poll interval,
   reachability test, then entry creation.

Options flow (two steps):
1. **init** — location toggle plus all tuning params; overrides never
   shown here.
2. **override** (conditional) — required lat/lon, shown only when the
   user selects override location.  Existing values pre-filled.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

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
    DOMAIN,
)

pytestmark = pytest.mark.hass


async def _init_flow(hass):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def _submit_location(hass, flow_id, data: dict[str, Any]):
    return await hass.config_entries.flow.async_configure(flow_id, data)


async def _submit_override(hass, flow_id, lat: float, lon: float):
    return await hass.config_entries.flow.async_configure(
        flow_id,
        {
            CONF_LATITUDE_OVERRIDE: lat,
            CONF_LONGITUDE_OVERRIDE: lon,
        },
    )


async def _submit_params(hass, flow_id, radius: int = 25, interval: int = 10):
    return await hass.config_entries.flow.async_configure(
        flow_id,
        {
            CONF_SEARCH_RADIUS: radius,
            CONF_POLL_INTERVAL: interval,
        },
    )


def _reachability_patch():
    """Return a patcher that mocks the API reachability test."""
    return patch(
        "custom_components.xcel_outages.config_flow._test_api_reachability",
        return_value=None,
    )


# =========================================================================
# 1. Initial form
# =========================================================================


class TestInitialForm:
    """The config flow starts with the location step form."""

    async def test_location_step_shown(self, hass):
        result = await _init_flow(hass)
        assert result["type"] == "form"
        assert result["step_id"] == "location"
        assert result["errors"] == {}
        schema = result["data_schema"].schema
        assert CONF_USE_HOME_LOCATION in schema
        assert CONF_LATITUDE_OVERRIDE not in schema
        assert CONF_LONGITUDE_OVERRIDE not in schema


# =========================================================================
# 2. HA location chosen (creates entry directly)
# =========================================================================


class TestHaLocation:
    async def test_ha_location_flows_to_params(self, hass):
        hass.config.latitude = 39.7555
        hass.config.longitude = -105.2211

        init = await _init_flow(hass)
        result = await _submit_location(
            hass, init["flow_id"], {CONF_USE_HOME_LOCATION: True}
        )
        assert result["type"] == "form"
        assert result["step_id"] == "params"

    async def test_ha_location_creates_entry(self, hass):
        hass.config.latitude = 39.7555
        hass.config.longitude = -105.2211

        init = await _init_flow(hass)
        loc = await _submit_location(
            hass, init["flow_id"], {CONF_USE_HOME_LOCATION: True}
        )
        assert loc["step_id"] == "params"

        with _reachability_patch():
            result = await _submit_params(hass, loc["flow_id"])

        assert result["type"] == "create_entry"
        assert result["title"] == "Xcel Outage Map"
        assert result["data"][CONF_USE_HOME_LOCATION] is True
        assert CONF_LATITUDE_OVERRIDE not in result["data"]
        assert CONF_LONGITUDE_OVERRIDE not in result["data"]


# =========================================================================
# 3. Override coordinates (three-step flow)
# =========================================================================


class TestOverrideCoordinates:
    async def test_override_creates_entry(self, hass):
        """Valid override → location → override → params → entry."""
        init = await _init_flow(hass)
        ovr = await _submit_location(
            hass, init["flow_id"], {CONF_USE_HOME_LOCATION: False}
        )
        assert ovr["type"] == "form"
        assert ovr["step_id"] == "override"

        ovr2 = await _submit_override(hass, ovr["flow_id"], 39.7392, -104.9903)
        assert ovr2["type"] == "form"
        assert ovr2["step_id"] == "params"

        with _reachability_patch():
            result = await _submit_params(hass, ovr2["flow_id"])

        assert result["type"] == "create_entry"
        assert result["data"][CONF_USE_HOME_LOCATION] is False
        assert result["data"][CONF_LATITUDE_OVERRIDE] == 39.7392
        assert result["data"][CONF_LONGITUDE_OVERRIDE] == -104.9903

    async def test_valid_zero_zero_overrides_accepted(self, hass):
        """0.0, 0.0 is a valid coordinate pair."""
        hass.config.latitude = None
        hass.config.longitude = None

        init = await _init_flow(hass)
        ovr = await _submit_location(
            hass, init["flow_id"], {CONF_USE_HOME_LOCATION: False}
        )
        assert ovr["step_id"] == "override"

        ovr2 = await _submit_override(hass, ovr["flow_id"], 0.0, 0.0)
        assert ovr2["step_id"] == "params"

        with _reachability_patch():
            result = await _submit_params(hass, ovr2["flow_id"])

        assert result["type"] == "create_entry"
        assert result["data"][CONF_LATITUDE_OVERRIDE] == 0.0
        assert result["data"][CONF_LONGITUDE_OVERRIDE] == 0.0

    async def test_override_out_of_range_rejected(self, hass):
        """Out-of-range lat → schema-level InvalidData."""
        from homeassistant.data_entry_flow import InvalidData

        init = await _init_flow(hass)
        ovr = await _submit_location(
            hass, init["flow_id"], {CONF_USE_HOME_LOCATION: False}
        )
        assert ovr["step_id"] == "override"

        with pytest.raises(InvalidData):
            await _submit_override(hass, ovr["flow_id"], 999.0, 0.0)


# =========================================================================
# 4. Valid HA location + user chooses override
# =========================================================================


class TestHaLocationWithOverrideChoice:
    async def test_valid_ha_can_still_choose_override(self, hass):
        """HA coords valid but user selects manual override."""
        hass.config.latitude = 39.7555
        hass.config.longitude = -105.2211

        init = await _init_flow(hass)
        ovr = await _submit_location(
            hass, init["flow_id"], {CONF_USE_HOME_LOCATION: False}
        )
        assert ovr["step_id"] == "override"

        ovr2 = await _submit_override(hass, ovr["flow_id"], 40.0, -105.0)
        assert ovr2["step_id"] == "params"

        with _reachability_patch():
            result = await _submit_params(hass, ovr2["flow_id"])

        assert result["data"][CONF_USE_HOME_LOCATION] is False
        assert result["data"][CONF_LATITUDE_OVERRIDE] == 40.0
        assert result["data"][CONF_LATITUDE_OVERRIDE] != hass.config.latitude


# =========================================================================
# 5. API reachability errors
# =========================================================================


class TestApiReachability:
    async def test_cannot_connect_error(self, hass):
        hass.config.latitude = 39.7555
        hass.config.longitude = -105.2211

        init = await _init_flow(hass)
        loc = await _submit_location(
            hass, init["flow_id"], {CONF_USE_HOME_LOCATION: True}
        )
        assert loc["step_id"] == "params"

        with patch(
            "custom_components.xcel_outages.config_flow._test_api_reachability",
            return_value="cannot_connect",
        ):
            result = await _submit_params(hass, loc["flow_id"])

        assert result["type"] == "form"
        assert result["step_id"] == "params"
        assert result["errors"]["base"] == "cannot_connect"

    async def test_unsupported_response_error(self, hass):
        hass.config.latitude = 39.7555
        hass.config.longitude = -105.2211

        init = await _init_flow(hass)
        loc = await _submit_location(
            hass, init["flow_id"], {CONF_USE_HOME_LOCATION: True}
        )
        assert loc["step_id"] == "params"

        with patch(
            "custom_components.xcel_outages.config_flow._test_api_reachability",
            return_value="unsupported_response",
        ):
            result = await _submit_params(hass, loc["flow_id"])

        assert result["type"] == "form"
        assert result["step_id"] == "params"
        assert result["errors"]["base"] == "unsupported_response"


# =========================================================================
# 6. Invalid HA runtime coordinates
# =========================================================================


class TestInvalidHaRuntimeCoordinates:
    async def test_none_coordinates_shows_error(self, hass):
        """HA lat/lon are None → location step shows error when submitted
        with use_home_location=True."""
        hass.config.latitude = None
        hass.config.longitude = None

        init = await _init_flow(hass)
        result = await _submit_location(
            hass, init["flow_id"], {CONF_USE_HOME_LOCATION: True}
        )
        assert result["type"] == "form"
        assert result["step_id"] == "location"
        assert result["errors"]["base"] == "missing_coordinates"

    async def test_invalid_ha_prompts_override(self, hass):
        """HA lat out of range → submit with use_home=True shows error;
        user can switch to override path instead."""
        hass.config.latitude = 91.0
        hass.config.longitude = 0.0

        init = await _init_flow(hass)
        result = await _submit_location(
            hass, init["flow_id"], {CONF_USE_HOME_LOCATION: True}
        )
        assert result["type"] == "form"
        assert result["step_id"] == "location"
        assert result["errors"]["base"] == "invalid_coordinates"

        # Now user chooses override instead
        result2 = await _submit_location(
            hass, init["flow_id"], {CONF_USE_HOME_LOCATION: False}
        )
        assert result2["type"] == "form"
        assert result2["step_id"] == "override"


# =========================================================================
# 7. Options flow
# =========================================================================


class TestOptionsFlow:
    _ENTRY_DATA = {CONF_USE_HOME_LOCATION: True}
    _ENTRY_OPTIONS = {
        CONF_SEARCH_RADIUS: 25,
        CONF_LOCAL_RADIUS: DEFAULT_LOCAL_RADIUS,
        CONF_MATERIAL_THRESHOLD: DEFAULT_MATERIAL_THRESHOLD,
        CONF_POLL_INTERVAL: 10,
    }

    async def _make_entry(self, hass, data=None, options=None):
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        entry = MockConfigEntry(
            domain=DOMAIN,
            data=data or self._ENTRY_DATA,
            options=options or self._ENTRY_OPTIONS,
            entry_id="opts_test",
        )
        entry.add_to_hass(hass)
        return entry

    async def test_options_form_shown(self, hass):
        entry = await self._make_entry(hass)
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] == "form"
        assert result["step_id"] == "init"
        schema = result["data_schema"].schema
        assert CONF_USE_HOME_LOCATION in schema
        assert CONF_LATITUDE_OVERRIDE not in schema
        assert CONF_LONGITUDE_OVERRIDE not in schema

    async def test_options_switch_to_override_shows_override_step(self, hass):
        entry = await self._make_entry(hass)
        init = await hass.config_entries.options.async_init(entry.entry_id)

        result = await hass.config_entries.options.async_configure(
            init["flow_id"],
            user_input={
                CONF_USE_HOME_LOCATION: False,
                CONF_SEARCH_RADIUS: 25,
                CONF_LOCAL_RADIUS: 10,
                CONF_MATERIAL_THRESHOLD: 25,
                CONF_POLL_INTERVAL: 10,
            },
        )
        assert result["type"] == "form"
        assert result["step_id"] == "override"

    async def test_options_switch_to_override_with_coords(self, hass):
        entry = await self._make_entry(hass)
        init = await hass.config_entries.options.async_init(entry.entry_id)

        r1 = await hass.config_entries.options.async_configure(
            init["flow_id"],
            user_input={
                CONF_USE_HOME_LOCATION: False,
                CONF_SEARCH_RADIUS: 25,
                CONF_LOCAL_RADIUS: 10,
                CONF_MATERIAL_THRESHOLD: 25,
                CONF_POLL_INTERVAL: 10,
            },
        )
        assert r1["step_id"] == "override"

        r2 = await hass.config_entries.options.async_configure(
            r1["flow_id"],
            user_input={
                CONF_LATITUDE_OVERRIDE: 40.0,
                CONF_LONGITUDE_OVERRIDE: -105.0,
            },
        )
        await hass.async_block_till_done()

        assert r2["type"] == "create_entry"
        assert entry.data[CONF_USE_HOME_LOCATION] is False
        assert entry.data[CONF_LATITUDE_OVERRIDE] == 40.0
        assert entry.data[CONF_LONGITUDE_OVERRIDE] == -105.0

    async def test_options_switch_back_to_ha_location(self, hass):
        entry = await self._make_entry(
            hass,
            data={
                CONF_USE_HOME_LOCATION: False,
                CONF_LATITUDE_OVERRIDE: 40.0,
                CONF_LONGITUDE_OVERRIDE: -105.0,
            },
        )

        init = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            init["flow_id"],
            user_input={
                CONF_USE_HOME_LOCATION: True,
                CONF_SEARCH_RADIUS: 25,
                CONF_LOCAL_RADIUS: 10,
                CONF_MATERIAL_THRESHOLD: 25,
                CONF_POLL_INTERVAL: 10,
            },
        )
        await hass.async_block_till_done()

        assert result["type"] == "create_entry"
        assert entry.data[CONF_USE_HOME_LOCATION] is True
        assert CONF_LATITUDE_OVERRIDE not in entry.data
        assert CONF_LONGITUDE_OVERRIDE not in entry.data


# =========================================================================
# 8. Config flow class contract
# =========================================================================


class TestConfigFlowClassContract:
    def test_config_flow_version(self):
        from custom_components.xcel_outages.config_flow import XcelOutagesConfigFlow
        assert XcelOutagesConfigFlow.VERSION == 1

    def test_has_user_step(self):
        from custom_components.xcel_outages.config_flow import XcelOutagesConfigFlow
        assert hasattr(XcelOutagesConfigFlow, "async_step_user")

    def test_has_location_step(self):
        from custom_components.xcel_outages.config_flow import XcelOutagesConfigFlow
        assert hasattr(XcelOutagesConfigFlow, "async_step_location")

    def test_has_override_step(self):
        from custom_components.xcel_outages.config_flow import XcelOutagesConfigFlow
        assert hasattr(XcelOutagesConfigFlow, "async_step_override")

    def test_has_params_step(self):
        from custom_components.xcel_outages.config_flow import XcelOutagesConfigFlow
        assert hasattr(XcelOutagesConfigFlow, "async_step_params")

    def test_has_get_options_flow(self):
        from custom_components.xcel_outages.config_flow import XcelOutagesConfigFlow
        assert hasattr(XcelOutagesConfigFlow, "async_get_options_flow")


# =========================================================================
# 9. _has_valid_ha_coordinates unit tests
# =========================================================================


class TestHasValidHaCoordinates:
    def test_valid(self, hass):
        from custom_components.xcel_outages.config_flow import _has_valid_ha_coordinates
        hass.config.latitude = 39.7555
        hass.config.longitude = -105.2211
        assert _has_valid_ha_coordinates(hass) is True

    def test_none_latitude(self, hass):
        from custom_components.xcel_outages.config_flow import _has_valid_ha_coordinates
        hass.config.latitude = None
        hass.config.longitude = -105.0
        assert _has_valid_ha_coordinates(hass) is False

    def test_none_longitude(self, hass):
        from custom_components.xcel_outages.config_flow import _has_valid_ha_coordinates
        hass.config.latitude = 39.75
        hass.config.longitude = None
        assert _has_valid_ha_coordinates(hass) is False

    def test_lat_out_of_range_positive(self, hass):
        from custom_components.xcel_outages.config_flow import _has_valid_ha_coordinates
        hass.config.latitude = 91.0
        hass.config.longitude = 0.0
        assert _has_valid_ha_coordinates(hass) is False

    def test_lat_out_of_range_negative(self, hass):
        from custom_components.xcel_outages.config_flow import _has_valid_ha_coordinates
        hass.config.latitude = -91.0
        hass.config.longitude = 0.0
        assert _has_valid_ha_coordinates(hass) is False

    def test_lon_out_of_range(self, hass):
        from custom_components.xcel_outages.config_flow import _has_valid_ha_coordinates
        hass.config.latitude = 0.0
        hass.config.longitude = 181.0
        assert _has_valid_ha_coordinates(hass) is False


# =========================================================================
# 10. NumberSelector form schema assertions
# =========================================================================


def _extract_number_selector(
    validator: Any,
) -> NumberSelector | None:
    """Walk a validator (possibly vol.All) and return the first
    NumberSelector found, or None."""
    if isinstance(validator, NumberSelector):
        return validator
    if isinstance(validator, vol.All):
        for v in validator.validators:
            result = _extract_number_selector(v)
            if result is not None:
                return result
    return None


class TestParamsStepNumberSelectors:
    """Each bounded integer field in the params step must use
    NumberSelector with BOX mode, step=1, correct bounds, and correct
    unit_of_measurement."""

    FIELD_EXPECTATIONS: dict[str, dict[str, Any]] = {
        "search_radius": {
            "min": 1,
            "max": 100,
            "unit": "km",
        },
        "poll_interval": {
            "min": 5,
            "max": 60,
            "unit": "min",
        },
    }

    async def _go_to_params_step(self, hass):
        """Drive the config flow to the params step via HA location."""
        hass.config.latitude = 39.7555
        hass.config.longitude = -105.2211

        init = await hass.config_entries.flow.async_init(
            "xcel_outages", context={"source": config_entries.SOURCE_USER}
        )
        loc = await hass.config_entries.flow.async_configure(
            init["flow_id"], {CONF_USE_HOME_LOCATION: True}
        )
        assert loc["step_id"] == "params"
        return loc

    async def _assert_params_selector(self, hass, field_key: str) -> None:
        result = await self._go_to_params_step(hass)
        schema = result["data_schema"].schema
        validator = schema[field_key]
        selector = _extract_number_selector(validator)
        assert selector is not None, (
            f"Expected NumberSelector for {field_key}"
        )
        exp = self.FIELD_EXPECTATIONS[field_key]
        cfg = selector.config
        assert cfg["min"] == exp["min"]
        assert cfg["max"] == exp["max"]
        assert cfg["step"] == 1
        assert cfg["mode"] == NumberSelectorMode.BOX
        assert cfg["unit_of_measurement"] == exp["unit"]

    async def test_params_step_search_radius_selector(self, hass):
        await self._assert_params_selector(hass, CONF_SEARCH_RADIUS)

    async def test_params_step_poll_interval_selector(self, hass):
        await self._assert_params_selector(hass, CONF_POLL_INTERVAL)


class TestOptionsInitStepNumberSelectors:
    """Each bounded integer field in the options init step must use
    NumberSelector with BOX mode, step=1, correct bounds, and correct
    unit_of_measurement."""

    FIELD_EXPECTATIONS: dict[str, dict[str, Any]] = {
        "search_radius": {
            "min": 1,
            "max": 100,
            "unit": "km",
        },
        "local_radius": {
            "min": 1,
            "max": 50,
            "unit": "km",
        },
        "material_threshold": {
            "min": 1,
            "max": 10_000,
            "unit": "customers",
        },
        "poll_interval": {
            "min": 5,
            "max": 60,
            "unit": "min",
        },
    }

    async def _go_to_init_step(self, hass):
        """Drive the options flow to the init step."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        entry = MockConfigEntry(
            domain="xcel_outages",
            data={CONF_USE_HOME_LOCATION: True},
            options={
                CONF_SEARCH_RADIUS: 25,
                CONF_LOCAL_RADIUS: DEFAULT_LOCAL_RADIUS,
                CONF_MATERIAL_THRESHOLD: DEFAULT_MATERIAL_THRESHOLD,
                CONF_POLL_INTERVAL: 10,
            },
            entry_id="opts_sel_test",
        )
        entry.add_to_hass(hass)
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["step_id"] == "init"
        return result

    async def _assert_selector(self, hass, field_key: str) -> None:
        result = await self._go_to_init_step(hass)
        schema = result["data_schema"].schema
        validator = schema[field_key]
        selector = _extract_number_selector(validator)
        assert selector is not None, (
            f"Expected NumberSelector for {field_key}"
        )
        exp = self.FIELD_EXPECTATIONS[field_key]
        cfg = selector.config
        assert cfg["min"] == exp["min"]
        assert cfg["max"] == exp["max"]
        assert cfg["step"] == 1
        assert cfg["mode"] == NumberSelectorMode.BOX
        assert cfg["unit_of_measurement"] == exp["unit"]

    async def test_options_init_search_radius_selector(self, hass):
        await self._assert_selector(hass, CONF_SEARCH_RADIUS)

    async def test_options_init_local_radius_selector(self, hass):
        await self._assert_selector(hass, CONF_LOCAL_RADIUS)

    async def test_options_init_material_threshold_selector(self, hass):
        await self._assert_selector(hass, CONF_MATERIAL_THRESHOLD)

    async def test_options_init_poll_interval_selector(self, hass):
        await self._assert_selector(hass, CONF_POLL_INTERVAL)
