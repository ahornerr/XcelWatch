"""Tests for the three supporting sensors: NearbyCustomers,
NearestDistance, and OutageCount.

All tests import the actual source classes from
``custom_components.xcel_outages.sensor`` and verify their contracts
against live ``RiskContext`` fixtures provided by the test harness.
"""

from __future__ import annotations

import pytest

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import EntityCategory

from custom_components.xcel_outages.const import DEVICE_NAME, DOMAIN, ENDPOINT_URL
from custom_components.xcel_outages.sensor import (
    XcelCustomersSensor,
    XcelNearestDistanceSensor,
    XcelOutageCountSensor,
)

pytestmark = pytest.mark.hass


# =========================================================================
# 1. Native value / state
# =========================================================================


class TestCustomersSensorState:
    """``native_value`` reflects ``nearby_customer_total``."""

    def test_none_when_no_data(self, mock_coordinator_no_data):
        sensor = XcelCustomersSensor(mock_coordinator_no_data, "e1")
        assert sensor.native_value is None

    def test_zero_when_no_material_events(self, mock_coordinator_zero_risk):
        sensor = XcelCustomersSensor(mock_coordinator_zero_risk, "e1")
        assert sensor.native_value == 0

    def test_value_from_risk_context(self, mock_coordinator_low_risk):
        sensor = XcelCustomersSensor(mock_coordinator_low_risk, "e1")
        assert sensor.native_value == 50

    def test_high_value(self, mock_coordinator_high_risk):
        sensor = XcelCustomersSensor(mock_coordinator_high_risk, "e1")
        assert sensor.native_value == 2500


class TestNearestDistanceSensorState:
    """``native_value`` reflects ``nearest_material_km``."""

    def test_none_when_no_data(self, mock_coordinator_no_data):
        sensor = XcelNearestDistanceSensor(mock_coordinator_no_data, "e1")
        assert sensor.native_value is None

    def test_none_when_no_material_events(self, mock_coordinator_zero_risk):
        sensor = XcelNearestDistanceSensor(mock_coordinator_zero_risk, "e1")
        assert sensor.native_value is None

    def test_value_from_risk_context(self, mock_coordinator_low_risk):
        sensor = XcelNearestDistanceSensor(mock_coordinator_low_risk, "e1")
        assert sensor.native_value == 3.5

    def test_moderate_distance(self, mock_coordinator_moderate_risk):
        sensor = XcelNearestDistanceSensor(mock_coordinator_moderate_risk, "e1")
        assert sensor.native_value == 1.2


class TestOutageCountSensorState:
    """``native_value`` reflects ``nearby_event_count`` (all events, any
    customer count)."""

    def test_none_when_no_data(self, mock_coordinator_no_data):
        sensor = XcelOutageCountSensor(mock_coordinator_no_data, "e1")
        assert sensor.native_value is None

    def test_zero_when_no_events(self, mock_coordinator_zero_risk):
        sensor = XcelOutageCountSensor(mock_coordinator_zero_risk, "e1")
        assert sensor.native_value == 0

    def test_value_from_risk_context(self, mock_coordinator_low_risk):
        sensor = XcelOutageCountSensor(mock_coordinator_low_risk, "e1")
        assert sensor.native_value == 1

    def test_many_events(self, mock_coordinator_high_risk):
        """high_risk has nearby_event_count=7."""
        sensor = XcelOutageCountSensor(mock_coordinator_high_risk, "e1")
        assert sensor.native_value == 7


# =========================================================================
# 2. Units / device class / diagnostic category
# =========================================================================


class TestCustomersSensorMetadata:
    """Unit, device class, state class, category."""

    def test_unit_of_measurement(self):
        s = XcelCustomersSensor(None, "e1")
        assert s.native_unit_of_measurement == "customers"

    def test_state_class(self):
        s = XcelCustomersSensor(None, "e1")
        assert s.state_class is None

    def test_entity_category(self):
        s = XcelCustomersSensor(None, "e1")
        assert s.entity_category is EntityCategory.DIAGNOSTIC

    def test_device_class(self):
        s = XcelCustomersSensor(None, "e1")
        assert s.device_class is None


