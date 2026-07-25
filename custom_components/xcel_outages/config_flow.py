"""Config and options flow for the Xcel Outage Map integration.

Setup flow
----------
Three-step initial setup:

1. **Location preference** — ``async_step_location`` asks whether to use
   Home Assistant's configured coordinates or enter override values.

2. **Override coordinates (conditional)** — ``async_step_override``
   collects the override latitude/longitude when override location is
   selected.  Both fields are required and validated; no silent HA/0
   defaults are accepted.

3. **Parameters** — ``async_step_params`` collects search radius and poll
   interval, performs a live endpoint reachability test, and creates the
   config entry.

Options flow
------------
Two-step options flow:

1. **Main settings** — ``async_step_init`` exposes search radius, local
   radius, material threshold, poll interval, and location source.
   Override coordinates are **not** shown here.

2. **Override coordinates (conditional)** — ``async_step_override`` is
   shown only when the user selects override location.  Existing override
   values are preserved as defaults; missing overrides are never accepted.

Data changes are persisted safely via
:meth:`~homeassistant.config_entries.ConfigEntries.async_update_entry`,
and the entry is reloaded so the coordinator picks up the new values.
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    XcelOutageApi,
    XcelOutagesConnectionError,
    XcelOutagesSchemaError,
)
from .const import (
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
    MAX_LOCAL_RADIUS,
    MAX_MATERIAL_THRESHOLD,
    MAX_POLL_INTERVAL,
    MAX_SEARCH_RADIUS,
    MIN_LOCAL_RADIUS,
    MIN_MATERIAL_THRESHOLD,
    MIN_POLL_INTERVAL,
    MIN_SEARCH_RADIUS,
)

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _has_valid_ha_coordinates(hass: HomeAssistant) -> bool:
    """Return ``True`` when Home Assistant has configured latitude/longitude
    within valid geographic bounds."""
    lat = hass.config.latitude
    lon = hass.config.longitude
    if lat is None or lon is None:
        return False
    if not (-90.0 <= lat <= 90.0):
        return False
    if not (-180.0 <= lon <= 180.0):
        return False
    return True


async def _test_api_reachability(hass: HomeAssistant) -> str | None:
    """Attempt a single fetch from the outage endpoint.

    Returns ``None`` on success, or an error string key on failure.
    """
    session = async_get_clientsession(hass)
    api = XcelOutageApi(session)

    try:
        await api.fetch_events()
    except XcelOutagesConnectionError:
        _LOGGER.debug("API reachability test failed: connection error")
        return "cannot_connect"
    except XcelOutagesSchemaError:
        _LOGGER.debug("API reachability test failed: schema error")
        return "unsupported_response"

    return None


# ---------------------------------------------------------------------------
# Config flow
# ---------------------------------------------------------------------------


class XcelOutagesConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup of the Xcel Outage Map integration."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise transient setup state."""
        super().__init__()
        self._use_home_location: bool = True
        self._latitude_override: float | None = None
        self._longitude_override: float | None = None

    # ------------------------------------------------------------------
    # Step 1 — location preference (selection only)
    # ------------------------------------------------------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Entry point — delegate to the location step."""
        return await self.async_step_location(user_input)

    async def async_step_location(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Choose whether to use Home Assistant home coordinates or
        supply override values.

        This step only asks the location-source question.  When the user
        selects override, ``async_step_override`` (below) collects the
        required lat/lon values.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            self._use_home_location = user_input[CONF_USE_HOME_LOCATION]

            if self._use_home_location:
                # Validate HA coordinates are present and in range
                lat = self.hass.config.latitude
                lon = self.hass.config.longitude
                if lat is None or lon is None:
                    errors["base"] = "missing_coordinates"
                elif not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
                    errors["base"] = "invalid_coordinates"
                else:
                    return await self.async_step_params()
            else:
                # Defer coordinate collection to the override substep
                return await self.async_step_override()

            # If we reach here, there were errors for use_home=True
            # — the form will be re-shown with the error message.

        use_home_default = _has_valid_ha_coordinates(self.hass)

        return self.async_show_form(
            step_id="location",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USE_HOME_LOCATION, default=use_home_default
                    ): bool,
                }
            ),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Step 1b — override coordinates (conditional substep)
    # ------------------------------------------------------------------

    async def async_step_override(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Collect required override latitude and longitude.

        Both fields are required and validated to be within geographic
        bounds.  No silent HA/0 defaults are accepted — the user must
        explicitly provide values when override location is selected.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            lat = user_input[CONF_LATITUDE_OVERRIDE]
            lon = user_input[CONF_LONGITUDE_OVERRIDE]
            if lat is None or lon is None:
                errors["base"] = "missing_coordinates"
            elif not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
                errors["base"] = "invalid_coordinates"
            else:
                self._latitude_override = lat
                self._longitude_override = lon
                return await self.async_step_params()

        return self.async_show_form(
            step_id="override",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_LATITUDE_OVERRIDE): vol.All(
                        vol.Coerce(float),
                        vol.Range(min=-90, max=90),
                    ),
                    vol.Required(CONF_LONGITUDE_OVERRIDE): vol.All(
                        vol.Coerce(float),
                        vol.Range(min=-180, max=180),
                    ),
                }
            ),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Step 2 — parameters & test
    # ------------------------------------------------------------------

    async def async_step_params(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Collect search radius and poll interval, test the endpoint,
        and create the config entry."""
        errors: dict[str, str] = {}

        if user_input is not None:
            error_key = await _test_api_reachability(self.hass)
            if error_key is not None:
                errors["base"] = error_key

            if not errors:
                data: dict[str, Any] = {
                    CONF_USE_HOME_LOCATION: self._use_home_location,
                }
                if not self._use_home_location:
                    data[CONF_LATITUDE_OVERRIDE] = self._latitude_override
                    data[CONF_LONGITUDE_OVERRIDE] = self._longitude_override

                options: dict[str, Any] = {
                    CONF_SEARCH_RADIUS: user_input[CONF_SEARCH_RADIUS],
                    CONF_POLL_INTERVAL: user_input[CONF_POLL_INTERVAL],
                    CONF_LOCAL_RADIUS: DEFAULT_LOCAL_RADIUS,
                    CONF_MATERIAL_THRESHOLD: DEFAULT_MATERIAL_THRESHOLD,
                }

                return self.async_create_entry(
                    title="Xcel Outage Map",
                    data=data,
                    options=options,
                )

        schema_fields: dict[Any, Any] = {
            vol.Required(
                CONF_SEARCH_RADIUS, default=DEFAULT_SEARCH_RADIUS
            ): vol.All(
                NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SEARCH_RADIUS,
                        max=MAX_SEARCH_RADIUS,
                        step=1,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="km",
                    )
                ),
                vol.Coerce(int),
                vol.Range(min=MIN_SEARCH_RADIUS, max=MAX_SEARCH_RADIUS),
            ),
            vol.Required(
                CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL
            ): vol.All(
                NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_POLL_INTERVAL,
                        max=MAX_POLL_INTERVAL,
                        step=1,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="min",
                    )
                ),
                vol.Coerce(int),
                vol.Range(min=MIN_POLL_INTERVAL, max=MAX_POLL_INTERVAL),
            ),
        }

        return self.async_show_form(
            step_id="params",
            data_schema=vol.Schema(schema_fields),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OptionsFlow:
        """Return the options flow handler."""
        return XcelOutagesOptionsFlow(config_entry)


# ---------------------------------------------------------------------------
# Options flow
# ---------------------------------------------------------------------------


class XcelOutagesOptionsFlow(OptionsFlow):
    """Handle options updates for an existing config entry.

    Two-step flow:

    1. **init** — location-source toggle and all mutable parameters
       (search radius, local radius, material threshold, poll interval).
       Override coordinates are **not** shown here.

    2. **override (conditional)** — required lat/lon fields, shown only
       when the user selects override location.  Existing override values
       are pre-filled as defaults; missing overrides are never accepted.

    Data changes are persisted via
    :meth:`~homeassistant.config_entries.ConfigEntries.async_update_entry`,
    and the entry is reloaded by the update listener registered in
    ``__init__.py``, which creates a fresh coordinator (resetting the
    customer-total-increase baseline).
    """

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialise with the existing config entry."""
        self._config_entry = config_entry
        #: Stores the init-step field values while the override substep
        #: is showing (``None`` when not in the override path).
        self._pending_init: dict[str, Any] | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Show main settings (no override coords)."""
        if user_input is not None:
            use_home: bool = user_input[CONF_USE_HOME_LOCATION]

            if use_home:
                # Validate HA coordinates are present and in range
                lat = self.hass.config.latitude
                lon = self.hass.config.longitude
                if lat is None or lon is None:
                    return self.async_abort(reason="missing_coordinates")
                if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
                    return self.async_abort(reason="invalid_coordinates")

                # Save immediately — no override step needed
                return self._save_options(
                    init_data=user_input,
                    use_home=True,
                    lat=None,
                    lon=None,
                )

            # Override selected — store pending init data and show
            # the override-coordinates substep
            self._pending_init = user_input
            return await self.async_step_override()

        current_data = self._config_entry.data
        current_options = self._config_entry.options

        use_home_current = current_data.get(CONF_USE_HOME_LOCATION, True)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_USE_HOME_LOCATION, default=use_home_current
                    ): bool,
                    vol.Required(
                        CONF_SEARCH_RADIUS,
                        default=current_options.get(
                            CONF_SEARCH_RADIUS, DEFAULT_SEARCH_RADIUS
                        ),
                    ): vol.All(
                        NumberSelector(
                            NumberSelectorConfig(
                                min=MIN_SEARCH_RADIUS,
                                max=MAX_SEARCH_RADIUS,
                                step=1,
                                mode=NumberSelectorMode.BOX,
                                unit_of_measurement="km",
                            )
                        ),
                        vol.Coerce(int),
                        vol.Range(
                            min=MIN_SEARCH_RADIUS, max=MAX_SEARCH_RADIUS
                        ),
                    ),
                    vol.Required(
                        CONF_LOCAL_RADIUS,
                        default=current_options.get(
                            CONF_LOCAL_RADIUS, DEFAULT_LOCAL_RADIUS
                        ),
                    ): vol.All(
                        NumberSelector(
                            NumberSelectorConfig(
                                min=MIN_LOCAL_RADIUS,
                                max=MAX_LOCAL_RADIUS,
                                step=1,
                                mode=NumberSelectorMode.BOX,
                                unit_of_measurement="km",
                            )
                        ),
                        vol.Coerce(int),
                        vol.Range(
                            min=MIN_LOCAL_RADIUS, max=MAX_LOCAL_RADIUS
                        ),
                    ),
                    vol.Required(
                        CONF_MATERIAL_THRESHOLD,
                        default=current_options.get(
                            CONF_MATERIAL_THRESHOLD,
                            DEFAULT_MATERIAL_THRESHOLD,
                        ),
                    ): vol.All(
                        NumberSelector(
                            NumberSelectorConfig(
                                min=MIN_MATERIAL_THRESHOLD,
                                max=MAX_MATERIAL_THRESHOLD,
                                step=1,
                                mode=NumberSelectorMode.BOX,
                                unit_of_measurement="customers",
                            )
                        ),
                        vol.Coerce(int),
                        vol.Range(
                            min=MIN_MATERIAL_THRESHOLD,
                            max=MAX_MATERIAL_THRESHOLD,
                        ),
                    ),
                    vol.Required(
                        CONF_POLL_INTERVAL,
                        default=current_options.get(
                            CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
                        ),
                    ): vol.All(
                        NumberSelector(
                            NumberSelectorConfig(
                                min=MIN_POLL_INTERVAL,
                                max=MAX_POLL_INTERVAL,
                                step=1,
                                mode=NumberSelectorMode.BOX,
                                unit_of_measurement="min",
                            )
                        ),
                        vol.Coerce(int),
                        vol.Range(
                            min=MIN_POLL_INTERVAL, max=MAX_POLL_INTERVAL
                        ),
                    ),
                }
            ),
        )

    # ------------------------------------------------------------------
    # Options step 2 — override coordinates (conditional substep)
    # ------------------------------------------------------------------

    async def async_step_override(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Collect required override latitude and longitude.

        Existing stored override values are pre-filled as defaults so
        users changing other settings do not need to re-enter them.
        When no previous override exists (switching from home to
        override) the fields have no default — the user must type
        values explicitly.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            lat = user_input[CONF_LATITUDE_OVERRIDE]
            lon = user_input[CONF_LONGITUDE_OVERRIDE]
            if lat is None or lon is None:
                errors["base"] = "missing_coordinates"
            elif not (-90.0 <= lat <= 90.0) or not (-180.0 <= lon <= 180.0):
                errors["base"] = "invalid_coordinates"
            else:
                # _pending_init is guaranteed to be set before this step
                assert self._pending_init is not None
                init_data = self._pending_init
                self._pending_init = None
                return self._save_options(
                    init_data=init_data,
                    use_home=False,
                    lat=lat,
                    lon=lon,
                )

        current_data = self._config_entry.data
        existing_lat = current_data.get(CONF_LATITUDE_OVERRIDE)
        existing_lon = current_data.get(CONF_LONGITUDE_OVERRIDE)

        # Build schema — pre-fill existing override values when present,
        # otherwise require the user to enter coordinates with no default.
        schema: dict[Any, Any] = {}
        if existing_lat is not None:
            schema[vol.Required(CONF_LATITUDE_OVERRIDE, default=existing_lat)] = (
                vol.All(vol.Coerce(float), vol.Range(min=-90, max=90))
            )
        else:
            schema[vol.Required(CONF_LATITUDE_OVERRIDE)] = vol.All(
                vol.Coerce(float), vol.Range(min=-90, max=90)
            )
        if existing_lon is not None:
            schema[vol.Required(CONF_LONGITUDE_OVERRIDE, default=existing_lon)] = (
                vol.All(vol.Coerce(float), vol.Range(min=-180, max=180))
            )
        else:
            schema[vol.Required(CONF_LONGITUDE_OVERRIDE)] = vol.All(
                vol.Coerce(float), vol.Range(min=-180, max=180)
            )

        return self.async_show_form(
            step_id="override",
            data_schema=vol.Schema(schema),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Persistence helper
    # ------------------------------------------------------------------

    def _save_options(
        self,
        init_data: dict[str, Any],
        use_home: bool,
        lat: float | None,
        lon: float | None,
    ) -> dict[str, Any]:
        """Persist data and options, then return the flow result."""
        # ---- data (immutable-at-setup values we choose to mutate) ----
        new_data = dict(self._config_entry.data)
        new_data[CONF_USE_HOME_LOCATION] = use_home
        if not use_home:
            new_data[CONF_LATITUDE_OVERRIDE] = lat
            new_data[CONF_LONGITUDE_OVERRIDE] = lon
        else:
            new_data.pop(CONF_LATITUDE_OVERRIDE, None)
            new_data.pop(CONF_LONGITUDE_OVERRIDE, None)

        # ---- options (mutable) --------------------------------------
        new_options = {
            CONF_SEARCH_RADIUS: init_data[CONF_SEARCH_RADIUS],
            CONF_LOCAL_RADIUS: init_data[CONF_LOCAL_RADIUS],
            CONF_MATERIAL_THRESHOLD: init_data[CONF_MATERIAL_THRESHOLD],
            CONF_POLL_INTERVAL: init_data[CONF_POLL_INTERVAL],
        }

        # Persist both data and options, then let the update listener
        # (registered in __init__.py) trigger a reload that creates a
        # new coordinator with a fresh baseline.
        self.hass.config_entries.async_update_entry(
            self._config_entry,
            data=new_data,
            options=new_options,
        )

        return self.async_create_entry(title="", data=new_options)
