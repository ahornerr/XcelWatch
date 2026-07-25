"""Tests for the sensor and binary_sensor entities.

Tests the actual ``XcelRiskSensor`` and ``XcelMaterialBinarySensor`` classes
with a mock coordinator (``MockCoordinator``).

All tests in this module are marked ``@pytest.mark.hass`` and require
``homeassistant`` and ``pytest-homeassistant-custom-component`` installed.
"""

from __future__ import annotations

import pytest

from custom_components.xcel_outages.binary_sensor import XcelMaterialBinarySensor
from custom_components.xcel_outages.const import ENDPOINT_URL
from custom_components.xcel_outages.sensor import XcelRiskSensor

pytestmark = pytest.mark.hass

# =========================================================================
# 1. XcelRiskSensor — native_value
# =========================================================================


class TestRiskSensorState:
    """``native_value`` reflects the coordinator's ``RiskContext.risk``."""

    def test_native_value_none_when_no_data(self, mock_coordinator_no_data):
        """No coordinator data → native_value is None (unknown)."""
        sensor = XcelRiskSensor(mock_coordinator_no_data, "entry_1")
        assert sensor.native_value is None

    def test_native_value_zero_risk(self, mock_coordinator_zero_risk):
        """Zero-risk context → native_value is 0."""
        sensor = XcelRiskSensor(mock_coordinator_zero_risk, "entry_1")
        assert sensor.native_value == 0

    def test_native_value_low_risk(self, mock_coordinator_low_risk):
        """Low-risk context → native_value is 15."""
        sensor = XcelRiskSensor(mock_coordinator_low_risk, "entry_1")
        assert sensor.native_value == 15

    def test_native_value_moderate_risk(self, mock_coordinator_moderate_risk):
        """Moderate-risk context → native_value is 35."""
        sensor = XcelRiskSensor(mock_coordinator_moderate_risk, "entry_1")
        assert sensor.native_value == 35

    def test_native_value_high_risk(self, mock_coordinator_high_risk):
        """High-risk context → native_value is 70."""
        sensor = XcelRiskSensor(mock_coordinator_high_risk, "entry_1")
        assert sensor.native_value == 70


# =========================================================================
# 2. XcelRiskSensor — extra_state_attributes
# =========================================================================


class TestRiskSensorAttributes:
    """``extra_state_attributes`` mirrors the ``RiskContext`` fields."""

    def test_attributes_present_for_low_risk(self, mock_coordinator_low_risk):
        """All expected attribute keys are present with correct values."""
        sensor = XcelRiskSensor(mock_coordinator_low_risk, "entry_1")
        attrs = sensor.extra_state_attributes
        assert attrs is not None
        assert attrs["risk_band"] == "Low"
        assert attrs["reason"] == "Material outage detected nearby"
        assert attrs["nearby_event_count"] == 1
        assert attrs["material_event_count"] == 1
        assert attrs["nearby_customer_total"] == 50
        assert attrs["local_customer_total"] == 50
        assert attrs["customer_total_increase"] == 0
        assert attrs["nearest_km"] == 3.5
        assert attrs["nearest_material_km"] == 3.5
        assert attrs["largest_nearby_event_customers"] == 50
        assert attrs["source_url"] == ENDPOINT_URL
        # last_successful_update is a dynamic ISO-8601 string
        assert isinstance(attrs["last_successful_update"], str)
        assert attrs["last_successful_update"].endswith("+00:00") or "Z" in attrs["last_successful_update"]

    def test_attributes_moderate_risk(self, mock_coordinator_moderate_risk):
        """Moderate risk context attributes are correct."""
        sensor = XcelRiskSensor(mock_coordinator_moderate_risk, "entry_1")
        attrs = sensor.extra_state_attributes
        assert attrs["risk_band"] == "Moderate"
        assert attrs["nearby_event_count"] == 3
        assert attrs["material_event_count"] == 2
        assert attrs["nearby_customer_total"] == 300
        assert attrs["nearest_km"] == 1.2
        assert attrs["nearest_material_km"] == 1.2

    def test_attributes_high_risk(self, mock_coordinator_high_risk):
        """High risk context attributes include customer_total_increase."""
        sensor = XcelRiskSensor(mock_coordinator_high_risk, "entry_1")
        attrs = sensor.extra_state_attributes
        assert attrs["risk_band"] == "High"
        assert attrs["nearby_customer_total"] == 2500
        assert attrs["customer_total_increase"] == 450

    def test_attributes_none_when_no_data(self, mock_coordinator_no_data):
        """No coordinator data → extra_state_attributes is None."""
        sensor = XcelRiskSensor(mock_coordinator_no_data, "entry_1")
        assert sensor.extra_state_attributes is None

    def test_attributes_on_failure_still_available(self, mock_coordinator_after_failure):
        """After an update failure, attributes retain the last successful
        context and ``last_successful_update`` is preserved (not cleared)."""
        sensor = XcelRiskSensor(mock_coordinator_after_failure, "entry_1")
        attrs = sensor.extra_state_attributes
        assert attrs is not None
        assert attrs["risk_band"] == "Low"
        # last_successful_update is retained from the previous success
        assert "last_successful_update" in attrs
        assert isinstance(attrs["last_successful_update"], str)

    def test_unique_id(self, mock_coordinator_low_risk):
        """Unique ID incorporates the entry ID."""
        sensor = XcelRiskSensor(mock_coordinator_low_risk, "entry_abc123")
        assert sensor.unique_id == "entry_abc123_nearby_outage_risk"


