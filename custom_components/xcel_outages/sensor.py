"""Sensors for the Xcel Outage Map integration.

Exposes one primary risk sensor with rich contextual attributes, three
supporting diagnostic value-only sensors, and a diagnostic freshness
timestamp sensor:

* **Risk** (0–100 ordinal nearby-outage risk)
* **Customers** (aggregate material nearby customer total)
* **Nearest distance** (km to the closest material outage)
* **Count** (total nearby events, any customer count)
* **Last update** (timestamp of the most recent successful coordinator refresh)
"""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    DEVICE_NAME,
    DOMAIN,
    ENDPOINT_URL,
    SENSOR_COUNT,
    SENSOR_CUSTOMERS,
    SENSOR_DISTANCE,
    SENSOR_FRESHNESS,
    SENSOR_RISK,
)
from .entity import XcelOutageEntity


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up all Xcel Outage Map sensors from a config entry.

    The coordinator is retrieved from ``hass.data[DOMAIN][entry.entry_id]``.
    """
    coordinator: DataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            XcelRiskSensor(coordinator, entry.entry_id),
            XcelCustomersSensor(coordinator, entry.entry_id),
            XcelNearestDistanceSensor(coordinator, entry.entry_id),
            XcelOutageCountSensor(coordinator, entry.entry_id),
            XcelFreshnessTimestampSensor(coordinator, entry.entry_id),
        ]
    )


# ---------------------------------------------------------------------------
# Primary risk sensor
# ---------------------------------------------------------------------------


class XcelRiskSensor(XcelOutageEntity, SensorEntity):
    """Sensor exposing the 0–100 nearby-outage risk score.

    The sensor is diagnostic — it provides outage awareness context and
    is not intended for safety-critical control.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:transmission-tower"
    _attr_native_unit_of_measurement = None
    _attr_state_class = None
    _attr_device_class = None

    def __init__(self, coordinator, entry_id: str) -> None:
        """Initialise the risk sensor."""
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_nearby_outage_risk"
        self._attr_translation_key = SENSOR_RISK

    @property
    def native_value(self) -> int | None:
        """Return the current risk score (0–100).

        Returns ``None`` when coordinator data is absent.
        """
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.risk

    @property
    def extra_state_attributes(self) -> dict | None:
        """Return risk-context attributes.

        Only the fields listed in the entity contract are included.
        The following are **explicitly excluded**:
        - Home coordinates (``home_lat``, ``home_lon``, etc.)
        - Raw event data, identifiers, titles, causes
        - ``city``, ``county``, ``comments``, ``outageimpact``
        - Event summaries
        - Exception traceback text
        """
        if self.coordinator.data is None:
            return None

        ctx = self.coordinator.data

        # Read the coordinator's persisted timestamp — updated only after
        # a fully successful refresh and retained across transient failures.
        last_successful_update: str | None = (
            self.coordinator.last_successful_update.isoformat()
            if self.coordinator.last_successful_update is not None
            else None
        )

        return {
            "risk_band": ctx.band,
            "reason": ctx.reason,
            "nearby_event_count": ctx.nearby_event_count,
            "material_event_count": ctx.material_event_count,
            "nearby_customer_total": ctx.nearby_customer_total,
            "local_customer_total": ctx.local_customer_total,
            "customer_total_increase": ctx.customer_total_increase,
            "nearest_km": ctx.nearest_km,
            "nearest_material_km": ctx.nearest_material_km,
            "largest_nearby_event_customers": ctx.largest_nearby_event_customers,
            "last_successful_update": last_successful_update,
            "source_url": ENDPOINT_URL,
        }


# ---------------------------------------------------------------------------
# Supporting sensors
# ---------------------------------------------------------------------------


class XcelCustomersSensor(XcelOutageEntity, SensorEntity):
    """Sensor exposing the aggregate material nearby-customer total.

    The value represents the sum of ``num_people`` for all **material**
    events (``num_people >= threshold``) within the configured search
    radius.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "customers"
    _attr_state_class = None
    _attr_device_class = None

    def __init__(self, coordinator, entry_id: str) -> None:
        """Initialise the customers sensor."""
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_nearby_outage_customers"
        self._attr_translation_key = SENSOR_CUSTOMERS

    @property
    def native_value(self) -> int | None:
        """Return the nearby material customer total.

        Returns ``None`` when coordinator data is absent.
        """
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.nearby_customer_total


class XcelNearestDistanceSensor(XcelOutageEntity, SensorEntity):
    """Sensor exposing the distance to the closest material outage.

    The value is in kilometres.  Returns ``None`` when no material
    outage exists within the search radius.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_native_unit_of_measurement = "km"
    _attr_state_class = None

    def __init__(self, coordinator, entry_id: str) -> None:
        """Initialise the distance sensor."""
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_nearest_material_outage_distance"
        self._attr_translation_key = SENSOR_DISTANCE

    @property
    def native_value(self) -> float | None:
        """Return the distance in km to the nearest material outage.

        Returns ``None`` when coordinator data is absent or no material
        events are nearby.
        """
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.nearest_material_km


class XcelOutageCountSensor(XcelOutageEntity, SensorEntity):
    """Sensor exposing the total number of nearby events.

    The value counts **all** events (any customer count) within the
    configured search radius.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = "outages"
    _attr_state_class = None
    _attr_device_class = None

    def __init__(self, coordinator, entry_id: str) -> None:
        """Initialise the count sensor."""
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_nearby_outage_count"
        self._attr_translation_key = SENSOR_COUNT

    @property
    def native_value(self) -> int | None:
        """Return the total number of nearby events.

        Returns ``None`` when coordinator data is absent.
        """
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.nearby_event_count


# ---------------------------------------------------------------------------
# Freshness timestamp sensor (standalone — not a CoordinatorEntity)
# ---------------------------------------------------------------------------


class XcelFreshnessTimestampSensor(SensorEntity):
    """Diagnostic sensor exposing the last successful coordinator refresh
    timestamp.

    This sensor is **not** a :class:`CoordinatorEntity` — it remains
    available whenever ``coordinator.last_successful_update`` is set, even
    after a transient refresh failure that marks other entities unavailable.

    The value is drawn from the existing coordinator timestamp and updated
    via a coordinator listener (no extra refresh cycle).
    """

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_icon = "mdi:clock-outline"
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        entry_id: str,
    ) -> None:
        """Initialise the freshness sensor."""
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry_id}_last_update_timestamp"
        self._attr_translation_key = SENSOR_FRESHNESS
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=DEVICE_NAME,
        )

    async def async_added_to_hass(self) -> None:
        """Register coordinator listener and clean up on remove."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self._coordinator.async_add_listener(self._handle_coordinator_update)
        )

    def _handle_coordinator_update(self) -> None:
        """Callback invoked by the coordinator after each refresh."""
        self.async_write_ha_state()

    @property
    def native_value(self) -> datetime | None:
        """Return the timestamp of the most recent successful refresh.

        Returns ``None`` before the first successful poll.
        """
        return self._coordinator.last_successful_update

    @property
    def available(self) -> bool:
        """Return ``True`` whenever a successful update has ever occurred.

        Unlike :class:`CoordinatorEntity` this sensor stays available
        across transient failures so users can always inspect *when* data
        was last successfully fetched.
        """
        return self._coordinator.last_successful_update is not None
