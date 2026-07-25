"""Base entity for the Xcel Outage Map integration.

All sensors share a single diagnostic device per config entry and common
availability logic derived from the :class:`DataUpdateCoordinator`.
"""

from __future__ import annotations

from homeassistant.const import EntityCategory
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEVICE_NAME, DOMAIN


class XcelOutageEntity(CoordinatorEntity):
    """Base entity for Xcel Outage Map sensors.

    Every entity is tied to a single coordinator (stored in
    ``hass.data[DOMAIN][entry_id]``) and shares a diagnostic device
    identified by ``(DOMAIN, entry_id)``.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator, entry_id: str) -> None:
        """Initialize the entity.

        Parameters
        ----------
        coordinator:
            The :class:`DataUpdateCoordinator` for this config entry.
        entry_id:
            The config entry ID, used to build the unique device identifier.
        """
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name=DEVICE_NAME,
        )

    @property
    def available(self) -> bool:
        """Return True when coordinator data is present and the last update
        did not fail."""
        if self.coordinator.data is None:
            return False
        return super().available