# =========================================================================
# 3. XcelMaterialBinarySensor — is_on
# =========================================================================


class TestMaterialBinarySensor:
    """``is_on`` reflects presence of material events."""

    def test_is_on_none_when_no_data(self, mock_coordinator_no_data):
        """No coordinator data → is_on is None (unknown)."""
        sensor = XcelMaterialBinarySensor(mock_coordinator_no_data, "entry_1")
        assert sensor.is_on is None

    def test_is_on_false_when_zero_material_events(self, mock_coordinator_zero_risk):
        """No material events → is_on is False."""
        sensor = XcelMaterialBinarySensor(mock_coordinator_zero_risk, "entry_1")
        assert sensor.is_on is False

    def test_is_on_true_when_material_events_present(self, mock_coordinator_low_risk):
        """At least one material event → is_on is True."""
        sensor = XcelMaterialBinarySensor(mock_coordinator_low_risk, "entry_1")
        assert sensor.is_on is True

    def test_unique_id(self, mock_coordinator_low_risk):
        """Unique ID incorporates the entry ID."""
        sensor = XcelMaterialBinarySensor(mock_coordinator_low_risk, "entry_xyz789")
        assert sensor.unique_id == "entry_xyz789_material_outage_nearby"

    def test_device_class_is_problem(self, mock_coordinator_low_risk):
        """Device class is PROBLEM."""
        sensor = XcelMaterialBinarySensor(mock_coordinator_low_risk, "entry_1")
        assert sensor.device_class == "problem"


# =========================================================================
# 4. Privacy — no home coordinates or raw event data in state attrs
# =========================================================================


