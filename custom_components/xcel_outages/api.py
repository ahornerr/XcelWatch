"""Async HTTP client for the Xcel Energy outage-map endpoint.

The client uses Home Assistant's shared ``aiohttp`` session, enforces a
descriptive User-Agent and JSON Accept header, applies an explicit timeout,
and returns a structured :class:`~models.ParseOutcome`.

Domain-specific exceptions never include raw payloads or configured
coordinates.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiohttp
from homeassistant.exceptions import HomeAssistantError

from .const import ENDPOINT_URL, REQUEST_TIMEOUT, USER_AGENT
from .models import ParseOutcome
from .parser import parse_payload

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain-specific exceptions
# ---------------------------------------------------------------------------


class XcelOutagesError(HomeAssistantError):
    """Base exception for the Xcel Outage Map integration."""


class XcelOutagesConnectionError(XcelOutagesError):
    """Communication failure (timeout, HTTP error, network issue).

    The message is intentionally generic and contains no payload or
    coordinate data.
    """


class XcelOutagesSchemaError(XcelOutagesError):
    """Unexpected or unparseable API response.

    Raised when:
    - The top-level JSON value is not a list.
    - Every record in the list is malformed.
    - JSON decoding fails.
    """


# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------


class XcelOutageApi:
    """Async HTTP client for the Xcel Energy outage-map event endpoint.

    Usage::

        api = XcelOutageApi(async_get_clientsession(hass))
        outcome = await api.fetch_events()
    """

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Initialise the client with an HA-managed ``aiohttp`` session."""
        self._session = session

    async def fetch_events(self) -> ParseOutcome:
        """Fetch and parse the outage-event list from the public endpoint.

        Returns
        -------
        ParseOutcome:
            Structured result that distinguishes valid data from filtered
            or empty payloads.

        Raises
        ------
        XcelOutagesConnectionError:
            Network, timeout, or HTTP-level failure.
        XcelOutagesSchemaError:
            Response is not a JSON list, or every record is malformed.
        """
        _LOGGER.debug("Fetching outage events from %s", ENDPOINT_URL)

        try:
            async with self._session.get(
                ENDPOINT_URL,
                headers={
                    "Accept": "application/json",
                    "User-Agent": USER_AGENT,
                },
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                raise_for_status=False,
            ) as resp:
                if resp.status != 200:
                    _LOGGER.debug("API returned HTTP %d", resp.status)
                    raise XcelOutagesConnectionError(
                        f"Endpoint returned HTTP {resp.status}"
                    )

                try:
                    data: Any = await resp.json()
                except (
                    json.JSONDecodeError,
                    ValueError,
                    TypeError,
                ) as err:
                    _LOGGER.debug("Failed to decode JSON response")
                    raise XcelOutagesSchemaError(
                        "Could not decode API response"
                    ) from err

        except asyncio.TimeoutError as err:
            _LOGGER.debug("Request timed out after %ds", REQUEST_TIMEOUT)
            raise XcelOutagesConnectionError(
                "Request timed out"
            ) from err
        except aiohttp.ClientError as err:
            _LOGGER.debug("HTTP client error: %s", type(err).__name__)
            raise XcelOutagesConnectionError(
                "Could not reach the outage API"
            ) from err

        # --- Parse payload via the pure-core parser -------------------------
        outcome = parse_payload(data)

        if not outcome.is_valid_payload:
            # Top-level value was not a list
            _LOGGER.debug("Payload is not a list (type=%s)", type(data).__name__)
            raise XcelOutagesSchemaError("Unexpected API response shape")

        if outcome.raw_count > 0 and outcome.malformed_count == outcome.raw_count:
            # Every record in the list was malformed
            _LOGGER.debug(
                "All %d record(s) were malformed; possible schema change",
                outcome.raw_count,
            )
            raise XcelOutagesSchemaError("Could not parse any event records")

        _LOGGER.debug(
            "Fetched %d record(s); %d valid, %d malformed, "
            "%d filtered (status), %d event(s) remain",
            outcome.raw_count,
            outcome.parsed_count,
            outcome.malformed_count,
            outcome.filtered_status_count,
            len(outcome.events),
        )

        return outcome
