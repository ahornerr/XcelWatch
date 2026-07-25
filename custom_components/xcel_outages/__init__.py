"""Xcel Outage Map integration for Home Assistant.

This integration polls Xcel Energy's public outage-map cache, filters active
outages around Home Assistant's configured home location, and exposes
normalized outage context for dashboards and automations.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "binary_sensor"]


async def _async_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Reload the config entry on data or options changes.

    This ensures a fresh coordinator is created (resetting the
    customer-total-increase baseline) and that any location or
    radius changes take effect immediately.
    """
    _LOGGER.debug("Config entry updated; reloading %s", entry.entry_id)
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the Xcel Outage Map integration from a config entry.

    Creates one :class:`XcelOutagesCoordinator` per entry, performs the
    initial data refresh, stores the coordinator in ``hass.data``, and
    forwards the entry to sensor and binary_sensor platforms.

    Parameters
    ----------
    hass:
        The Home Assistant instance.
    entry:
        The config entry created by the config flow.

    Returns
    -------
    bool:
        ``True`` on success.
    """
    hass.data.setdefault(DOMAIN, {})

    # Local import — coordinator depends on HA internals and is only
    # needed at call-time, not at module-import time.
    from .coordinator import XcelOutagesCoordinator

    coordinator = XcelOutagesCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Reload the entry whenever data or options change
    entry.async_on_unload(
        entry.add_update_listener(_async_update_listener)
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry.

    Tears down sensor and binary_sensor platforms and removes the coordinator
    from ``hass.data``.

    Returns
    -------
    bool:
        ``True`` when all platforms unloaded successfully.
    """
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok
