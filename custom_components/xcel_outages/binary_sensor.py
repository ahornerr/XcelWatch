"""Binary sensor indicating whether a material outage exists nearby.

The sensor is diagnostic and informational.  An ``on`` state means at
least one material event (``num_people >= threshold``) exists within the
configured search radius.  This is **not** a claim that the configured
home is affected.
"""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorDeviceClass,
)
from homeassistant.const import EntityCategory

from .const import BINARY_SENSOR_MATERIAL
from .entity import XcelOutageEntity


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the material-outage binary sensor from a config entry.

    The coordinator is retrieved from ``hass.data[DOMAIN][entry.entry_id]``.
    """
    from .const import DOMAIN

    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([XcelMaterialBinarySensor(coordinator, entry.entry_id)])


class XcelMaterialBinarySensor(XcelOutageEntity, BinarySensorEntity):
    """Binary sensor: on when at least one material outage is nearby.

    This is purely informational — it does **not** imply that the home
    itself is without power.
    """

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry_id: str) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator, entry_id)
        self._attr_unique_id = f"{entry_id}_material_outage_nearby"
        self._attr_translation_key = BINARY_SENSOR_MATERIAL

    @property
    def is_on(self) -> bool | None:
        """Return ``True`` when at least one material event is nearby.

        Returns ``None`` (unknown) when coordinator data is absent.
        """
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.material_event_count > 0