class TestNearestDistanceSensorMetadata:
    """Unit, device class, state class, category."""

    def test_unit_of_measurement(self):
        s = XcelNearestDistanceSensor(None, "e1")
        assert s.native_unit_of_measurement == "km"

    def test_device_class(self):
        s = XcelNearestDistanceSensor(None, "e1")
        assert s.device_class is SensorDeviceClass.DISTANCE

    def test_state_class(self):
        s = XcelNearestDistanceSensor(None, "e1")
        assert s.state_class is None

    def test_entity_category(self):
        s = XcelNearestDistanceSensor(None, "e1")
        assert s.entity_category is EntityCategory.DIAGNOSTIC


class TestOutageCountSensorMetadata:
    """Unit, device class, state class, category."""

    def test_unit_of_measurement(self):
        s = XcelOutageCountSensor(None, "e1")
        assert s.native_unit_of_measurement == "outages"

    def test_state_class(self):
        s = XcelOutageCountSensor(None, "e1")
        assert s.state_class is None

    def test_entity_category(self):
        s = XcelOutageCountSensor(None, "e1")
        assert s.entity_category is EntityCategory.DIAGNOSTIC

    def test_device_class(self):
        s = XcelOutageCountSensor(None, "e1")
        assert s.device_class is None


# =========================================================================
# 3. Stable unique IDs
# =========================================================================


class TestUniqueIds:
    """Each sensor has a stable, deterministic unique ID."""

    def test_customers_sensor_unique_id(self):
        s = XcelCustomersSensor(None, "entry_abc")
        assert s.unique_id == "entry_abc_nearby_outage_customers"

    def test_distance_sensor_unique_id(self):
        s = XcelNearestDistanceSensor(None, "entry_abc")
        assert s.unique_id == "entry_abc_nearest_material_outage_distance"

    def test_count_sensor_unique_id(self):
        s = XcelOutageCountSensor(None, "entry_abc")
        assert s.unique_id == "entry_abc_nearby_outage_count"

    def test_ids_differ_by_entry(self):
        s1 = XcelCustomersSensor(None, "entry_1")
        s2 = XcelCustomersSensor(None, "entry_2")
        assert s1.unique_id != s2.unique_id

    def test_ids_differ_by_sensor_type(self):
        ids = {
            XcelCustomersSensor(None, "x").unique_id,
            XcelNearestDistanceSensor(None, "x").unique_id,
            XcelOutageCountSensor(None, "x").unique_id,
        }
        assert len(ids) == 3


# =========================================================================
# 4. Shared device
# =========================================================================


class TestSharedDevice:
    """All sensors share a single device per config entry."""

    def test_customers_device(self):
        s = XcelCustomersSensor(None, "entry_d1")
        ids = s.device_info["identifiers"]
        assert (DOMAIN, "entry_d1") in ids

    def test_distance_device(self):
        s = XcelNearestDistanceSensor(None, "entry_d1")
        ids = s.device_info["identifiers"]
        assert (DOMAIN, "entry_d1") in ids

    def test_count_device(self):
        s = XcelOutageCountSensor(None, "entry_d1")
        ids = s.device_info["identifiers"]
        assert (DOMAIN, "entry_d1") in ids

    def test_all_sensors_same_device(self):
        entry_id = "shared_d"
        sensors = [
            XcelCustomersSensor(None, entry_id),
            XcelNearestDistanceSensor(None, entry_id),
            XcelOutageCountSensor(None, entry_id),
        ]
        dev_ids = {
            next(iter(s.device_info["identifiers"])) for s in sensors
        }
        assert len(dev_ids) == 1

    def test_different_entries_different_devices(self):
        id_a = next(iter(XcelCustomersSensor(None, "a").device_info["identifiers"]))
        id_b = next(iter(XcelCustomersSensor(None, "b").device_info["identifiers"]))
        assert id_a != id_b

    def test_device_name(self):
        s = XcelCustomersSensor(None, "e1")
        assert s.device_info.get("name") == DEVICE_NAME


