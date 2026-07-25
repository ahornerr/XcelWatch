"""Data update coordinator for the Xcel Outage Map integration.

One coordinator is created per config entry.  Responsibilities:

* Resolve coordinates from HA config or saved override.
* Fetch and parse events via :class:`api.XcelOutageApi`.
* Compute a :class:`~models.RiskContext` via :func:`scoring.compute_risk_context`.
* Track the previous nearby-customer total for the customer-total-increase
  bonus (resets on coordinator creation).
* Surface network / schema failures as :class:`UpdateFailed` while retaining
  the last successful data.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import XcelOutageApi, XcelOutagesError
from .const import (
    CONF_LOCAL_RADIUS,
    CONF_MATERIAL_THRESHOLD,
    CONF_POLL_INTERVAL,
    CONF_SEARCH_RADIUS,
    CONF_USE_HOME_LOCATION,
    CONF_LATITUDE_OVERRIDE,
    CONF_LONGITUDE_OVERRIDE,
    DEFAULT_LOCAL_RADIUS,
    DEFAULT_MATERIAL_THRESHOLD,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_SEARCH_RADIUS,
    DOMAIN,
)
from .models import RiskContext
from .scoring import compute_risk_context

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Coordinate validation (privacy-safe — no values in messages)
# ---------------------------------------------------------------------------

_COORD_ERR_MSG = "Home location is not properly configured"


def _check_coordinates(lat: Any, lon: Any) -> None:
    """Validate that *lat* and *lon* are finite floats in range.

    Raises ``UpdateFailed`` with a coordinate-free message when invalid.
    """
    if lat is None or lon is None:
        raise UpdateFailed(_COORD_ERR_MSG)
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        raise UpdateFailed(_COORD_ERR_MSG)
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
        raise UpdateFailed(_COORD_ERR_MSG)


# ---------------------------------------------------------------------------
# Coordinator
# ---------------------------------------------------------------------------


class XcelOutagesCoordinator(DataUpdateCoordinator[RiskContext]):
    """Coordinator that fetches Xcel outage data and computes risk.

    ``coordinator.data`` contains a :class:`~models.RiskContext` after each
    successful refresh.  On failure the previous data is retained and the
    coordinator reports ``last_update_success = False``, marking entities
    unavailable.

    ``coordinator.last_successful_update`` carries the UTC datetime of the
    most recent successful refresh.  It is ``None`` before the first
    successful poll and is retained across transient failures.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialise the coordinator.

        Parameters
        ----------
        hass:
            The Home Assistant instance.
        entry:
            The config entry whose data/options govern behaviour.
        """
        self._entry = entry
        self._api = XcelOutageApi(async_get_clientsession(hass))
        # Baseline resets on every new coordinator (e.g. after reload).
        self._previous_total: int | None = None
        # Timestamp carried across failures; updated only on success.
        self.last_successful_update: datetime | None = None

        poll_interval = entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} ({entry.entry_id[:8]}...)",
            update_interval=timedelta(minutes=poll_interval),
        )

    # ------------------------------------------------------------------
    # Coordinate resolution (never exposed outside this class)
    # ------------------------------------------------------------------

    def _get_home_coordinates(self) -> tuple[float | None, float | None]:
        """Return the effective (latitude, longitude) for this entry.

        Returns ``(None, None)`` when the configured source does not have
        usable coordinates — the caller must validate with
        :func:`_check_coordinates`.

        Privacy guarantee: these coordinates are passed directly to the pure
        scoring function and are **never** stored in coordinator state,
        logged at info/warning/error level, or included in entity attributes,
        diagnostics, or exceptions.
        """
        if self._entry.data.get(CONF_USE_HOME_LOCATION, True):
            return (self.hass.config.latitude, self.hass.config.longitude)

        return (
            self._entry.data.get(CONF_LATITUDE_OVERRIDE),
            self._entry.data.get(CONF_LONGITUDE_OVERRIDE),
        )

    # ------------------------------------------------------------------
    # Data refresh
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> RiskContext:
        """Fetch events, compute risk, and return the updated context.

        Raises
        ------
        UpdateFailed:
            On any network, HTTP, schema, or coordinate failure.  The
            coordinator retains its last successful data when this is
            raised.
        """
        try:
            outcome = await self._api.fetch_events()
        except XcelOutagesError as err:
            raise UpdateFailed(str(err)) from err

        lat, lon = self._get_home_coordinates()
        # Validate coordinate defensively — never pass bad values to scorer.
        try:
            _check_coordinates(lat, lon)
        except UpdateFailed:
            _LOGGER.debug("Invalid home coordinates; skipping update")
            raise

        options = self._entry.options

        ctx = compute_risk_context(
            events=list(outcome.events),
            home_lat=lat,          # type: ignore[arg-type]  — validated above
            home_lon=lon,          # type: ignore[arg-type]
            search_radius=options.get(CONF_SEARCH_RADIUS, DEFAULT_SEARCH_RADIUS),
            local_radius=options.get(CONF_LOCAL_RADIUS, DEFAULT_LOCAL_RADIUS),
            material_threshold=options.get(
                CONF_MATERIAL_THRESHOLD, DEFAULT_MATERIAL_THRESHOLD
            ),
            previous_total=self._previous_total,
        )

        # Store the current total as the baseline for the next poll.
        self._previous_total = ctx.nearby_customer_total

        # Record the timestamp only after a fully successful refresh.
        self.last_successful_update = datetime.now(timezone.utc)

        _LOGGER.debug(
            "Risk context updated: risk=%d, band=%s, nearby_events=%d, "
            "material_events=%d, nearby_customers=%d, increase=%d",
            ctx.risk,
            ctx.band,
            ctx.nearby_event_count,
            ctx.material_event_count,
            ctx.nearby_customer_total,
            ctx.customer_total_increase,
        )

        return ctx