class TestPrivacyNoSensitiveData:
    """State attributes must never expose home coordinates or raw events.

    This is a critical privacy invariant.  The following are forbidden:
    - ``home_lat``, ``home_lon``, ``home_latitude``, ``home_longitude``
    - Any event identifier, title, cause, county, city
    - ``coordinates`` or ``location`` fields
    - Raw event summaries or payload excerpts
    """

    FORBIDDEN_ATTRS = {
        "home_lat",
        "home_lon",
        "home_latitude",
        "home_longitude",
        "home_coordinates",
        "coordinates",
        "location",
    }

    FORBIDDEN_PREFIXES = {
        "event_",
        "events_",
        "raw_",
        "outage_events",
    }

    def test_no_home_coordinates_in_risk_sensor(self, mock_coordinator_high_risk):
        """No home coordinate keys in risk sensor attributes."""
        sensor = XcelRiskSensor(mock_coordinator_high_risk, "entry_1")
        attrs = sensor.extra_state_attributes or {}
        for forbidden in self.FORBIDDEN_ATTRS:
            assert forbidden not in attrs, (
                f"Risk sensor attributes must not contain '{forbidden}'"
            )

    def test_no_raw_event_data_in_risk_sensor(self, mock_coordinator_high_risk):
        """No raw event fields in risk sensor attributes."""
        sensor = XcelRiskSensor(mock_coordinator_high_risk, "entry_1")
        attrs = sensor.extra_state_attributes or {}
        for prefix in self.FORBIDDEN_PREFIXES:
            assert not any(
                k.startswith(prefix) for k in attrs
            ), f"Risk sensor must not contain keys with prefix '{prefix}'"

    def test_event_detail_fields_absent(self, mock_coordinator_high_risk):
        """Individual event fields (identifier, title, cause, etc.) are absent."""
        sensor = XcelRiskSensor(mock_coordinator_high_risk, "entry_1")
        attrs = sensor.extra_state_attributes or {}
        event_fields = {
            "identifier", "title", "cause", "county", "city",
            "num_people", "latitude", "longitude",
            "start_time", "last_updated_time", "etr_time",
            "additional_properties",
        }
        for field in event_fields:
            assert field not in attrs, (
                f"Risk sensor attributes must not contain event field '{field}'"
            )

    def test_no_geolocation_keys(self, mock_coordinator_high_risk):
        """No geolocation or mapping keys in attributes."""
        sensor = XcelRiskSensor(mock_coordinator_high_risk, "entry_1")
        attrs = sensor.extra_state_attributes or {}
        geo_keys = {"latitude", "longitude", "lat", "lon", "geo", "position"}
        for key in geo_keys:
            assert key not in attrs, (
                f"Risk sensor attributes must not contain geolocation key '{key}'"
            )

    def test_binary_sensor_no_sensitive_attrs(self, mock_coordinator_high_risk):
        """Binary sensor has no extra attributes at all (no leak vector)."""
        sensor = XcelMaterialBinarySensor(mock_coordinator_high_risk, "entry_1")
        # Binary sensor does not provide extra_state_attributes by default
        assert sensor.extra_state_attributes is None or sensor.extra_state_attributes == {}


# =========================================================================
# 5. Availability
# =========================================================================


class TestAvailability:
    """Entity availability reflects coordinator state."""

    def test_unavailable_when_no_data(self, mock_coordinator_no_data):
        """No coordinator data → entity is unavailable."""
        sensor = XcelRiskSensor(mock_coordinator_no_data, "entry_1")
        assert sensor.available is False

    def test_available_with_data_and_success(self, mock_coordinator_low_risk):
        """Coordinator has data and last update succeeded → available."""
        sensor = XcelRiskSensor(mock_coordinator_low_risk, "entry_1")
        assert sensor.available is True

    def test_unavailable_on_update_failure(self, mock_coordinator_after_failure):
        """Coordinator has data but last update failed → unavailable."""
        sensor = XcelRiskSensor(mock_coordinator_after_failure, "entry_1")
        assert sensor.available is False

    def test_entity_attributes_null_on_failure(self, mock_coordinator_after_failure):
        """Sensor attributes still return data even when unavailable,
        because coordinator.data is retained."""
        sensor = XcelRiskSensor(mock_coordinator_after_failure, "entry_1")
        assert sensor.available is False
        assert sensor.native_value is not None
        assert sensor.extra_state_attributes is not None

    def test_binary_sensor_unavailable_on_failure(self, mock_coordinator_after_failure):
        """Binary sensor becomes unavailable on coordinator failure."""
        sensor = XcelMaterialBinarySensor(mock_coordinator_after_failure, "entry_1")
        assert sensor.available is False

    def test_binary_sensor_available_with_data(self, mock_coordinator_low_risk):
        """Binary sensor is available with coordinator data."""
        sensor = XcelMaterialBinarySensor(mock_coordinator_low_risk, "entry_1")
        assert sensor.available is True