# =========================================================================
# 5. Availability
# =========================================================================


class TestAvailability:
    """Entities become unavailable when coordinator has no data or fails."""

    def test_unavailable_when_no_data(self, mock_coordinator_no_data):
        for sensor_cls in (
            XcelCustomersSensor,
            XcelNearestDistanceSensor,
            XcelOutageCountSensor,
        ):
            assert sensor_cls(mock_coordinator_no_data, "e1").available is False

    def test_available_with_data_and_success(self, mock_coordinator_low_risk):
        for sensor_cls in (
            XcelCustomersSensor,
            XcelNearestDistanceSensor,
            XcelOutageCountSensor,
        ):
            assert sensor_cls(mock_coordinator_low_risk, "e1").available is True

    def test_unavailable_on_update_failure(self, mock_coordinator_after_failure):
        for sensor_cls in (
            XcelCustomersSensor,
            XcelNearestDistanceSensor,
            XcelOutageCountSensor,
        ):
            assert sensor_cls(mock_coordinator_after_failure, "e1").available is False

    def test_data_still_readable_when_unavailable(self, mock_coordinator_after_failure):
        c = XcelCustomersSensor(mock_coordinator_after_failure, "e1")
        d = XcelNearestDistanceSensor(mock_coordinator_after_failure, "e1")
        n = XcelOutageCountSensor(mock_coordinator_after_failure, "e1")
        assert c.native_value is not None
        assert d.native_value is not None
        assert n.native_value is not None


# =========================================================================
# 6. Privacy — supporting sensors are pure-value, no attributes
# =========================================================================


class TestPrivacyNoSensitiveData:
    """Supporting sensors expose no ``extra_state_attributes`` (they are
    pure-value sensors).  This ensures home coordinates, raw event data,
    and individual outage details are never leaked through these entities."""

    FORBIDDEN_KEYS = {
        "home_lat", "home_lon", "home_latitude", "home_longitude",
        "home_coordinates", "coordinates", "location", "latitude",
        "longitude",
    }

    def test_customers_has_no_attributes(self, mock_coordinator_high_risk):
        s = XcelCustomersSensor(mock_coordinator_high_risk, "e1")
        assert s.extra_state_attributes is None

    def test_distance_has_no_attributes(self, mock_coordinator_high_risk):
        s = XcelNearestDistanceSensor(mock_coordinator_high_risk, "e1")
        assert s.extra_state_attributes is None

    def test_count_has_no_attributes(self, mock_coordinator_high_risk):
        s = XcelOutageCountSensor(mock_coordinator_high_risk, "e1")
        assert s.extra_state_attributes is None

    def test_no_forbidden_keys_customers(self, mock_coordinator_high_risk):
        """Even if attributes were added, they must not contain forbidden keys."""
        s = XcelCustomersSensor(mock_coordinator_high_risk, "e1")
        attrs = s.extra_state_attributes or {}
        for key in self.FORBIDDEN_KEYS:
            assert key not in attrs

    def test_no_forbidden_keys_distance(self, mock_coordinator_high_risk):
        s = XcelNearestDistanceSensor(mock_coordinator_high_risk, "e1")
        attrs = s.extra_state_attributes or {}
        for key in self.FORBIDDEN_KEYS:
            assert key not in attrs

    def test_no_forbidden_keys_count(self, mock_coordinator_high_risk):
        s = XcelOutageCountSensor(mock_coordinator_high_risk, "e1")
        attrs = s.extra_state_attributes or {}
        for key in self.FORBIDDEN_KEYS:
            assert key not in attrs
